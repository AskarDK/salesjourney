import os, asyncio, aiohttp, socket, unicodedata
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.client.session.aiohttp import AiohttpSession  # сессия под AioHTTP

# загружаем .env из корня проекта (или рядом с bot.py)
load_dotenv()

API_BASE = os.getenv("BACKEND_URL", "http://localhost:5000")  # Flask base URL
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

dp = Dispatcher()
rt = Router()
dp.include_router(rt)

WELCOME = (
    "Привет! 👋\n"
    "Чтобы привязать аккаунт, отправьте <b>код привязки</b>, который вы сгенерировали в профиле на сайте."
)

# ---------- клавиатура ----------
def main_kb() -> types.ReplyKeyboardMarkup:
    return types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [types.KeyboardButton(text="👤 Профиль"), types.KeyboardButton(text="🔔 Уведомления")]
        ],
    )

# ---------- утилиты сети/сессии ----------
def build_bot_session() -> AiohttpSession:
    """
    Кросс-версионная сборка сессии бота.
    ENV:
      TELEGRAM_PROXY_URL="socks5://user:pass@host:port" или "http://host:port"
      FORCE_IPV4=1  (по умолчанию 1)
    """
    proxy = (os.getenv("TELEGRAM_PROXY_URL") or "").strip() or None
    force_ipv4 = (os.getenv("FORCE_IPV4", "1").lower() not in ("0", "false", "no"))
    family = socket.AF_INET if force_ipv4 else socket.AF_UNSPEC
    connector = aiohttp.TCPConnector(family=family, ttl_dns_cache=60)
    try:
        return AiohttpSession(proxy=proxy, connector=connector)  # новые версии aiogram
    except TypeError:
        return AiohttpSession(proxy=proxy)  # старые версии aiogram (без параметра connector)

async def _http_json(method: str, url: str, *, json: dict | None = None, timeout: int = 10):
    try:
        async with aiohttp.ClientSession() as s:
            if method.upper() == "GET":
                async with s.get(url, timeout=timeout) as r:
                    return await r.json()
            else:
                async with s.post(url, json=json, timeout=timeout) as r:
                    return await r.json()
    except Exception:
        return None

# ---------- кэш пользователя по chat_id ----------
_cache: dict[int, dict] = {}

def _cache_put(chat_id: int, user: dict):
    _cache[chat_id] = user or {}

def _cache_get(chat_id: int) -> dict | None:
    return _cache.get(chat_id)

# ---------- распознавание кнопок ----------
def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u200d", "").replace("\ufe0f", "").replace("\u00a0", " ")
    return s.strip().lower()

def _is_profile_btn(t: str) -> bool:
    t = _norm(t)
    return "профиль" in t

def _is_notify_btn(t: str) -> bool:
    t = _norm(t)
    return "уведомлен" in t  # покрывает «уведомления»

# ---------- форматирование ----------
def _fmt_profile_block(u: dict, *, show_name: bool = True) -> str:
    if not u:
        return ""
    lines = []
    name = u.get("display_name") or "Пользователь"
    if show_name:
        lines.append(f"<b>👤 {name}</b>")
    if u.get("email"):
        lines.append(f"✉️  {u['email']}")
    lvl = u.get("level")
    xp = u.get("xp")
    coins = u.get("coins")
    if lvl is not None and xp is not None:
        lines.append(f"📈 Уровень: <b>{lvl}</b> · XP: <b>{xp}</b>")
    if coins is not None:
        lines.append(f"🪙 Монеты: <b>{coins}</b>")
    if u.get("company"):
        lines.append(f"🏢 Компания: <b>{u['company']}</b>")
    return "\n".join(lines)

# ---------- API-хелперы ----------
async def _whoami(chat_id: int):
    cid = str(chat_id)
    j = await _http_json("GET", f"{API_BASE}/api/telegram/bot/me?chat_id={cid}")
    if j and j.get("ok") and "linked" in j:
        return j
    j = await _http_json("POST", f"{API_BASE}/api/telegram/bot/me", json={"chat_id": cid})
    return j if (j and j.get("ok") and "linked" in j) else None

async def _last_notifications(chat_id: int, limit: int = 5):
    cid = str(chat_id)
    j = await _http_json("GET", f"{API_BASE}/api/telegram/bot/notifications?chat_id={cid}&limit={int(limit)}")
    if j and j.get("ok"):
        return j
    j = await _http_json("POST", f"{API_BASE}/api/telegram/bot/notifications", json={"chat_id": cid, "limit": int(limit)})
    return j if (j and j.get("ok")) else None

# ---------- команды ----------
# ✅ Исправлено: обрабатываем И обычный /start, И /start <payload>
@rt.message(CommandStart())
async def start(m: types.Message):
    text = (m.text or "").strip()
    payload = ""
    if " " in text:
        payload = text.split(" ", 1)[1].strip()

    # deep-link код → привязка
    if payload and payload.isalnum() and 4 <= len(payload) <= 16:
        await _try_link_code(m, payload.upper())
        return

    who = await _whoami(m.chat.id)

    if who and who.get("linked"):
        user = who.get("user") or {}
        _cache_put(m.chat.id, user)
        name = user.get("display_name") or "Пользователь"
        msg = f"<b>{name}</b>, вы уже привязаны.\n\n{_fmt_profile_block(user, show_name=False)}"
        await m.answer(msg, reply_markup=main_kb())
        return

    # фолбэк на кэш — если API не ответил вовремя
    cached = _cache_get(m.chat.id)
    if cached:
        name = cached.get("display_name") or "Пользователь"
        msg = f"<b>{name}</b>, вы уже привязаны.\n\n{_fmt_profile_block(cached, show_name=False)}"
        await m.answer(msg, reply_markup=main_kb())
        return

    await m.answer(WELCOME, reply_markup=main_kb())

@rt.message(Command("me"))
async def cmd_me(m: types.Message):
    who = await _whoami(m.chat.id)
    if who and who.get("linked"):
        user = who.get("user") or {}
        _cache_put(m.chat.id, user)
        await m.answer(_fmt_profile_block(user), reply_markup=main_kb())
    else:
        await m.answer(
            "Аккаунт ещё не привязан. Сгенерируйте код в профиле на сайте и отправьте его сюда.",
            reply_markup=main_kb()
        )

@rt.message(Command("notify"))
async def cmd_notify(m: types.Message):
    j = await _last_notifications(m.chat.id, limit=5)
    if not j or not j.get("ok"):
        cached = _cache_get(m.chat.id)
        if cached:
            await m.answer("Пока уведомлений нет ✨", reply_markup=main_kb())
        else:
            await m.answer(
                "Аккаунт ещё не привязан. Сгенерируйте код в профиле на сайте и отправьте его сюда.",
                reply_markup=main_kb()
            )
        return

    if not j.get("linked"):
        await m.answer(
            "Аккаунт ещё не привязан. Сгенерируйте код в профиле на сайте и отправьте его сюда.",
            reply_markup=main_kb()
        )
        return

    items = j.get("items") or []
    if not items:
        await m.answer("Пока уведомлений нет ✨", reply_markup=main_kb())
        return

    lines = ["<b>Последние уведомления:</b>"]
    for n in items:
        dt = n.get("created_at", "")[:19].replace("T", " ")
        title = n.get("title") or "Уведомление"
        body = n.get("body") or ""
        lines.append(f"• <b>{title}</b>\n  {body}\n  <i>{dt}</i>")
    await m.answer("\n\n".join(lines), reply_markup=main_kb())

async def _try_link_code(m: types.Message, code: str):
    payload = {"code": code, "chat_id": str(m.chat.id), "username": m.from_user.username or ""}
    j = await _http_json("POST", f"{API_BASE}/api/telegram/bot/link", json=payload)
    if not j:
        await m.answer("Сервис временно недоступен. Попробуйте позже.", reply_markup=main_kb())
        return

    if j.get("ok"):
        user = j.get("user") or {}
        if user:
            _cache_put(m.chat.id, user)

        who = await _whoami(m.chat.id)
        if who and who.get("linked"):
            user = who.get("user") or user
            _cache_put(m.chat.id, user)
            await m.answer(
                "✅ Готово! Вы привязаны. Теперь уведомления будут приходить сюда.\n\n" + _fmt_profile_block(user),
                reply_markup=main_kb()
            )
        else:
            await m.answer("✅ Готово! Вы привязаны. Теперь уведомления будут приходить сюда.", reply_markup=main_kb())
    else:
        err = j.get("error") or "UNKNOWN"
        if err == "CODE_NOT_FOUND":
            await m.answer("❌ Код не найден. Сгенерируйте новый в профиле.", reply_markup=main_kb())
        elif err == "CODE_EXPIRED":
            await m.answer("⏳ Срок действия кода истёк. Сгенерируйте новый в профиле.", reply_markup=main_kb())
        else:
            await m.answer("❌ Не удалось привязать. Попробуйте ещё раз.", reply_markup=main_kb())

@rt.message(F.text.len() >= 4)
async def handle_code(m: types.Message):
    t = (m.text or "").strip()

    # игнорируем команды
    if t.startswith("/"):
        return

    # кнопки → маршрутизация
    if _is_profile_btn(t):
        await cmd_me(m)
        return
    if _is_notify_btn(t):
        await cmd_notify(m)
        return

    # строгая валидация кода
    code = t.upper()
    if not (code.isascii() and code.isalnum() and 4 <= len(code) <= 16):
        await m.answer("Код должен содержать латинские буквы/цифры (4–16). Попробуйте ещё раз.", reply_markup=main_kb())
        return

    await _try_link_code(m, code)

# ---------- запуск ----------
async def main():
    token = BOT_TOKEN or ""
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан (env). Проверьте .env или переменные среды")

    # Префлайт: проверим, что DNS хотя бы резолвит api.telegram.org
    loop = asyncio.get_running_loop()
    try:
        await loop.getaddrinfo("api.telegram.org", 443, type=socket.SOCK_STREAM, family=socket.AF_INET)
    except Exception as e:
        print("❌ DNS не может разрешить api.telegram.org (IPv4).")
        print("   Проверьте интернет/файрвол/прокси. Можно задать TELEGRAM_PROXY_URL или отключить корпоративный VPN.")
        print("   Детали:", repr(e))

    session = build_bot_session()  # своя сессия (IPv4/прокси)
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)

    print("Bot started (IPv4 forced; proxy:", os.getenv("TELEGRAM_PROXY_URL") or "none", ").")

    try:
        await dp.start_polling(bot)
    except Exception:
        print("❌ Бот упал при старте. Частая причина — блокировка доступа к api.telegram.org или DNS.")
        print("   Попробуйте задать TELEGRAM_PROXY_URL или сменить сеть/провайдера/DNS (8.8.8.8/1.1.1.1).")
        raise

if __name__ == "__main__":
    asyncio.run(main())
