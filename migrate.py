# migrate.py
import argparse
import json
import sqlite3
from contextlib import closing

INTRO_TEXT = (
    "Здесь вы быстро пройдёте регистрацию и выберете, хотите ли познакомиться "
    "с компанией прямо сейчас."
)

def table_exists(conn, name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    )
    return cur.fetchone() is not None

def column_exists(conn, table: str, col: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())

def ensure_schema(conn: sqlite3.Connection):
    conn.execute("PRAGMA foreign_keys = ON")

    # 1) flows
    if not table_exists(conn, "onboarding_flows"):
        conn.execute(
            """
            CREATE TABLE onboarding_flows (
              id                   INTEGER PRIMARY KEY AUTOINCREMENT,
              name                 TEXT NOT NULL,
              final_bonus_coins    INTEGER NOT NULL DEFAULT 0,
              is_active            INTEGER NOT NULL DEFAULT 1,
              created_at           TEXT,
              updated_at           TEXT
            );
            """
        )

    # 2) steps
    if not table_exists(conn, "onboarding_steps"):
        conn.execute(
            """
            CREATE TABLE onboarding_steps (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              flow_id       INTEGER NOT NULL REFERENCES onboarding_flows(id) ON DELETE CASCADE,
              type          TEXT NOT NULL,                   -- enum-замена
              title         TEXT,
              body_md       TEXT,
              ask_field     TEXT,
              is_required   INTEGER NOT NULL DEFAULT 0,
              coins_award   INTEGER NOT NULL DEFAULT 0,
              xp_award      INTEGER NOT NULL DEFAULT 0,
              order_index   INTEGER NOT NULL DEFAULT 0,
              -- новые поля
              is_active     INTEGER NOT NULL DEFAULT 1,
              is_immutable  INTEGER NOT NULL DEFAULT 0,
              config        TEXT NOT NULL DEFAULT '{}',      -- json как TEXT
              media_url     TEXT,
              created_at    TEXT,
              updated_at    TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onb_steps_flow ON onboarding_steps(flow_id)")

    # 3) step options
    if not table_exists(conn, "onboarding_step_options"):
        conn.execute(
            """
            CREATE TABLE onboarding_step_options (
              id          INTEGER PRIMARY KEY AUTOINCREMENT,
              step_id     INTEGER NOT NULL REFERENCES onboarding_steps(id) ON DELETE CASCADE,
              key         TEXT NOT NULL,
              title       TEXT NOT NULL,
              body_md     TEXT,
              order_index INTEGER NOT NULL DEFAULT 0,
              UNIQUE(step_id, key)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onb_opts_step ON onboarding_step_options(step_id)")

    # На всякий — дотащим новые колонки, если таблица уже была старой
    for col, coldef in [
        ("is_active",    "is_active INTEGER NOT NULL DEFAULT 1"),
        ("is_immutable", "is_immutable INTEGER NOT NULL DEFAULT 0"),
        ("config",       "config TEXT NOT NULL DEFAULT '{}'"),
        ("media_url",    "media_url TEXT"),
    ]:
        if not column_exists(conn, "onboarding_steps", col):
            conn.execute(f"ALTER TABLE onboarding_steps ADD COLUMN {coldef}")

def ensure_flow(conn: sqlite3.Connection, flow_id: int, name: str):
    cur = conn.execute("SELECT id FROM onboarding_flows WHERE id=?", (flow_id,))
    if cur.fetchone() is None:
        # Вставляем с заданным id — SQLite это позволяет
        conn.execute(
            "INSERT INTO onboarding_flows (id, name, final_bonus_coins, is_active) VALUES (?, ?, ?, 1)",
            (flow_id, name, 50),
        )

def disable_old_ask_input(conn, flow_ids):
    qmarks = ",".join("?" * len(flow_ids))
    conn.execute(
        f"UPDATE onboarding_steps SET is_active=0 WHERE flow_id IN ({qmarks}) AND type='ask_input'",
        flow_ids,
    )

def move_reward_to_end(conn, flow_ids):
    # Ставим reward_shop временно после максимального индекса
    for fid in flow_ids:
        cur = conn.execute(
            "SELECT COALESCE(MAX(order_index), -1) FROM onboarding_steps WHERE flow_id=?", (fid,)
        )
        mx = cur.fetchone()[0]
        conn.execute(
            "UPDATE onboarding_steps SET order_index=? WHERE flow_id=? AND type='reward_shop'",
            (mx + 1, fid),
        )

def upsert_intro(conn, fid: int):
    cur = conn.execute(
        "SELECT id FROM onboarding_steps WHERE flow_id=? AND type='intro_page' AND is_active=1 LIMIT 1",
        (fid,),
    )
    row = cur.fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO onboarding_steps
               (flow_id,type,title,body_md,is_required,coins_award,xp_award,order_index,config,is_active,is_immutable)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fid,
                "intro_page",
                "Добро пожаловать!",
                INTRO_TEXT,
                0,
                5,
                5,
                0,
                json.dumps({}),
                1,
                0,
            ),
        )
    else:
        conn.execute(
            "UPDATE onboarding_steps SET order_index=0 WHERE id=?", (row[0],)
        )

def ensure_registration_section(conn, fid: int):
    cur = conn.execute(
        "SELECT id FROM onboarding_steps WHERE flow_id=? AND type='registration_section' AND is_active=1 LIMIT 1",
        (fid,),
    )
    if cur.fetchone() is None:
        conn.execute(
            """INSERT INTO onboarding_steps
               (flow_id,type,title,body_md,is_required,coins_award,xp_award,order_index,config,is_active,is_immutable)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fid,
                "registration_section",
                "Регистрация",
                "Заполните контактные данные одним экраном: имя, email, телефон.",
                1,
                5,
                5,
                1,
                json.dumps({}),
                1,
                0,
            ),
        )
    else:
        # гарантируем позицию
        conn.execute(
            """UPDATE onboarding_steps
               SET order_index=1, is_active=1
               WHERE flow_id=? AND type='registration_section'""",
            (fid,),
        )

def upsert_choice_and_options(conn, fid: int):
    # сам шаг
    cur = conn.execute(
        "SELECT id FROM onboarding_steps WHERE flow_id=? AND type='choice_one' AND is_active=1 LIMIT 1",
        (fid,),
    )
    if cur.fetchone() is None:
        conn.execute(
            """INSERT INTO onboarding_steps
               (flow_id,type,title,body_md,is_required,coins_award,xp_award,order_index,config,is_active,is_immutable)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fid,
                "choice_one",
                "Познакомимся с компанией?",
                "Выберите: посмотреть информацию о компании сейчас или позже.",
                0,
                5,
                5,
                2,
                json.dumps({}),
                1,
                0,
            ),
        )

    # id шага
    cur = conn.execute(
        "SELECT id FROM onboarding_steps WHERE flow_id=? AND type='choice_one' AND is_active=1 LIMIT 1",
        (fid,),
    )
    step_id = cur.fetchone()[0]

    # опции (уникальны по (step_id, key))
    for key, title, body, idx in [
        ("intro_now", "Да, показать сейчас", "Показать информацию о компании.", 0),
        ("later", "Позже", "Перейти к завершению.", 1),
    ]:
        conn.execute(
            """INSERT OR IGNORE INTO onboarding_step_options(step_id,key,title,body_md,order_index)
               VALUES (?,?,?,?,?)""",
            (step_id, key, title, body, idx),
        )

def upsert_reward_shop(conn, fid: int):
    cur = conn.execute(
        "SELECT id FROM onboarding_steps WHERE flow_id=? AND type='reward_shop' LIMIT 1",
        (fid,),
    )
    if cur.fetchone() is None:
        conn.execute(
            """INSERT INTO onboarding_steps
               (flow_id,type,title,body_md,is_required,coins_award,xp_award,order_index,config,is_active,is_immutable)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fid,
                "reward_shop",
                "Финальный бонус",
                "После завершения можно выбрать приз.",
                0,
                0,
                0,
                3,
                json.dumps({}),
                1,
                0,
            ),
        )
    else:
        conn.execute(
            """UPDATE onboarding_steps
               SET order_index=3, is_active=1
               WHERE flow_id=? AND type='reward_shop'""",
            (fid,),
        )

def renumber_order(conn, fid: int):
    # Перечитываем шаги, сортируем и назначаем индексы 0..n-1
    cur = conn.execute(
        """SELECT id, order_index FROM onboarding_steps
           WHERE flow_id=? AND is_active=1
           ORDER BY order_index, id""",
        (fid,),
    )
    rows = cur.fetchall()
    for idx, (sid, _) in enumerate(rows):
        conn.execute("UPDATE onboarding_steps SET order_index=? WHERE id=?", (idx, sid))

def migrate(conn: sqlite3.Connection, flow_ids):
    ensure_schema(conn)
    # убедимся, что потоки существуют
    for fid in flow_ids:
        ensure_flow(conn, fid, name=f"Онбординг флоу #{fid}")

    disable_old_ask_input(conn, flow_ids)
    move_reward_to_end(conn, flow_ids)

    for fid in flow_ids:
        upsert_intro(conn, fid)
        ensure_registration_section(conn, fid)
        upsert_choice_and_options(conn, fid)
        upsert_reward_shop(conn, fid)
        renumber_order(conn, fid)

def add_telegram_columns(conn):
    # добавить колонки в users, если их нет
    def col_exists(name):
        cur = conn.execute("PRAGMA table_info(users)")
        return any(row[1] == name for row in cur.fetchall())

    if not col_exists("telegram_chat_id"):
        conn.execute("ALTER TABLE users ADD COLUMN telegram_chat_id TEXT")
    if not col_exists("tg_link_code"):
        conn.execute("ALTER TABLE users ADD COLUMN tg_link_code TEXT UNIQUE")
    if not col_exists("tg_link_code_created_at"):
        conn.execute("ALTER TABLE users ADD COLUMN tg_link_code_created_at DATETIME")
    if not col_exists("tg_linked_at"):
        conn.execute("ALTER TABLE users ADD COLUMN tg_linked_at DATETIME")

def main():
    ap = argparse.ArgumentParser(description="Миграции: онбординг/telegram")
    ap.add_argument("--db", default="sales_journey.db",
                    help="путь к SQLite базе (по умолчанию sales_journey.db)")
    ap.add_argument("--flows", default="1,2",
                    help="ID флоу, через запятую (по умолчанию 1,2)")
    ap.add_argument("--op", choices=["onboarding3", "add_tg_columns"], default="onboarding3",
                    help="операция: onboarding3 (по умолчанию) или add_tg_columns")
    args = ap.parse_args()

    with closing(sqlite3.connect(args.db)) as conn:
        try:
            conn.isolation_level = None
            conn.execute("BEGIN")
            if args.op == "onboarding3":
                flow_ids = [int(x.strip()) for x in args.flows.split(",") if x.strip()]
                migrate(conn, flow_ids)
                print(f"OK: миграция онбординга для флоу {flow_ids}")
            else:
                add_telegram_columns(conn)
                print("OK: добавлены колонки Telegram в users")
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            raise

if __name__ == "__main__":
    main()
