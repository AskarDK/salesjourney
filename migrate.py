# seed_demo.py
# Единоразовая загрузка демо-данных для Sales Journey
# Запуск:  python seed_demo.py

from datetime import datetime
import json
import uuid

from werkzeug.security import generate_password_hash

from app import (
    app, db,
    User, Company, CompanyMember,
    PartnerUser, AdminUser,
    Achievement, UserAchievement,
    AvatarItem, UserAvatar, Inventory,
    TrainingCourse, TrainingQuestion, TrainingOption, TrainingEnrollment, TrainingAttempt,
    ScoreEvent,
    now_utc, xp_required
)

# ---------------- helpers ----------------

def get_or_create_admin(email: str, password_plain: str):
    a = AdminUser.query.filter_by(email=email.lower()).first()
    if a:
        return a
    a = AdminUser(email=email.lower(), password=generate_password_hash(password_plain))
    db.session.add(a)
    db.session.commit()
    return a

def get_or_create_partner(email: str, password_plain: str, display_name: str):
    p = PartnerUser.query.filter_by(email=email.lower()).first()
    if p:
        return p
    p = PartnerUser(email=email.lower(), password=generate_password_hash(password_plain), display_name=display_name)
    db.session.add(p)
    db.session.commit()
    return p

def get_or_create_company(name: str, slug: str, owner_partner_id=None):
    c = Company.query.filter_by(slug=slug.lower()).first()
    if c:
        # убедимся что есть join_code
        if not getattr(c, "join_code", None):
            c.join_code = uuid.uuid4().hex[:8].upper()
            db.session.commit()
        if owner_partner_id and not c.owner_partner_id:
            c.owner_partner_id = owner_partner_id
            db.session.commit()
        return c
    c = Company(
        name=name, slug=slug.lower(),
        owner_partner_id=owner_partner_id,
        # если поле есть — заполним код
        join_code=uuid.uuid4().hex[:8].upper()
    )
    db.session.add(c)
    db.session.commit()
    return c

def get_or_create_user(email: str, password_plain: str, display_name: str, gender: str = None, company: Company | None = None, make_admin=False):
    u = User.query.filter_by(email=email.lower()).first()
    if u:
        return u
    u = User(
        email=email.lower(),
        password=generate_password_hash(password_plain),
        display_name=display_name,
        gender=gender or None
    )
    db.session.add(u)
    db.session.flush()

    # базовый аватар
    base = AvatarItem.query.filter_by(slot="base", key="base_t1").first()
    if not base:
        base = AvatarItem(slot="base", key="base_t1", gender="any", min_level=1, rarity="common", asset_url="/assets/avatars/base/base_t1.png")
        db.session.add(base); db.session.flush()
    db.session.add(UserAvatar(user_id=u.id, selected_by_slot=json.dumps({"base": base.key})))

    # приветственная ачивка
    ach = Achievement.query.filter_by(code="WELCOME").first()
    if not ach:
        ach = Achievement(code="WELCOME", title="Первое знакомство", points=50, rarity="common", description="Заверши регистрацию")
        db.session.add(ach); db.session.flush()
    if not UserAchievement.query.filter_by(user_id=u.id, achievement_id=ach.id).first():
        db.session.add(UserAchievement(user_id=u.id, achievement_id=ach.id))
        u.xp += ach.points

    # компания и роль
    if company:
        u.company_id = company.id
        if make_admin:
            if not CompanyMember.query.filter_by(company_id=company.id, user_id=u.id).first():
                db.session.add(CompanyMember(company_id=company.id, user_id=u.id, role="admin"))
        else:
            if not CompanyMember.query.filter_by(company_id=company.id, user_id=u.id).first():
                db.session.add(CompanyMember(company_id=company.id, user_id=u.id, role="member"))

    db.session.commit()
    return u

def get_or_create_achievement(code: str, title: str, points: int = 50, rarity="common", description=None):
    a = Achievement.query.filter_by(code=code).first()
    if a:
        return a
    a = Achievement(code=code, title=title, points=points, rarity=rarity, description=description)
    db.session.add(a)
    db.session.commit()
    return a

def get_or_create_course(title: str, scope: str = "global", company: Company | None = None,
                         description: str = None, content_md: str = None, youtube_url: str = None,
                         pass_score: int = 80, max_attempts: int = 3, xp_reward: int = 50,
                         achievement_code: str | None = None, created_by_partner_id: int | None = None):
    q = TrainingCourse.query.filter_by(title=title).first()
    if q:
        return q
    c = TrainingCourse(
        title=title,
        description=description,
        content_md=content_md,
        youtube_url=youtube_url,
        pass_score=pass_score,
        max_attempts=max_attempts,
        xp_reward=xp_reward,
        achievement_code=achievement_code,
        scope=scope,
        company_id=(company.id if (scope == "company" and company) else None),
        created_by_admin=(scope == "global" and created_by_partner_id is None),
        created_by_partner_id=created_by_partner_id
    )
    db.session.add(c)
    db.session.commit()
    return c

def ensure_questions(course: TrainingCourse, questions: list[dict]):
    """questions = [{ 'text': '...', 'options': [{'text': '...', 'is_correct': True}, ...] }, ...]"""
    existing = TrainingQuestion.query.filter_by(course_id=course.id).count()
    if existing:
        return
    for idx, q in enumerate(questions):
        tq = TrainingQuestion(course_id=course.id, text=q.get("text","").strip(), order_index=idx)
        db.session.add(tq); db.session.flush()
        for opt in (q.get("options") or []):
            db.session.add(TrainingOption(
                question_id=tq.id,
                text=(opt.get("text") or "").strip(),
                is_correct=bool(opt.get("is_correct", False))
            ))
    db.session.commit()

def enroll_course_for_company(course: TrainingCourse, company: Company):
    if not TrainingEnrollment.query.filter_by(course_id=course.id, target_type="company", target_id=company.id).first():
        db.session.add(TrainingEnrollment(course_id=course.id, target_type="company", target_id=company.id))
        db.session.commit()

def record_pass_attempt(user: User, course: TrainingCourse, score: int):
    """Создаёт успешную попытку с начислением XP и ачивки (если настроена). Идемпотентность по простому признаку — если уже есть passed attempt, не дублируем."""
    exists = TrainingAttempt.query.filter_by(course_id=course.id, user_id=user.id, passed=True).first()
    if exists:
        return exists

    att = TrainingAttempt(course_id=course.id, user_id=user.id, score=score, passed=True, answers_json=json.dumps({}))
    db.session.add(att)

    # XP за курс
    reward = max(0, int(course.xp_reward or 0))
    user.xp += reward
    db.session.add(ScoreEvent(
        user_id=user.id, source="training", points=reward, coins=0,
        meta_json=json.dumps({"course_id": course.id, "title": course.title, "score": score})
    ))

    # Ачивка курса
    if course.achievement_code:
        ach = Achievement.query.filter_by(code=course.achievement_code).first()
        if ach and not UserAchievement.query.filter_by(user_id=user.id, achievement_id=ach.id).first():
            db.session.add(UserAchievement(user_id=user.id, achievement_id=ach.id))
            user.xp += ach.points
            db.session.add(ScoreEvent(
                user_id=user.id, source="achievement", points=ach.points, coins=0,
                meta_json=json.dumps({"code": course.achievement_code})
            ))
    db.session.commit()
    return att

def record_fail_attempt(user: User, course: TrainingCourse, score: int):
    """Неуспешная попытка без награждения."""
    att = TrainingAttempt(course_id=course.id, user_id=user.id, score=score, passed=False, answers_json=json.dumps({}))
    db.session.add(att)
    db.session.commit()
    return att

# ---------------- main seeding ----------------

with app.app_context():
    print("==> Создаём/обновляем базу…")

    # Базовые ачивки (если вдруг не создались при старте приложения)
    get_or_create_achievement("WELCOME", "Первое знакомство", 50, "common", "Заверши регистрацию")
    get_or_create_achievement("PROFILE_100", "Полный профиль", 100, "uncommon", "Заполни профиль на 100%")

    # Админ
    admin_email = "admin@salesjourney.local"
    admin_pass  = "admin123"
    admin = get_or_create_admin(admin_email, admin_pass)

    # Партнёр и его компания
    partner_email = "partner@demo.local"
    partner_pass  = "partner123"
    partner = get_or_create_partner(partner_email, partner_pass, "Partner One")

    company = get_or_create_company("Acme Corp", "acme", owner_partner_id=partner.id)

    # Пользователи компании
    manager = get_or_create_user("manager@acme.local", "pass123", "Alice Manager", gender="female", company=company, make_admin=True)
    bob     = get_or_create_user("bob@acme.local", "pass123", "Bob Seller", gender="male", company=company, make_admin=False)
    chris   = get_or_create_user("chris@acme.local", "pass123", "Chris SDR", gender="female", company=company, make_admin=False)

    # Внешний пользователь (не из компании)
    outsider = get_or_create_user("outsider@demo.local", "pass123", "Evan Outsider", gender="male", company=None, make_admin=False)

    # Глобальный курс (виден всем)
    ach_onboard = get_or_create_achievement("TRAIN_ONBOARD", "Онбординг пройден", 70, "common", "Пройди базовый онбординг")
    global_course = get_or_create_course(
        title="Онбординг Sales Journey",
        scope="global",
        description="Как работает геймификация, XP/ачивки, лидерборды и магазин.",
        content_md=(
            "# Онбординг\n"
            "- Что такое XP и уровни\n"
            "- Как получить ачивки\n"
            "- Где смотреть конкурсы и магазин\n"
            "Удачи и высоких конверсий!"
        ),
        youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        pass_score=70, max_attempts=3, xp_reward=60,
        achievement_code="TRAIN_ONBOARD"
    )
    ensure_questions(global_course, [
        {
            "text": "За что выдаются XP?",
            "options": [
                {"text": "За активность и результаты", "is_correct": True},
                {"text": "Только за вход в систему", "is_correct": False},
                {"text": "Исключительно за покупки в магазине", "is_correct": False},
            ],
        },
        {
            "text": "Где посмотреть текущие конкурсы?",
            "options": [
                {"text": "В разделе «Конкурсы»", "is_correct": True},
                {"text": "На главной странице браузера", "is_correct": False},
                {"text": "В письме от админа", "is_correct": False},
            ],
        },
        {
            "text": "Можно ли обменять коины на призы?",
            "options": [
                {"text": "Да, в магазине призов", "is_correct": True},
                {"text": "Нет, это только цифры", "is_correct": False},
            ],
        },
    ])

    # Корпоративный курс для ACME, создан партнёром-владельцем
    ach_acme = get_or_create_achievement("TRAIN_ACME_CALL", "Скрипт звонка ACME", 80, "uncommon", "Освой фирменный скрипт")
    company_course = get_or_create_course(
        title="Скрипт звонка ACME",
        scope="company", company=company,
        description="Фазовая структура холодного звонка для ACME.",
        content_md=(
            "## Скрипт звонка\n"
            "1) Приветствие и представление\n"
            "2) Квалификация\n"
            "3) Ценность и следующий шаг\n"
            "_Примерные формулировки и типовые возражения — внутри._"
        ),
        youtube_url=None,
        pass_score=80, max_attempts=3, xp_reward=80,
        achievement_code="TRAIN_ACME_CALL",
        created_by_partner_id=partner.id
    )
    ensure_questions(company_course, [
        {
            "text": "Что идёт после приветствия?",
            "options": [
                {"text": "Квалификация", "is_correct": True},
                {"text": "Скидка 90%", "is_correct": False},
            ],
        },
        {
            "text": "Цель первого звонка — это…",
            "options": [
                {"text": "Договориться о следующем шаге", "is_correct": True},
                {"text": "Сразу закрыть сделку", "is_correct": False},
            ],
        },
    ])
    enroll_course_for_company(company_course, company)

    # Смоделируем прогресс:
    # Alice (manager) — успешно проходит оба курса
    record_pass_attempt(manager, global_course, score=90)
    record_pass_attempt(manager, company_course, score=92)

    # Bob — сначала фейл глобального (60%), потом pass (80%), корпоративный pass
    record_fail_attempt(bob, global_course, score=60)
    record_pass_attempt(bob, global_course, score=85)
    record_pass_attempt(bob, company_course, score=88)

    # Chris — только глобальный pass
    record_pass_attempt(chris, global_course, score=75)

    # Outsider — глобальный fail один раз
    record_fail_attempt(outsider, global_course, score=40)

    db.session.commit()

    # Выводим сводку учёток/доступов
    print("\n=== ГОТОВО. Данные для входа ===")
    print(f"Админ:    {admin_email} / {admin_pass}   (панель: /admin)")
    print(f"Партнёр:  {partner_email} / {partner_pass}   (страницы: /partner/login, /partner/company, /partner/training/create)")
    print("\nПользователи компании ACME:")
    print(" - manager@acme.local / pass123   (admin компании)")
    print(" - bob@acme.local     / pass123")
    print(" - chris@acme.local   / pass123")
    print("\nВнешний пользователь:")
    print(" - outsider@demo.local / pass123 (не состоит в компании)")
    print(f"\nКомпания ACME: slug=acme  | join_code={company.join_code}")
    print("\nКурсы:")
    print(f" - [GLOBAL]  {global_course.title} (pass {global_course.pass_score}%, XP {global_course.xp_reward}, ach {global_course.achievement_code})")
    print(f" - [COMPANY] {company_course.title} (ACME) (pass {company_course.pass_score}%, XP {company_course.xp_reward}, ach {company_course.achievement_code})")
    print("\nОткрой /training — увидишь доступные курсы; менеджер увидит кнопку «Создать курс», партнёр — «Курс для сотрудников».")
