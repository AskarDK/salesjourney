# app.py
import os
import json
import uuid
from datetime import datetime, timedelta, date
from functools import wraps
from typing import Optional, Dict, Any

from flask import (
    Flask, request, jsonify, session, redirect, url_for, abort, render_template, make_response
)

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, Index, func, and_, or_, text
from werkzeug.security import generate_password_hash, check_password_hash
import pathlib, hashlib, re
import uuid, random, string
from datetime import datetime
from sqlalchemy import func
# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///sales_journey.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_change_me")
SESSION_COOKIE_NAME = "salesjourney"

app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=DATABASE_URL,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_NAME=SESSION_COOKIE_NAME,
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # в проде True (HTTPS)
)

db = SQLAlchemy(app)

ASSETS_DIR = pathlib.Path("static/avatars/layers")  # как выше в структуре

# -----------------------------------------------------------------------------
# Helpers / Auth
# -----------------------------------------------------------------------------
def require_json():
    if not request.is_json:
        abort(415, description="Content-Type must be application/json")

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return db.session.get(User, uid)

def current_admin():
    aid = session.get("admin_uid")
    if not aid:
        return None
    return db.session.get(AdminUser, aid)

def admin_required(f):
    @wraps(f)
    def w(*args, **kwargs):
        if not current_admin():
            abort(401)
        return f(*args, **kwargs)
    return w


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            abort(401)
        return f(*args, **kwargs)
    return wrapper

def login_required_page(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            # редиректим на логин и передаём next, чтобы вернуть пользователя обратно
            nxt = request.path
            return redirect(url_for("page_login") + f"?next={nxt}")
        return f(*args, **kwargs)
    return wrapper

def parse_iso_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def company_admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            abort(401)
        cm = CompanyMember.query.filter_by(user_id=user.id).first()
        if not cm or cm.role not in ("admin", "manager"):
            abort(403)
        return f(*args, **kwargs)
    return wrapper

def as_json(obj):
    return jsonify(obj)

def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default

def now_utc():
    return datetime.utcnow()

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"
    id          = db.Column(db.Integer, primary_key=True)
    email       = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password    = db.Column(db.String(255), nullable=False)
    display_name= db.Column(db.String(100), nullable=False)
    gender      = db.Column(db.String(10), nullable=True)  # male/female/other
    level       = db.Column(db.Integer, nullable=False, default=1)
    xp          = db.Column(db.Integer, nullable=False, default=0)
    coins       = db.Column(db.Integer, nullable=False, default=0)
    company_id  = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=now_utc)
    updated_at  = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    company = db.relationship("Company", back_populates="members_rel", lazy="joined")
    avatar  = db.relationship("UserAvatar", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def add_xp(self, amount: int):
        self.xp += max(0, amount)
        # простая формула уровня: 100 * level
        while self.xp >= xp_required(self.level + 1):
            self.level += 1

    def add_coins(self, amount: int):
        self.coins += max(0, amount)

def xp_required(next_level: int) -> int:
    # Линейно-экспоненциальная кривая: 100 * L^1.15 (округлим)
    return int(100 * (next_level ** 1.15))

class Company(db.Model):
    __tablename__ = "companies"
    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(255), unique=True, nullable=False)
    slug            = db.Column(db.String(64), unique=True, nullable=False)
    plan            = db.Column(db.String(32), nullable=False, default="starter")  # starter|pro|enterprise
    billing_email   = db.Column(db.String(255), nullable=True)
    created_at      = db.Column(db.DateTime, default=now_utc)

    # владелец-партнёр и код приглашения
    owner_partner_id= db.Column(db.Integer, db.ForeignKey("partner_users.id"), nullable=True)
    join_code       = db.Column(db.String(32), unique=True, nullable=True, index=True)

    members_rel = db.relationship("User", back_populates="company", lazy="select")
    members_map = db.relationship("CompanyMember", back_populates="company", cascade="all, delete-orphan")
    owner_partner   = db.relationship("PartnerUser", lazy="joined")

class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id       = db.Column(db.Integer, primary_key=True)
    email    = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # hash
    created_at = db.Column(db.DateTime, default=now_utc)


class CompanyJoinRequest(db.Model):
    __tablename__ = "company_join_requests"
    id          = db.Column(db.Integer, primary_key=True)
    company_id  = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status      = db.Column(db.String(16), nullable=False, default="pending")  # pending|approved|rejected
    created_at  = db.Column(db.DateTime, default=now_utc)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    company = db.relationship("Company", foreign_keys=[company_id], lazy="joined")
    user    = db.relationship("User", foreign_keys=[user_id], lazy="joined")

class CompanyInvite(db.Model):
    __tablename__ = "company_invites"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)  # ✅ имя таблицы как в Company
    code = db.Column(db.String(12), unique=True, nullable=False, index=True)
    token = db.Column(db.String(36), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship('Company', backref=db.backref('invites', lazy='dynamic'))

class CompanyMember(db.Model):
    __tablename__ = "company_members"
    id          = db.Column(db.Integer, primary_key=True)
    company_id  = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role        = db.Column(db.String(16), nullable=False, default="member")  # admin|manager|member
    created_at  = db.Column(db.DateTime, default=now_utc)
    __table_args__ = (UniqueConstraint('company_id','user_id', name='uq_company_user'),)

    company = db.relationship("Company", back_populates="members_map", lazy="joined")
    user    = db.relationship("User", lazy="joined")

# Ачивки и события
class Achievement(db.Model):
    __tablename__ = "achievements"
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(64), unique=True, nullable=False)
    title       = db.Column(db.String(255), nullable=False)
    points      = db.Column(db.Integer, nullable=False, default=50)  # XP
    rarity      = db.Column(db.String(16), nullable=False, default="common")
    description = db.Column(db.Text, nullable=True)

class UserAchievement(db.Model):
    __tablename__ = "user_achievements"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    achievement_id  = db.Column(db.Integer, db.ForeignKey("achievements.id"), nullable=False)
    awarded_at      = db.Column(db.DateTime, default=now_utc)
    __table_args__  = (UniqueConstraint('user_id','achievement_id', name='uq_user_achievement'),)

    user        = db.relationship("User", lazy="joined")
    achievement = db.relationship("Achievement", lazy="joined")

class ScoreEvent(db.Model):
    __tablename__ = "score_events"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source      = db.Column(db.String(32), nullable=False)  # sale|task|contest|bonus|achievement|training
    points      = db.Column(db.Integer, nullable=False, default=0)
    coins       = db.Column(db.Integer, nullable=False, default=0)
    meta_json   = db.Column(db.Text, nullable=True)  # TEXT на SQLite; JSONB на PG позже
    created_at  = db.Column(db.DateTime, default=now_utc, index=True)

    user = db.relationship("User", lazy="joined")

# --- helpers ---
def parse_json(s):
    try:
        return json.loads(s) if s else None
    except Exception:
        return None

def score_event_to_dict(ev: ScoreEvent, ach_map: Dict[str, Achievement]):
    meta = parse_json(ev.meta_json) or {}
    code = meta.get("code")
    ach_title = None
    if ev.source == "achievement" and code and code in ach_map:
        ach_title = ach_map[code].title
    return {
        "id": ev.id,
        "created_at": ev.created_at.isoformat(),
        "source": ev.source,          # sale|task|contest|bonus|achievement|training
        "points": ev.points,
        "coins": ev.coins,
        "meta": meta,
        "achievement_code": code,
        "achievement_title": ach_title,
    }

def _make_code(n=8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(random.choice(alphabet) for _ in range(n))

def generate_company_invite(company_id: int) -> CompanyInvite:
    # деактивируем старые
    CompanyInvite.query.filter_by(company_id=company_id, is_active=True).update({"is_active": False})
    # генерим уникальные code+token
    code = _make_code(8)
    while CompanyInvite.query.filter(func.upper(CompanyInvite.code) == code.upper()).first():
        code = _make_code(8)
    token = str(uuid.uuid4())
    while CompanyInvite.query.filter_by(token=token).first():
        token = str(uuid.uuid4())
    inv = CompanyInvite(company_id=company_id, code=code, token=token, is_active=True)
    db.session.add(inv)
    db.session.commit()
    return inv

def get_active_invite(company_id: int) -> CompanyInvite | None:
    return CompanyInvite.query.filter_by(company_id=company_id, is_active=True).order_by(CompanyInvite.id.desc()).first()

def join_company_by_invite(user_id: int, *, code: str | None = None, token: str | None = None):
    q = CompanyInvite.query.filter_by(is_active=True)
    if code:
        q = q.filter(func.upper(CompanyInvite.code) == code.upper())
    elif token:
        q = q.filter_by(token=token)
    else:
        return None, "NO_CODE"
    inv = q.first()
    if not inv:
        return None, "NOT_FOUND"

    # уже участник?
    link = CompanyMember.query.filter_by(user_id=user_id, company_id=inv.company_id).first()
    if link:
        # гарантируем company_id у пользователя
        u = db.session.get(User, user_id)
        if u and u.company_id != inv.company_id:
            u.company_id = inv.company_id
            db.session.commit()
        return inv.company, "ALREADY_MEMBER"

    # создаём связь + проставляем company_id у пользователя
    cm = CompanyMember(user_id=user_id, company_id=inv.company_id)
    db.session.add(cm)
    u = db.session.get(User, user_id)
    if u:
        u.company_id = inv.company_id
    db.session.commit()
    return inv.company, "JOINED"

# Аватары
class AvatarItem(db.Model):
    __tablename__ = "avatar_items"
    id          = db.Column(db.Integer, primary_key=True)
    slot        = db.Column(db.String(24), nullable=False)   # hair/outfit/acc/background/eyes/skin ...
    key         = db.Column(db.String(64), nullable=False)   # уникальный код ассета
    gender      = db.Column(db.String(10), nullable=False, default="any")  # any|male|female
    rarity      = db.Column(db.String(16), nullable=False, default="common")
    min_level   = db.Column(db.Integer, nullable=False, default=1)
    asset_url   = db.Column(db.String(512), nullable=False)  # где фронт возьмёт PNG/SVG
    __table_args__ = (UniqueConstraint('slot','key', name='uq_item_slot_key'),)

class Inventory(db.Model):
    __tablename__ = "inventory"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    item_id     = db.Column(db.Integer, db.ForeignKey("avatar_items.id"), nullable=False)
    obtained_at = db.Column(db.DateTime, default=now_utc)
    __table_args__= (UniqueConstraint('user_id','item_id', name='uq_inventory_user_item'),)

    user = db.relationship("User", lazy="joined")
    item = db.relationship("AvatarItem", lazy="joined")

class UserAvatar(db.Model):
    __tablename__ = "user_avatars"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    # Храним выбранные предметы по слотам в JSON
    selected_by_slot = db.Column(db.Text, nullable=False, default='{}')

    user = db.relationship("User", back_populates="avatar", lazy="joined")

# Конкурсы
class Contest(db.Model):
    __tablename__ = "contests"
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_at    = db.Column(db.DateTime, nullable=False)
    end_at      = db.Column(db.DateTime, nullable=False)
    prize       = db.Column(db.String(255), nullable=True)
    min_rating  = db.Column(db.Integer, nullable=True)   # минимальный уровень, например
    is_company_only = db.Column(db.Boolean, nullable=False, default=False)
    company_id  = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=now_utc)

    company = db.relationship("Company", lazy="joined")

class ContestEntry(db.Model):
    __tablename__ = "contest_entries"
    id          = db.Column(db.Integer, primary_key=True)
    contest_id  = db.Column(db.Integer, db.ForeignKey("contests.id"), nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    score       = db.Column(db.Integer, nullable=False, default=0)
    rank        = db.Column(db.Integer, nullable=True)
    status      = db.Column(db.String(16), nullable=False, default="joined")  # joined|finished
    joined_at   = db.Column(db.DateTime, default=now_utc)

    __table_args__= (UniqueConstraint('contest_id','user_id', name='uq_contest_user'),)

    contest = db.relationship("Contest", lazy="joined")
    user    = db.relationship("User", lazy="joined")

# Магазин/Партнеры
class Partner(db.Model):
    __tablename__ = "partners"
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(255), nullable=False)
    contact     = db.Column(db.String(255), nullable=True)
    webhook_url = db.Column(db.String(512), nullable=True)

class StoreItem(db.Model):
    __tablename__ = "store_items"
    id          = db.Column(db.Integer, primary_key=True)
    type        = db.Column(db.String(24), nullable=False)  # skin/coupon/merch
    title       = db.Column(db.String(255), nullable=False)
    cost_coins  = db.Column(db.Integer, nullable=False, default=0)
    stock       = db.Column(db.Integer, nullable=True)  # None=unlimited
    partner_id  = db.Column(db.Integer, db.ForeignKey("partners.id"), nullable=True)
    payload     = db.Column(db.Text, nullable=True)     # JSON для купона/метаданных
    min_level   = db.Column(db.Integer, nullable=False, default=1)
    created_at  = db.Column(db.DateTime, default=now_utc)

    partner = db.relationship("Partner", lazy="joined")

class Purchase(db.Model):
    __tablename__ = "purchases"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    store_item_id = db.Column(db.Integer, db.ForeignKey("store_items.id"), nullable=False)
    created_at  = db.Column(db.DateTime, default=now_utc)
    status      = db.Column(db.String(16), nullable=False, default="done")  # done|failed|pending
    __table_args__= (Index('ix_user_store_unique', "user_id", "store_item_id"),)

    user  = db.relationship("User", lazy="joined")
    item  = db.relationship("StoreItem", lazy="joined")

# Античит/аудит (MVP)
class AuditEvent(db.Model):
    __tablename__ = "audit_events"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type        = db.Column(db.String(32), nullable=False)  # rate_limit|duplicate|suspicious
    signal      = db.Column(db.String(64), nullable=True)
    score       = db.Column(db.Integer, nullable=False, default=0)
    notes       = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime, default=now_utc)

    user = db.relationship("User", lazy="joined")

# ------------------ Partners ------------------
class PartnerUser(db.Model):
    __tablename__ = "partner_users"
    id          = db.Column(db.Integer, primary_key=True)
    email       = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password    = db.Column(db.String(255), nullable=False)
    display_name= db.Column(db.String(100), nullable=False)
    created_at  = db.Column(db.DateTime, default=now_utc)

# ------------------ Training module ------------------
class TrainingCourse(db.Model):
    __tablename__ = "training_courses"
    id            = db.Column(db.Integer, primary_key=True)
    title         = db.Column(db.String(255), nullable=False)
    description   = db.Column(db.Text, nullable=True)
    content_md    = db.Column(db.Text, nullable=True)  # основной материал
    youtube_url   = db.Column(db.String(512), nullable=True)
    pass_score    = db.Column(db.Integer, nullable=False, default=80)  # % порог
    max_attempts  = db.Column(db.Integer, nullable=False, default=3)
    xp_reward     = db.Column(db.Integer, nullable=False, default=50)
    achievement_code = db.Column(db.String(64), nullable=True)

    scope         = db.Column(db.String(16), nullable=False, default="global")  # global|company
    company_id    = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)  # если course для конкретной компании
    created_by_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_by_partner_id = db.Column(db.Integer, db.ForeignKey("partner_users.id"), nullable=True)

    created_at    = db.Column(db.DateTime, default=now_utc)
    updated_at    = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    company       = db.relationship("Company", lazy="joined")
    partner_owner = db.relationship("PartnerUser", lazy="joined")

class TrainingQuestion(db.Model):
    __tablename__ = "training_questions"
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey("training_courses.id"), nullable=False, index=True)
    text        = db.Column(db.Text, nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    course      = db.relationship("TrainingCourse", lazy="joined")

class TrainingOption(db.Model):
    __tablename__ = "training_options"
    id          = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("training_questions.id"), nullable=False, index=True)
    text        = db.Column(db.Text, nullable=False)
    is_correct  = db.Column(db.Boolean, nullable=False, default=False)

    question    = db.relationship("TrainingQuestion", lazy="joined")

class TrainingEnrollment(db.Model):
    """
    Отмечает, кому доступен курс:
    - либо всем сотрудникам company_id (target_type='company', target_id=company_id)
    - либо конкретному user_id (target_type='user', target_id=user_id)
    """
    __tablename__ = "training_enrollments"
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey("training_courses.id"), nullable=False)
    target_type = db.Column(db.String(12), nullable=False)  # company|user
    target_id   = db.Column(db.Integer, nullable=False)
    created_at  = db.Column(db.DateTime, default=now_utc)
    __table_args__ = (Index('ix_course_target_unique', "course_id", "target_type", "target_id", unique=True),)

    course      = db.relationship("TrainingCourse", lazy="joined")


# --- Partner company dashboard: feed & tasks ---

class CompanyFeedPost(db.Model):
    __tablename__ = "company_feed_posts"
    id          = db.Column(db.Integer, primary_key=True)
    company_id  = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    author_type = db.Column(db.String(16), nullable=False, default="partner")  # partner|manager
    author_name = db.Column(db.String(100), nullable=False)
    text        = db.Column(db.Text, nullable=False)
    pinned      = db.Column(db.Boolean, nullable=False, default=False)
    created_at  = db.Column(db.DateTime, default=now_utc)
    image_url   = db.Column(db.String(255), nullable=True)  # <<< новое поле

    company = db.relationship("Company", lazy="joined")

class CompanyTask(db.Model):
    __tablename__ = "company_tasks"
    id          = db.Column(db.Integer, primary_key=True)
    company_id  = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    title       = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    points_xp   = db.Column(db.Integer, nullable=False, default=20)
    coins       = db.Column(db.Integer, nullable=False, default=5)
    due_at      = db.Column(db.DateTime, nullable=True)
    is_active   = db.Column(db.Boolean, nullable=False, default=True)

    # НОВОЕ:
    priority    = db.Column(db.String(16), nullable=False, default="normal")  # low|normal|high|critical
    require_proof = db.Column(db.Boolean, nullable=False, default=True)
    reward_achievement_id = db.Column(db.Integer, db.ForeignKey("achievements.id"), nullable=True)
    reward_item_payload   = db.Column(db.Text, nullable=True)  # JSON: {"slot":"frame", "key":"frame_gold", "auto_equip":true}

    created_by_partner_id = db.Column(db.Integer, db.ForeignKey("partner_users.id"), nullable=True)
    created_by_user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=now_utc)

    company = db.relationship("Company", lazy="joined")
    partner = db.relationship("PartnerUser", lazy="joined")
    creator_user = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

class CompanyTaskAssign(db.Model):
    __tablename__ = "company_task_assigns"
    id          = db.Column(db.Integer, primary_key=True)
    task_id     = db.Column(db.Integer, db.ForeignKey("company_tasks.id"), nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # НОВОЕ: статусы для процесса с отчётом и модерацией
    status      = db.Column(db.String(16), nullable=False, default="assigned")  # assigned|submitted|approved|rejected
    submitted_at= db.Column(db.DateTime, nullable=True)
    completed_at= db.Column(db.DateTime, nullable=True)

    __table_args__ = (UniqueConstraint('task_id','user_id', name='uq_task_user'),)

    task = db.relationship("CompanyTask", lazy="joined")
    user = db.relationship("User", lazy="joined")

class Notification(db.Model):
    __tablename__ = "notifications"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey("partner_users.id"), nullable=True, index=True)
    type       = db.Column(db.String(32), nullable=False, default="system")  # task_assigned|task_due|task_submitted|task_result|system
    title      = db.Column(db.String(255), nullable=False)
    body       = db.Column(db.Text, nullable=True)
    data_json  = db.Column(db.Text, nullable=True)  # произвольный payload
    is_read    = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=now_utc)

class CompanyTaskSubmission(db.Model):
    __tablename__ = "company_task_submissions"
    id          = db.Column(db.Integer, primary_key=True)
    assign_id   = db.Column(db.Integer, db.ForeignKey("company_task_assigns.id"), nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    task_id     = db.Column(db.Integer, db.ForeignKey("company_tasks.id"), nullable=False, index=True)
    image_url   = db.Column(db.String(255), nullable=False)
    comment     = db.Column(db.Text, nullable=True)
    submitted_at= db.Column(db.DateTime, default=now_utc)


class TrainingAttempt(db.Model):
    __tablename__ = "training_attempts"
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey("training_courses.id"), nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    score       = db.Column(db.Integer, nullable=False, default=0)  # %
    passed      = db.Column(db.Boolean, nullable=False, default=False)
    created_at  = db.Column(db.DateTime, default=now_utc)
    answers_json= db.Column(db.Text, nullable=True)  # {"question_id": option_id, ...}

    course      = db.relationship("TrainingCourse", lazy="joined")
    user        = db.relationship("User", lazy="joined")

# -----------------------------------------------------------------------------
# DB bootstrap
# -----------------------------------------------------------------------------
with app.app_context():
    db.create_all()

    def _migrate_db():
        try: db.session.execute(text('ALTER TABLE company_tasks ADD COLUMN priority VARCHAR(16) DEFAULT "normal"'))
        except Exception: pass
        try: db.session.execute(text('ALTER TABLE company_tasks ADD COLUMN require_proof BOOLEAN DEFAULT 1'))
        except Exception: pass
        try: db.session.execute(text('ALTER TABLE company_tasks ADD COLUMN reward_achievement_id INTEGER'))
        except Exception: pass
        try: db.session.execute(text('ALTER TABLE company_tasks ADD COLUMN reward_item_payload TEXT'))
        except Exception: pass
        try: db.session.execute(text('ALTER TABLE company_task_assigns ADD COLUMN submitted_at DATETIME'))
        except Exception: pass
        try: db.session.execute(text('ALTER TABLE company_task_assigns RENAME COLUMN status TO status'))
        except Exception: pass
        try: db.session.execute(text('UPDATE company_task_assigns SET status="assigned" WHERE status NOT IN ("submitted","approved","rejected")'))
        except Exception: pass
        try: db.session.execute(text('ALTER TABLE company_feed_posts ADD COLUMN image_url VARCHAR(255)'))   # <<< добавлено
        except Exception: pass
        db.session.commit()
    _migrate_db()


    if not AdminUser.query.filter_by(email="admin@salesjourney.local").first():
        db.session.add(AdminUser(
            email="admin@salesjourney.local",
            password=generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin123"))
        ))
        db.session.commit()


    # seed начальных ачивок/предметов/магазина (один раз)
    if not Achievement.query.first():
        db.session.add_all([
            Achievement(code="WELCOME", title="Первое знакомство", points=50, rarity="common",
                        description="Заверши регистрацию"),
            Achievement(code="PROFILE_100", title="Полный профиль", points=100, rarity="uncommon",
                        description="Заполни профиль на 100%"),
        ])
    if not AvatarItem.query.first():
        db.session.add_all([
            AvatarItem(slot="base", key="base_t1", gender="any", rarity="common", min_level=1,
                       asset_url="/assets/avatars/base/base_t1.png"),
            AvatarItem(slot="hair", key="hair_short_v1", gender="male", rarity="common", min_level=1,
                       asset_url="/assets/avatars/male/hair/hair_short_v1.png"),
            AvatarItem(slot="hair", key="hair_long_v1", gender="female", rarity="common", min_level=1,
                       asset_url="/assets/avatars/female/hair/hair_long_v1.png"),
            AvatarItem(slot="outfit", key="outfit_lvl1_common", gender="any", rarity="common", min_level=1,
                       asset_url="/assets/avatars/common/outfit_lvl1_common.png"),
        ])
    if not StoreItem.query.first():
        db.session.add_all([
            StoreItem(type="skin", title="Редкий плащ", cost_coins=200, stock=100, min_level=3),
            StoreItem(type="coupon", title="Сертификат $10", cost_coins=500, stock=50,
                      payload=json.dumps({"provider":"GiftCo"}), min_level=5),
        ])
    db.session.commit()

    # Попытка мягкой миграции для существующих баз: добавим недостающие колонки (SQLite допускает)
    with db.engine.connect() as con:
        try:
            con.execute(text("ALTER TABLE companies ADD COLUMN join_code VARCHAR(32)"))
        except Exception:
            pass
        try:
            con.execute(text("ALTER TABLE companies ADD COLUMN owner_partner_id INTEGER"))
        except Exception:
            pass
        try:
            con.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_join_code ON companies (join_code)"))
        except Exception:
            pass

    # Дополнительные предметы + заполнение join_code
    if not StoreItem.query.filter_by(title="Золотая рамка").first():
        db.session.add_all([
            StoreItem(
                type="skin",
                title="Золотая рамка",
                cost_coins=150,
                stock=50,
                min_level=1,
                payload=json.dumps({"slot":"frame","key":"frame_gold","auto_equip":True})
            ),
            StoreItem(
                type="skin",
                title="Костюм Торговца",
                cost_coins=200,
                stock=30,
                min_level=3,
                payload=json.dumps({"slot":"outfit","key":"lvl_5_trader","auto_equip":True})
            ),
            StoreItem(
                type="skin",
                title="Стрижка Fade",
                cost_coins=120,
                stock=40,
                min_level=1,
                payload=json.dumps({"slot":"hair","key":"male_short_v2","gender":"male","auto_equip":True})
            ),
        ])
        db.session.commit()

    # Проставить коды приглашений компаниям, где пусто
    for c in Company.query.filter(or_(Company.join_code.is_(None), Company.join_code == "")).all():
        c.join_code = uuid.uuid4().hex[:8].upper()
    db.session.commit()

# -----------------------------------------------------------------------------
# Serializers
# -----------------------------------------------------------------------------
def user_to_dict(u: User) -> Dict[str, Any]:
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
        "gender": u.gender,
        "level": u.level,
        "xp": u.xp,
        "xp_next": xp_required(u.level + 1),
        "coins": u.coins,
        "company": u.company.slug if u.company else None,
        "created_at": u.created_at.isoformat(),
    }

def partner_to_dict(p: "PartnerUser") -> dict:
    return {"id": p.id, "email": p.email, "display_name": p.display_name, "created_at": p.created_at.isoformat()}

def company_public_to_dict(c: "Company") -> dict:
    return {
        "id": c.id, "name": c.name, "slug": c.slug, "plan": c.plan,
        "join_code": c.join_code, "owner_partner_id": c.owner_partner_id
    }

def course_to_dict(c: "TrainingCourse", with_questions=False) -> dict:
    data = {
        "id": c.id, "title": c.title, "description": c.description,
        "content_md": c.content_md, "youtube_url": c.youtube_url,
        "pass_score": c.pass_score, "max_attempts": c.max_attempts,
        "xp_reward": c.xp_reward, "achievement_code": c.achievement_code,
        "scope": c.scope, "company_id": c.company_id,
        "created_by_admin": c.created_by_admin,
        "created_by_partner_id": c.created_by_partner_id,
        "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()
    }
    if with_questions:
        qs = TrainingQuestion.query.filter_by(course_id=c.id).order_by(TrainingQuestion.order_index.asc()).all()
        data["questions"] = [
            {
                "id": q.id, "text": q.text, "order_index": q.order_index,
                "options": [{"id": o.id, "text": o.text} for o in TrainingOption.query.filter_by(question_id=q.id).all()]
            } for q in qs
        ]
    return data

def attempt_to_dict(a: "TrainingAttempt") -> dict:
    return {
        "id": a.id, "course_id": a.course_id, "user_id": a.user_id,
        "score": a.score, "passed": a.passed, "created_at": a.created_at.isoformat()
    }

def avatar_item_to_dict(i: AvatarItem) -> Dict[str, Any]:
    return {
        "id": i.id, "slot": i.slot, "key": i.key, "gender": i.gender,
        "rarity": i.rarity, "min_level": i.min_level, "asset_url": i.asset_url
    }

def user_avatar_to_dict(ua: UserAvatar) -> Dict[str, Any]:
    selected = {}
    try:
        selected = json.loads(ua.selected_by_slot or "{}")
    except Exception:
        selected = {}
    return {"user_id": ua.user_id, "selected_by_slot": selected}

def contest_to_dict(c: Contest) -> Dict[str, Any]:
    return {
        "id": c.id, "title": c.title, "description": c.description,
        "start_at": c.start_at.isoformat(), "end_at": c.end_at.isoformat(),
        "prize": c.prize, "min_rating": c.min_rating,
        "is_company_only": c.is_company_only,
        "company": c.company.slug if c.company else None
    }

def contest_entry_to_dict(e: ContestEntry) -> Dict[str, Any]:
    return {
        "contest_id": e.contest_id, "user_id": e.user_id, "score": e.score,
        "rank": e.rank, "status": e.status, "joined_at": e.joined_at.isoformat()
    }

def store_item_to_dict(s: StoreItem) -> Dict[str, Any]:
    payload = None
    try:
        payload = json.loads(s.payload) if s.payload else None
    except Exception:
        payload = None
    return {
        "id": s.id, "type": s.type, "title": s.title, "cost_coins": s.cost_coins,
        "stock": s.stock, "min_level": s.min_level, "partner": s.partner.name if s.partner else None,
        "payload": payload
    }

def achievement_to_dict(a: Achievement) -> Dict[str, Any]:
    return {
        "id": a.id, "code": a.code, "title": a.title,
        "points": a.points, "rarity": a.rarity, "description": a.description
    }

# -------- Partner auth helpers ----------

def _partner_owns_company_or_403(company_id: int):
    p = current_partner()
    if not p:
        abort(401)
    c = db.session.get(Company, company_id)
    if not c:
        abort(404)
    if c.owner_partner_id != p.id:
        abort(403)
    return c

def _manager_of_company_or_403(company_id: int):
    user = current_user()
    if not user:
        abort(401)
    cm = CompanyMember.query.filter_by(company_id=company_id, user_id=user.id).first()
    if not cm or cm.role not in ("admin", "manager"):
        abort(403)
    return True


def current_partner():
    pid = session.get("partner_uid")
    if not pid:
        return None
    return db.session.get(PartnerUser, pid)

def partner_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_partner():
            abort(401)
        return f(*args, **kwargs)
    return wrapper

def company_manager_or_admin_required(f):
    """
    Доступ дают: партнёр-владелец ИЛИ user-админ/менеджер ИМЕННО этой компании.
    company_id берём из path-параметра, query или JSON.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        # 1) достаём company_id для ЛЮБОГО типа запроса (включая multipart)
        cid = safe_int(
            request.args.get("company_id")
            or ((request.get_json() or {}).get("company_id") if request.is_json else None)
            or (kwargs.get("company_id") if "company_id" in kwargs else None),
            0
        )
        if cid <= 0:
            abort(400, description="company_id required")
        c = db.session.get(Company, cid)
        if not c:
            abort(404, description="Company not found")

        # 2) партнёр-владелец
        p = current_partner()
        if p:
            if c.owner_partner_id != p.id:
                abort(403)
            return f(*args, **kwargs)

        # 3) руководитель (admin/manager) этой компании
        u = current_user()
        if u:
            cm = CompanyMember.query.filter_by(company_id=cid, user_id=u.id).first()
            if cm and cm.role in ("admin", "manager"):
                return f(*args, **kwargs)
            abort(403)

        # 4) никто не залогинен
        abort(401)
    return wrapper

# -----------------------------------------------------------------------------
# Auth / Onboarding
# -----------------------------------------------------------------------------
@app.post("/api/auth/register")
def register():
    require_json()
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip()
    gender = data.get("gender")

    if not email or not password or not display_name:
        abort(400, description="email, password, display_name required")

    if User.query.filter_by(email=email).first():
        abort(409, description="Email already registered")

    session.clear()  # чистая сессия
    user = User(
        email=email,
        password=generate_password_hash(password),
        display_name=display_name,
        gender=gender,
    )
    db.session.add(user)
    db.session.flush()
    auto_join_company_from_request(request, user)  # <— ВСТАВИТЬ ЭТУ СТРОКУ

    # Инициализируем аватар
    base = AvatarItem.query.filter_by(slot="base", key="base_t1").first()
    ua = UserAvatar(user_id=user.id, selected_by_slot=json.dumps({"base": base.key if base else "base_t1"}))
    db.session.add(ua)

    # Приветственная ачивка + XP
    ach = Achievement.query.filter_by(code="WELCOME").first()
    if ach:
        db.session.add(UserAchievement(user_id=user.id, achievement_id=ach.id))
        user.add_xp(ach.points)

    db.session.commit()
    session["uid"] = user.id
    return as_json({"user": user_to_dict(user)})

# ---- JSON error responses (чтобы фронт всегда понимал ошибку) ----
from werkzeug.exceptions import HTTPException

def auto_join_company_from_request(req, user):
    # 1) токен из URL, формы или JSON
    token = (req.args.get("invite") or "").strip()
    if not token:
        token = (req.form.get("invite") or req.form.get("invite_token") or "").strip()
    if not token and req.is_json:
        try:
            j = (req.get_json(silent=True) or {})
            token = (j.get("invite") or j.get("invite_token") or "").strip()
        except Exception:
            token = ""

    # 2) код из формы или JSON
    code = (req.form.get("company_code") or "").strip()
    if not code and req.is_json:
        try:
            j = (req.get_json(silent=True) or {})
            code = (j.get("company_code") or j.get("code") or "").strip()
        except Exception:
            code = ""

    if token:
        join_company_by_invite(user.id, token=token)
    elif code:
        join_company_by_invite(user.id, code=code)

def _sync_user_company(u: "User"):
    if not u:
        return
    if u.company_id:
        return
    cm = CompanyMember.query.filter_by(user_id=u.id).first()
    if cm and cm.company_id:
        u.company_id = cm.company_id
        db.session.commit()


@app.errorhandler(HTTPException)
def handle_http_error(e: HTTPException):
    response = {
        "error": e.name,
        "description": e.description,
        "status": e.code,
    }
    return jsonify(response), e.code

@app.errorhandler(Exception)
def handle_unexpected_error(e: Exception):
    app.logger.exception(e)
    return jsonify({"error": "Internal Server Error", "description": "Unexpected error", "status": 500}), 500

@app.post("/api/auth/login")
def login():
    require_json()
    session.clear()  # СБРОС сессии перед логином (фиксация, смешивание ролей)
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        abort(401, description="Invalid credentials")
    session.pop("partner_uid", None)  # гарантированно не партнёр
    session["uid"] = user.id
    _sync_user_company(user)  # <<< доп. защита от рассинхрона
    return as_json({"user": user_to_dict(user)})


@app.post("/api/auth/logout")
@login_required
def logout():
    session.clear()
    return as_json({"ok": True})

@app.get("/api/me")
@login_required
def me():
    return as_json({"user": user_to_dict(current_user())})

# -----------------------------------------------------------------------------
# Avatar / Inventory
# -----------------------------------------------------------------------------
@app.get("/api/avatar/items")
@login_required
def list_avatar_items():
    u = current_user()
    items = AvatarItem.query.filter(or_(AvatarItem.gender=="any", AvatarItem.gender==u.gender)).all()
    # фильтруем по уровню
    items = [i for i in items if i.min_level <= u.level]
    return as_json({"items": [avatar_item_to_dict(i) for i in items]})

@app.get("/api/avatar/my")
@login_required
def get_my_avatar():
    u = current_user()
    if not u.avatar:
        ua = UserAvatar(user_id=u.id, selected_by_slot="{}")
        db.session.add(ua)
        db.session.commit()
    return as_json({"avatar": user_avatar_to_dict(u.avatar)})

@app.post("/api/avatar/select")
@login_required
def select_avatar_items():
    require_json()
    u = current_user()
    data = request.get_json()
    selected = data.get("selected_by_slot") or {}
    # Валидация: существование предметов, доступность по уровню и полу
    for slot, key in selected.items():
        item = AvatarItem.query.filter_by(slot=slot, key=key).first()
        if not item:
            abort(400, description=f"Item not found for slot={slot}, key={key}")
        if item.min_level > u.level:
            abort(403, description=f"Item requires level {item.min_level}")
        if item.gender not in ("any", u.gender or "any"):
            abort(403, description=f"Item not allowed for gender={u.gender}")
    if not u.avatar:
        u.avatar = UserAvatar(user_id=u.id, selected_by_slot=json.dumps(selected))
    else:
        current_sel = {}
        try:
            current_sel = json.loads(u.avatar.selected_by_slot or "{}")
        except Exception:
            current_sel = {}
        current_sel.update(selected)
        u.avatar.selected_by_slot = json.dumps(current_sel)
    db.session.commit()
    return as_json({"avatar": user_avatar_to_dict(u.avatar)})

# Выдать предмет в инвентарь (теперь только админ/менеджер компании)
@app.post("/api/avatar/grant")
@login_required
def grant_item():
    require_json()
    u = current_user()
    cm = CompanyMember.query.filter_by(user_id=u.id).first()
    if not cm or cm.role not in ("admin", "manager"):
        abort(403, description="Only company admin/manager may grant items")

    data = request.get_json()
    item_id = data.get("item_id")
    item = db.session.get(AvatarItem, item_id)
    if not item:
        abort(404, description="Item not found")
    inv = Inventory(user_id=u.id, item_id=item.id)
    db.session.add(inv)
    db.session.commit()
    return as_json({"granted": avatar_item_to_dict(item)})

# -----------------------------------------------------------------------------
# Achievements / Score Events
# -----------------------------------------------------------------------------
@app.get("/api/achievements")
@login_required
def list_achievements():
    ach = Achievement.query.all()
    return as_json({"achievements": [achievement_to_dict(a) for a in ach]})

@app.post("/api/achievements/claim")
@login_required
def claim_achievement():
    require_json()
    u = current_user()
    code = (request.json.get("code") or "").strip()
    ach = Achievement.query.filter_by(code=code).first()
    if not ach:
        abort(404, description="Achievement not found")
    if UserAchievement.query.filter_by(user_id=u.id, achievement_id=ach.id).first():
        return as_json({"ok": True, "already": True})
    db.session.add(UserAchievement(user_id=u.id, achievement_id=ach.id))
    u.add_xp(ach.points)
    ev = ScoreEvent(user_id=u.id, source="achievement", points=ach.points, coins=0, meta_json=json.dumps({"code":code}))
    db.session.add(ev)
    db.session.commit()
    return as_json({"ok": True, "user": user_to_dict(u)})

@app.post("/api/events/score")
@login_required
def post_score_event():
    """
    payload:
    {
      "source": "sale|task|contest|bonus",
      "points": 20,
      "coins": 5,
      "meta": {...}
    }
    Мини-античит: рейтовый лимит по источнику: не более 10 событий за 10 минут.
    """
    require_json()
    u = current_user()
    data = request.get_json()
    source = (data.get("source") or "bonus").strip()
    points = safe_int(data.get("points"), 0)
    coins  = safe_int(data.get("coins"), 0)
    meta   = data.get("meta") or {}

    ten_min_ago = now_utc() - timedelta(minutes=10)
    recent_count = ScoreEvent.query.filter(
        ScoreEvent.user_id==u.id,
        ScoreEvent.source==source,
        ScoreEvent.created_at>=ten_min_ago
    ).count()
    if recent_count >= 10:
        db.session.add(AuditEvent(user_id=u.id, type="rate_limit", signal=source,
                                  score=1, notes="Too many events in 10 minutes"))
        db.session.commit()
        abort(429, description="Rate limit reached for this source")

    ev = ScoreEvent(
        user_id=u.id, source=source, points=max(0, points), coins=max(0, coins),
        meta_json=json.dumps(meta)
    )
    db.session.add(ev)
    u.add_xp(points)
    u.add_coins(coins)
    db.session.commit()
    return as_json({"ok": True, "user": user_to_dict(u)})

# -----------------------------------------------------------------------------
# Contests
# -----------------------------------------------------------------------------
@app.get("/api/contests")
@login_required
def list_contests():
    u = current_user()
    q = Contest.query
    q = q.filter(
        or_(
            Contest.is_company_only.is_(False),
            and_(Contest.is_company_only.is_(True), Contest.company_id==u.company_id)
        )
    )
    items = q.order_by(Contest.start_at.desc()).all()
    return as_json({"contests": [contest_to_dict(c) for c in items]})

@app.get("/api/contests/<int:contest_id>")
@login_required
def get_contest(contest_id):
    c = db.session.get(Contest, contest_id)
    if not c:
        abort(404)
    return as_json({"contest": contest_to_dict(c)})

@app.post("/api/contests/<int:contest_id>/join")
@login_required
def join_contest(contest_id):
    u = current_user()
    c = db.session.get(Contest, contest_id)
    if not c:
        abort(404)
    if c.min_rating and u.level < c.min_rating:
        abort(403, description="Level is too low for this contest")
    if c.is_company_only and u.company_id != c.company_id:
        abort(403, description="Company-only contest")
    if ContestEntry.query.filter_by(contest_id=c.id, user_id=u.id).first():
        return as_json({"ok": True, "already": True})
    entry = ContestEntry(contest_id=c.id, user_id=u.id)
    db.session.add(entry)
    db.session.commit()
    return as_json({"ok": True, "entry": contest_entry_to_dict(entry)})

@app.get("/api/contests/<int:contest_id>/leaderboard")
@login_required
def contest_leaderboard(contest_id):
    entries = (ContestEntry.query
               .filter_by(contest_id=contest_id)
               .order_by(ContestEntry.score.desc(), ContestEntry.joined_at.asc())
               .limit(100).all())
    data = []
    rank = 0
    last_score = None
    for e in entries:
        if e.score != last_score:
            rank += 1
            last_score = e.score
        data.append({
            "user": {"id": e.user.id, "display_name": e.user.display_name, "level": e.user.level},
            "score": e.score, "rank": rank
        })
    return as_json({"leaderboard": data})

@app.post("/api/contests/<int:contest_id>/add_score")
@login_required
def contest_add_score(contest_id):
    require_json()
    u = current_user()
    e = ContestEntry.query.filter_by(contest_id=contest_id, user_id=u.id).first()
    if not e:
        abort(403, description="Join first")
    delta = safe_int(request.json.get("score_delta"), 0)
    e.score += max(0, delta)
    db.session.commit()
    return as_json({"ok": True, "entry": contest_entry_to_dict(e)})

# -----------------------------------------------------------------------------
# Store (coins)
# -----------------------------------------------------------------------------
@app.get("/api/store")
@login_required
def store_list():
    u = current_user()
    items = StoreItem.query.order_by(StoreItem.created_at.desc()).all()
    out = []
    for i in items:
        d = store_item_to_dict(i)
        d["locked"] = i.min_level > u.level
        d["lock_reason"] = None if not d["locked"] else f"Требуется уровень {i.min_level}"
        out.append(d)
    return as_json({"items": out})

# -----------------------------------------------------------------------------
# Company (B2B) — простейшие endpoints
# -----------------------------------------------------------------------------
@app.post("/api/company/create")
@login_required
def company_create():
    """
    Создаёт компанию и делает текущего пользователя admin.
    payload: { "name": "...", "slug": "..." }
    """
    require_json()
    u = current_user()
    name = (request.json.get("name") or "").strip()
    slug = (request.json.get("slug") or "").strip().lower()
    if not name or not slug:
        abort(400, description="name, slug required")
    if Company.query.filter(or_(Company.name==name, Company.slug==slug)).first():
        abort(409, description="Company exists")
    c = Company(name=name, slug=slug)
    db.session.add(c)
    db.session.flush()
    u.company_id = c.id
    cm = CompanyMember(company_id=c.id, user_id=u.id, role="admin")
    db.session.add(cm)
    db.session.commit()
    return as_json({"company": {"id": c.id, "name": c.name, "slug": c.slug, "plan": c.plan}})

@app.get("/api/company/dashboard")
@company_admin_required
def company_dashboard():
    u = current_user()
    cid = u.company_id
    if not cid:
        abort(404, description="No company")
    members = User.query.filter_by(company_id=cid).all()
    total_members = len(members)
    avg_level = 0 if total_members==0 else round(sum(m.level for m in members)/total_members, 2)
    top_xp = sorted([{"id":m.id,"display_name":m.display_name,"xp":m.xp,"level":m.level} for m in members],
                    key=lambda x: x["xp"], reverse=True)[:10]
    week_ago = now_utc() - timedelta(days=7)
    events_count = ScoreEvent.query.join(User, ScoreEvent.user_id==User.id)\
        .filter(User.company_id==cid, ScoreEvent.created_at>=week_ago).count()
    now = now_utc()
    contests = Contest.query.filter(
        or_(
            and_(Contest.is_company_only.is_(True), Contest.company_id==cid),
            Contest.is_company_only.is_(False)
        ),
        Contest.end_at>=now
    ).order_by(Contest.start_at.desc()).all()

    return as_json({
        "company": u.company.slug if u.company else None,
        "kpi": {
            "members": total_members,
            "avg_level": avg_level,
            "events_7d": events_count
        },
        "top_xp": top_xp,
        "contests": [contest_to_dict(c) for c in contests]
    })

@app.post("/api/company/contest")
@company_admin_required
def company_create_contest():
    """
    payload: {
      "title": "...", "description": "...",
      "start_at": "2025-08-12T00:00:00Z",
      "end_at": "2025-09-12T00:00:00Z",
      "prize": "...", "min_rating": 2,
      "company_only": true
    }
    """
    require_json()
    u = current_user()
    data = request.get_json()
    try:
        c = Contest(
            title=data["title"],
            description=data.get("description"),
            start_at=datetime.fromisoformat(data["start_at"].replace("Z","+00:00")),
            end_at=datetime.fromisoformat(data["end_at"].replace("Z","+00:00")),
            prize=data.get("prize"),
            min_rating=safe_int(data.get("min_rating"), None),
            is_company_only=bool(data.get("company_only")),
            company_id=u.company_id if data.get("company_only") else None
        )
    except KeyError:
        abort(400, description="title, start_at, end_at required")
    db.session.add(c)
    db.session.commit()
    return as_json({"contest": contest_to_dict(c)})

# -----------------------------------------------------------------------------
# Public Landing placeholder (чтобы не было 404)
# -----------------------------------------------------------------------------
@app.get("/")
def landing():
    return render_template("index.html")

@app.get("/login")
def page_login():
    if session.get("uid"):
        return redirect(url_for("page_achievements"))
    return render_template("login.html")

@app.get("/register")
def page_register():
    if session.get("uid"):
        return redirect(url_for("page_achievements"))
    return render_template("register.html")

@app.get("/achievements")
@login_required_page
def page_achievements():
    u = current_user()
    all_ach = Achievement.query.order_by(Achievement.points.desc()).all()
    owned = UserAchievement.query.filter_by(user_id=u.id).all()
    owned_codes = {a.achievement.code for a in owned}
    return render_template(
        "achievements.html",
        user=u,
        user_next_xp=xp_required(u.level+1),
        achievements=all_ach,
        owned_codes=owned_codes
    )

# --- NEW: XP/coins timeline (события) ---
@app.get("/api/user/xp_history")
@login_required
def api_xp_history():
    u = current_user()
    events = (ScoreEvent.query
              .filter_by(user_id=u.id)
              .order_by(ScoreEvent.created_at.desc())
              .limit(500).all())
    codes = [ (parse_json(e.meta_json) or {}).get("code") for e in events if e.source == "achievement" ]
    codes = [c for c in codes if c]
    ach_map = {a.code: a for a in Achievement.query.filter(Achievement.code.in_(codes)).all()} if codes else {}
    return as_json({"events": [score_event_to_dict(e, ach_map) for e in events]})

# --- NEW: история полученных ачивок ---
@app.get("/api/user/achievements/history")
@login_required
def api_achievements_history():
    u = current_user()
    items = (UserAchievement.query
             .filter_by(user_id=u.id)
             .order_by(UserAchievement.awarded_at.desc()).all())
    data = []
    for ua in items:
        a = ua.achievement
        data.append({
            "code": a.code,
            "title": a.title,
            "points": a.points,
            "rarity": a.rarity,
            "awarded_at": ua.awarded_at.isoformat()
        })
    return as_json({"achievements": data})

# --- Jinja helpers in templates ---
@app.context_processor
def inject_helpers():
    u = current_user()
    p = current_partner()

    def j_is_company_manager(company_id: int) -> bool:
        if not u or not company_id:
            return False
        cm = CompanyMember.query.filter_by(company_id=company_id, user_id=u.id).first()
        return bool(cm and cm.role in ("admin", "manager"))

    def j_partner_has_company() -> bool:
        if not p:
            return False
        return Company.query.filter_by(owner_partner_id=p.id).first() is not None

    def j_is_admin() -> bool:
        # Админка у тебя на отдельной сессии admin_uid
        return current_admin() is not None

    # важно отдавать актуальные объекты current_user/current_partner
    return {
        "current_user": u,
        "current_partner": p,
        "is_manager": j_is_company_manager,
        "partner_has_company": j_partner_has_company,
        "is_admin": j_is_admin,
    "current_admin": current_admin(),  # <<< ДОБАВЬ ЭТО

    }

# --- SVG-аватар на лету ---
def render_avatar_svg(gender: str = "any", display_name: str = "") -> str:
    male = (gender or "").lower() == "male"
    skin = "#F2C6A0"
    hair = "#2C2C2C" if male else "#5C3B2E"
    bg   = "#0F172A"  # slate-900
    shirt= "#6366F1" if male else "#F472B6"  # индиго / розовый
    eyes = "#1F2937"
    hair_path = (
        '<path d="M60 52 q40 -26 80 0 v18 q-60 22 -120 0z" fill="{hair}" opacity="0.95"/>'
        if male else
        '<path d="M40 60 q50 -38 120 0 v40 q-40 28 -120 0z" fill="{hair}" opacity="0.95"/>'
    ).format(hair=hair)
    initials = (display_name[:1] or "").upper()
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">
  <defs>
    <clipPath id="clip"><circle cx="80" cy="80" r="76"/></clipPath>
  </defs>
  <rect width="160" height="160" rx="24" fill="{bg}"/>
  <g clip-path="url(#clip)">
    <rect width="160" height="160" fill="{bg}"/>
    {hair_path}
    <circle cx="80" cy="78" r="38" fill="{skin}"/>
    <circle cx="65" cy="78" r="5" fill="{eyes}"/><circle cx="95" cy="78" r="5" fill="{eyes}"/>
    <path d="M55 118 q25 12 50 0 v25 H55z" fill="{shirt}"/>
  </g>
  <circle cx="130" cy="126" r="18" fill="#10B981"/>
  <text x="130" y="131" text-anchor="middle" font-size="16" font-family="Inter,Segoe UI,Arial" fill="white">{initials}</text>
</svg>'''

def compose_avatar_head_svg(user: "User") -> str:
    seed = _hash_int(f"user:{user.id}")
    gender = (user.gender or "any").lower()
    base_key = "head_any_v1"
    hair_key = _gender_hair_key(gender, seed)
    base = _read_fragment("base", base_key)
    hair = _read_fragment("hair", hair_key)
    W = 320
    H = 320
    RADIUS   = 125
    CENTER_X = 160
    CENTER_Y = 160
    OFFSET_Y = -220
    OFFSET_X = -240
    SCALE    = 2.5
    skin = _skin_fill_from_seed(seed)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" 
        viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">
  <defs>
    <clipPath id="clip-head">
      <circle cx="{CENTER_X}" cy="{CENTER_Y}" r="{RADIUS}"/>
    </clipPath>
  </defs>
  <g clip-path="url(#clip-head)" transform="translate({OFFSET_X},{OFFSET_Y}) scale({SCALE})">
    <style>.skin {{ fill: {skin}; }}</style>
    {base}
    {hair}
  </g>
  <circle cx="{CENTER_X}" cy="{CENTER_Y}" r="{RADIUS-2}" 
    fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="3"/>
</svg>"""

def render_avatar_svg_base(gender: str = "any", display_name: str = "") -> str:
    male = (gender or "").lower() == "male"
    skin = "#F2C6A0"
    hair = "#2C2C2C" if male else "#5C3B2E"
    bg   = "#0F172A"
    shirt= "#6366F1" if male else "#F472B6"
    eyes = "#1F2937"
    hair_path = (
        '<path d="M60 52 q40 -26 80 0 v18 q-60 22 -120 0z" fill="{hair}" opacity="0.95"/>'
        if male else
        '<path d="M40 60 q50 -38 120 0 v40 q-40 28 -120 0z" fill="{hair}" opacity="0.95"/>'
    ).format(hair=hair)
    initials = (display_name[:1] or "").upper()
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">
  <rect width="160" height="160" rx="24" fill="{bg}"/>
  {hair_path}
  <circle cx="80" cy="78" r="38" fill="{skin}"/>
  <circle cx="65" cy="78" r="5" fill="{eyes}"/><circle cx="95" cy="78" r="5" fill="{eyes}"/>
  <path d="M55 118 q25 12 50 0 v25 H55z" fill="{shirt}"/>
  <circle cx="130" cy="126" r="18" fill="#10B981"/>
  <text x="130" y="131" text-anchor="middle" font-size="16" font-family="Inter,Segoe UI,Arial" fill="white">{initials}</text>
</svg>'''

@app.get("/avatar_svg/<int:user_id>")
def avatar_svg(user_id):
    u = db.session.get(User, user_id)
    if not u:
        return "not found", 404
    part = (request.args.get("part") or "").lower()
    preview = request.args.get("preview_level", type=int)
    try:
        if part == "head":
            svg = compose_avatar_head_svg(u)
        else:
            svg = compose_avatar_svg(u, preview_level=preview)
            if not svg or "<svg" not in svg:
                svg = render_avatar_svg_base(u.gender or "any", u.display_name or "")
    except Exception:
        svg = render_avatar_svg_base(u.gender or "any", u.display_name or "")
    resp = make_response(svg)
    resp.headers["Content-Type"] = "image/svg+xml"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

# --- простая страница профиля
@app.get("/profile")
def profile_page():
    u = current_user()
    if not u: return redirect(url_for("landing"))
    return render_template("profile.html", user=u, user_next_xp=xp_required(u.level+1))

def _read_fragment(slot: str, key: str) -> str:
    p = ASSETS_DIR / slot / f"{key}.svg"
    if not p.exists():
        return ""
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"</?svg[^>]*>", "", s, flags=re.IGNORECASE)
    return s.strip()

def _hash_int(v: str) -> int:
    return int(hashlib.sha1(v.encode("utf-8")).hexdigest(), 16)

def _gender_hair_key(gender: str, seed: int) -> str:
    male_keys   = ["male_short_v1", "male_short_v2"]
    female_keys = ["female_long_v1", "female_ponytail_v1"]
    if (gender or "").lower() == "female":
        return female_keys[seed % len(female_keys)]
    elif (gender or "").lower() == "male":
        return male_keys[seed % len(male_keys)]
    return male_keys[seed % len(male_keys)]

def _level_preset(level: int) -> dict:
    if level >= 20:
        return dict(outfit="lvl_20_lord", accessory="crown_gold", frame="frame_gold", background="rays_purple")
    if level >= 10:
        return dict(outfit="lvl_10_knight", accessory="medal_silver", frame="frame_silver", background="rays_purple")
    if level >= 5:
        return dict(outfit="lvl_5_trader", accessory="medal_bronze", frame="frame_silver", background="rays_blue")
    return dict(outfit="lvl_1_peasant", accessory="none", frame="frame_wood", background="plain_dark")

def _skin_fill_from_seed(seed: int) -> str:
    palette = ["#F2C6A0", "#E8B894", "#DDAA85", "#C98E66", "#B6784F"]
    return palette[seed % len(palette)]

def compose_avatar_svg(user: "User", preview_level: int | None = None) -> str:
    level = preview_level if preview_level is not None else user.level
    seed = _hash_int(f"user:{user.id}")
    gender = (user.gender or "any").lower()
    lp = _level_preset(level)
    slots = {
        "background": lp["background"],
        "base": "head_any_v1",
        "hair": _gender_hair_key(gender, seed),
        "outfit": lp["outfit"],
        "accessory": lp["accessory"],
        "frame": lp["frame"],
    }
    selected = _json_or_empty(user.avatar.selected_by_slot if user.avatar else "{}")
    for s, k in selected.items():
        if _user_owns_item(user.id, s, k):
            slots[s] = k
    background = _read_fragment("background", slots["background"])
    base = _read_fragment("base", slots["base"])
    hair = _read_fragment("hair", slots["hair"])
    outfit = _read_fragment("outfit", slots["outfit"])
    accessory = _read_fragment("accessory", slots["accessory"])
    frame = _read_fragment("frame", slots["frame"])
    W = 320
    H = 320
    skin = _skin_fill_from_seed(seed)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <style>
    .skin {{ fill: {skin}; }}
  </style>
  <defs></defs>
  <g id="bg">{background}</g>
  <g id="base">{base}</g>
  <g id="hair">{hair}</g>
  <g id="outfit">{outfit}</g>
  <g id="acc">{accessory}</g>
  <g id="frame">{frame}</g>
</svg>"""
    return svg

# ---------- Pages: Store / Contests / Company Dashboard ----------
@app.get("/store")
@login_required_page
def page_store():
    return render_template("store.html")

@app.get("/contests")
@login_required_page
def page_contests():
    return render_template("contests.html")

@app.get("/contest/<int:contest_id>")
@login_required_page
def page_contest(contest_id):
    return render_template("contest.html", contest_id=contest_id)

@app.get("/company/dashboard")
@login_required_page
def page_company_dashboard():
    return render_template("company_dashboard.html")

def _json_or_empty(s):
    try:
        return json.loads(s) if s else {}
    except Exception:
        return {}

def _user_owns_item(user_id: int, slot: str, key: str) -> bool:
    item = AvatarItem.query.filter_by(slot=slot, key=key).first()
    if not item:
        return False
    return Inventory.query.filter_by(user_id=user_id, item_id=item.id).first() is not None

def _grant_inventory(user_id: int, slot: str, key: str, gender: str = "any", min_level: int = 1, asset_url: str = ""):
    item = AvatarItem.query.filter_by(slot=slot, key=key).first()
    if not item:
        if not asset_url:
            asset_url = f"/static/avatars/layers/{slot}/{key}.svg"
        item = AvatarItem(slot=slot, key=key, gender=gender or "any", min_level=min_level, asset_url=asset_url)
        db.session.add(item)
        db.session.flush()
    if not Inventory.query.filter_by(user_id=user_id, item_id=item.id).first():
        inv = Inventory(user_id=user_id, item_id=item.id)
        db.session.add(inv)
    return item

def _equip_selected(user: "User", slot: str, key: str):
    if not _user_owns_item(user.id, slot, key):
        abort(403, description="You don't own this cosmetic item")
    sel = _json_or_empty(user.avatar.selected_by_slot if user.avatar else "{}")
    sel[slot] = key
    if not user.avatar:
        user.avatar = UserAvatar(user_id=user.id, selected_by_slot=json.dumps(sel))
    else:
        user.avatar.selected_by_slot = json.dumps(sel)

@app.get("/api/avatar/inventory")
@login_required
def api_avatar_inventory():
    u = current_user()
    rows = (db.session.query(Inventory, AvatarItem)
            .join(AvatarItem, Inventory.item_id == AvatarItem.id)
            .filter(Inventory.user_id == u.id)
            .all())
    items = []
    for inv, item in rows:
        items.append({
            "slot": item.slot,
            "key": item.key,
            "gender": item.gender,
            "rarity": item.rarity,
            "min_level": item.min_level,
        })
    return as_json({"items": items})

@app.post("/api/avatar/equip")
@login_required
def api_avatar_equip():
    """
    payload: { "slot": "frame|outfit|hair|...", "key": "frame_gold" }
    """
    require_json()
    u = current_user()
    slot = (request.json.get("slot") or "").strip()
    key  = (request.json.get("key") or "").strip()
    if not slot or not key:
        abort(400, description="slot, key required")
    _equip_selected(u, slot, key)
    u.updated_at = now_utc()  # чтобы обновлялся t=<timestamp> в navbar
    db.session.commit()
    return as_json({"ok": True, "selected_by_slot": _json_or_empty(u.avatar.selected_by_slot)})

@app.post("/api/store/buy/<int:item_id>")
@login_required
def store_buy(item_id):
    u = current_user()
    item = db.session.get(StoreItem, item_id)
    if not item:
        abort(404)
    if item.min_level > u.level:
        abort(403, description="Level too low")
    if item.stock is not None and item.stock <= 0:
        abort(409, description="Out of stock")
    if u.coins < item.cost_coins:
        abort(400, description="Not enough coins")

    u.coins -= item.cost_coins
    if item.stock is not None:
        item.stock -= 1
    p = Purchase(user_id=u.id, store_item_id=item.id, status="done")
    db.session.add(p)

    payload = _json_or_empty(item.payload)
    slot = payload.get("slot")
    key  = payload.get("key")
    gender = payload.get("gender", "any")
    min_lvl = int(payload.get("min_level", item.min_level or 1))
    auto_equip = bool(payload.get("auto_equip", True))

    if item.type == "skin" and slot and key:
        _grant_inventory(u.id, slot, key, gender=gender, min_level=min_lvl)
        if auto_equip:
            _equip_selected(u, slot, key)

    u.updated_at = now_utc()
    db.session.commit()
    return as_json({"ok": True, "purchase_id": p.id, "user": user_to_dict(u)})

# ---------------- Partner auth ----------------
@app.post("/api/partners/auth/register")
def partner_register():
    require_json()
    d = request.get_json()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    display_name = (d.get("display_name") or "").strip()
    if not email or not password or not display_name:
        abort(400, description="email, password, display_name required")
    if PartnerUser.query.filter_by(email=email).first():
        abort(409, description="Email already registered")
    session.pop("uid", None)  # на всякий случай, чтобы не смешивать
    p = PartnerUser(email=email, password=generate_password_hash(password), display_name=display_name)
    db.session.add(p)
    db.session.commit()
    session["partner_uid"] = p.id
    return as_json({"partner": partner_to_dict(p)})

@app.post("/api/partners/auth/login")
def partner_login():
    require_json()
    d = request.get_json()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    p = PartnerUser.query.filter_by(email=email).first()
    if not p or not check_password_hash(p.password, password):
        abort(401, description="Invalid credentials")
    session.pop("uid", None)          # не можем быть и юзером, и партнёром
    session["partner_uid"] = p.id
    return as_json({"partner": partner_to_dict(p)})

@app.post("/api/partners/auth/logout")
def partner_logout():
    session.pop("partner_uid", None)
    return as_json({"ok": True})

# --- совместимость и «на всякий случай» ---
@app.route("/api/partner/logout", methods=["POST", "GET"])
def partner_logout_alias():
    # тот же эффект, что и у основного выхода партнёра
    session.pop("partner_uid", None)
    return as_json({"ok": True})

@app.get("/api/partners/me")
@partner_required
def partner_me():
    return as_json({"partner": partner_to_dict(current_partner())})

# Создание компании партнёром
@app.post("/api/partners/company/create")
@partner_required
def partner_company_create():
    require_json()
    p = current_partner()
    name = (request.json.get("name") or "").strip()
    slug = (request.json.get("slug") or "").strip().lower()
    if not name or not slug:
        abort(400, description="name, slug required")
    if Company.query.filter(or_(Company.name==name, Company.slug==slug)).first():
        abort(409, description="Company exists")
    c = Company(name=name, slug=slug, owner_partner_id=p.id, join_code=uuid.uuid4().hex[:8].upper())
    db.session.add(c)
    db.session.commit()
    return as_json({"company": company_public_to_dict(c)})

# Обновить/перегенерировать join_code (партнёр-владелец)
@app.post("/api/partners/company/<int:company_id>/regen_code")
@partner_required
def partner_company_regen_code(company_id):
    p = current_partner()
    c = db.session.get(Company, company_id)
    if not c: abort(404)
    if c.owner_partner_id != p.id: abort(403)
    c.join_code = uuid.uuid4().hex[:8].upper()
    db.session.commit()
    return as_json({"company": company_public_to_dict(c)})

@app.post("/api/company/join/request")
@login_required
def company_join_request():
    require_json()
    u = current_user()
    code = (request.json.get("code") or "").strip().upper()
    if not code: abort(400, description="code required")
    c = Company.query.filter_by(join_code=code).first()
    if not c: abort(404, description="Company not found by code")

    # уже в компании?
    if u.company_id == c.id or CompanyMember.query.filter_by(company_id=c.id, user_id=u.id).first():
        return as_json({"ok": True, "already_member": True, "company": company_public_to_dict(c)})

    # <<< НОВОЕ: одна активная заявка на пользователя
    exists_any = CompanyJoinRequest.query.filter_by(user_id=u.id, status="pending").first()
    if exists_any and exists_any.company_id != c.id:
        return as_json({
            "ok": False,
            "pending_exists": True,
            "company": company_public_to_dict(exists_any.company)
        }), 409

    # заявка в ту же компанию уже есть
    exists = CompanyJoinRequest.query.filter_by(user_id=u.id, company_id=c.id, status="pending").first()
    if exists:
        return as_json({"ok": True, "request_id": exists.id, "status": "pending", "company": company_public_to_dict(c)})

    r = CompanyJoinRequest(user_id=u.id, company_id=c.id, status="pending")
    db.session.add(r)
    db.session.commit()
    return as_json({"ok": True, "request_id": r.id, "status": r.status, "company": company_public_to_dict(c)})

@app.get("/api/company/join/status")
@login_required
def company_join_status():
    u = current_user()
    if u.company_id:
        c = db.session.get(Company, u.company_id)
        return as_json({"member": True, "pending": False, "company": company_public_to_dict(c)})

    r = (CompanyJoinRequest.query
         .filter_by(user_id=u.id, status="pending")
         .order_by(CompanyJoinRequest.created_at.desc())
         .first())
    if r:
        return as_json({"member": False, "pending": True, "company": company_public_to_dict(r.company)})

    return as_json({"member": False, "pending": False})

@app.post("/api/company/join")
@login_required
def company_join():
    require_json()
    u = current_user()
    code = (request.json.get("code") or "").strip().upper()
    if not code: abort(400, description="code required")
    c = Company.query.filter_by(join_code=code).first()
    if not c: abort(404, description="Company not found by code")

    if u.company_id == c.id or CompanyMember.query.filter_by(company_id=c.id, user_id=u.id).first():
        return as_json({"ok": True, "already_member": True, "member": True, "company": company_public_to_dict(c)})

    exists_any = CompanyJoinRequest.query.filter_by(user_id=u.id, status="pending").first()
    if exists_any and exists_any.company_id != c.id:
        return as_json({
            "ok": False,
            "pending_exists": True,
            "company": company_public_to_dict(exists_any.company)
        }), 409

    exists = CompanyJoinRequest.query.filter_by(user_id=u.id, company_id=c.id, status="pending").first()
    if exists:
        return as_json({"ok": True, "request_id": exists.id, "status": "pending", "pending": True, "company": company_public_to_dict(c)})

    r = CompanyJoinRequest(user_id=u.id, company_id=c.id, status="pending")
    db.session.add(r); db.session.commit()
    return as_json({"ok": True, "request_id": r.id, "status": r.status, "pending": True, "company": company_public_to_dict(c)})

@app.post("/api/company/join/cancel")
@login_required
def company_join_cancel():
    u = current_user()
    r = (CompanyJoinRequest.query
         .filter_by(user_id=u.id, status="pending")
         .order_by(CompanyJoinRequest.created_at.desc())
         .first())
    if not r:
        return as_json({"ok": True, "already": True})
    db.session.delete(r)
    db.session.commit()
    return as_json({"ok": True})

# Апрув/реджект (менеджер компании или партнёр-владелец)
@app.post("/api/company/join/approve/<int:req_id>")
@company_manager_or_admin_required
def approve_company_join_request(req_id):
    r = db.session.get(CompanyJoinRequest, req_id)
    if not r or r.status != "pending":
        abort(404, description="Request not found/pending")
    u = r.user
    u.company_id = r.company_id
    if not CompanyMember.query.filter_by(user_id=u.id, company_id=r.company_id).first():
        db.session.add(CompanyMember(company_id=r.company_id, user_id=u.id, role="member"))
    r.status = "approved"
    r.reviewed_at = now_utc()
    db.session.commit()
    return as_json({"ok": True})

@app.post("/api/company/join/reject/<int:req_id>")
@company_manager_or_admin_required
def reject_company_join_request(req_id):
    r = db.session.get(CompanyJoinRequest, req_id)
    if not r or r.status != "pending":
        abort(404, description="Request not found/pending")
    r.status = "rejected"
    r.reviewed_at = now_utc()
    db.session.commit()
    return as_json({"ok": True})

# Список pending-заявок для компании (только менеджер/админ)
def _is_company_manager(company_id: int) -> bool:
    u = current_user()
    if not u: return False
    cm = CompanyMember.query.filter_by(company_id=company_id, user_id=u.id).first()
    return bool(cm and cm.role in ("admin","manager"))

@app.get("/api/company/join/requests")
@login_required
def api_company_join_requests():
    company_id = safe_int(request.args.get("company_id"))
    if not company_id or not _is_company_manager(company_id):
        abort(403)
    rows = (CompanyJoinRequest.query
            .filter_by(company_id=company_id, status="pending")
            .order_by(CompanyJoinRequest.created_at.asc()).all())
    out = [{"id": r.id, "user": {"id": r.user.id, "email": r.user.email, "display_name": r.user.display_name}} for r in rows]
    return as_json({"requests": out})

# --------- TRAINING: list/details for a user ---------
@app.get("/api/training/courses")
@login_required
def list_training_courses():
    u = current_user()
    q = TrainingCourse.query
    items = []
    for c in q.order_by(TrainingCourse.created_at.desc()).all():
        visible = False
        if c.scope == "global":
            visible = True
        if u.company_id and c.scope == "company" and c.company_id == u.company_id:
            visible = True
        if not visible and u.company_id:
            if TrainingEnrollment.query.filter_by(course_id=c.id, target_type="company", target_id=u.company_id).first():
                visible = True
        if not visible:
            if TrainingEnrollment.query.filter_by(course_id=c.id, target_type="user", target_id=u.id).first():
                visible = True
        if visible:
            items.append(c)
    return as_json({"courses": [course_to_dict(c, with_questions=False) for c in items]})

@app.get("/api/training/courses/<int:course_id>")
@login_required
def get_training_course(course_id):
    u = current_user()
    c = db.session.get(TrainingCourse, course_id)
    if not c: abort(404)
    allowed = False
    if c.scope == "global":
        allowed = True
    if u.company_id and c.scope == "company" and c.company_id == u.company_id:
        allowed = True
    if not allowed and u.company_id and TrainingEnrollment.query.filter_by(course_id=c.id, target_type="company", target_id=u.company_id).first():
        allowed = True
    if not allowed and TrainingEnrollment.query.filter_by(course_id=c.id, target_type="user", target_id=u.id).first():
        allowed = True
    if not allowed: abort(403)
    return as_json({"course": course_to_dict(c, with_questions=True)})

# --------- TRAINING: create (admin or partner company owner) ---------
@app.post("/api/training/courses")
def create_training_course():
    """
    Создаёт курс:
    - админ (через твою админку) -> scope='global', created_by_admin=True
    - партнёр-владелец -> scope='company', company_id обязателен, created_by_partner_id
    - менеджер компании (user) -> scope='company', company_id = его компании
    """
    require_json()
    d = request.get_json()
    title = (d.get("title") or "").strip()
    if not title: abort(400, description="title required")

    p = current_partner()
    u = current_user()

    scope = (d.get("scope") or "").strip() or ("company" if (p or u) else "global")
    if scope not in ("global","company"):
        abort(400, description="scope must be global|company")

    company_id = d.get("company_id")

    c = TrainingCourse(
        title=title,
        description=d.get("description"),
        content_md=d.get("content_md"),
        youtube_url=d.get("youtube_url"),
        pass_score=safe_int(d.get("pass_score"), 80),
        max_attempts=safe_int(d.get("max_attempts"), 3),
        xp_reward=safe_int(d.get("xp_reward"), 50),
        achievement_code=(d.get("achievement_code") or "").strip() or None,
        scope=scope
    )

    if p:
        if scope != "company": abort(403, description="Partners can create only company-scoped courses")
        cid = safe_int(company_id, 0)
        comp = db.session.get(Company, cid)
        if not comp or comp.owner_partner_id != p.id:
            abort(403, description="Not your company")
        c.company_id = comp.id
        c.created_by_partner_id = p.id
    elif u:
        cm = CompanyMember.query.filter_by(user_id=u.id).first()
        if not cm or cm.role not in ("admin","manager"):
            abort(403)
        if scope == "global":
            abort(403, description="Only admins can create global courses")
        c.company_id = cm.company_id
    else:
        abort(401)

    db.session.add(c)
    db.session.flush()

    for idx, q in enumerate(d.get("questions") or []):
        tq = TrainingQuestion(course_id=c.id, text=q.get("text","").strip(), order_index=idx)
        db.session.add(tq)
        db.session.flush()
        for opt in (q.get("options") or []):
            db.session.add(TrainingOption(
                question_id=tq.id,
                text=(opt.get("text") or "").strip(),
                is_correct=bool(opt.get("is_correct", False))
            ))
    db.session.commit()
    return as_json({"course": course_to_dict(c, with_questions=True)})

# Назначить курс
@app.post("/api/training/courses/<int:course_id>/assign")
@company_manager_or_admin_required
def assign_training_course(course_id):
    require_json()
    c = db.session.get(TrainingCourse, course_id)
    if not c: abort(404)

    d = request.get_json()
    target_type = (d.get("target_type") or "").strip()  # company|user
    if target_type not in ("company","user"):
        abort(400, description="target_type must be company|user")
    target_ids = d.get("target_ids") or []
    if not isinstance(target_ids, list) or not target_ids:
        abort(400, description="target_ids required")

    created = []
    for tid in target_ids:
        tid_int = safe_int(tid, 0)
        if tid_int <= 0: continue
        if not TrainingEnrollment.query.filter_by(course_id=c.id, target_type=target_type, target_id=tid_int).first():
            e = TrainingEnrollment(course_id=c.id, target_type=target_type, target_id=tid_int)
            db.session.add(e)
            created.append(tid_int)
    db.session.commit()
    return as_json({"ok": True, "created_for": created})

# Старт попытки
@app.post("/api/training/courses/<int:course_id>/start")
@login_required
def start_training_attempt(course_id):
    u = current_user()
    c = db.session.get(TrainingCourse, course_id)
    if not c: abort(404)

    allowed = False
    if c.scope == "global": allowed = True
    if u.company_id and c.scope == "company" and c.company_id == u.company_id: allowed = True
    if not allowed and u.company_id and TrainingEnrollment.query.filter_by(course_id=c.id, target_type="company", target_id=u.company_id).first(): allowed = True
    if not allowed and TrainingEnrollment.query.filter_by(course_id=c.id, target_type="user", target_id=u.id).first(): allowed = True
    if not allowed: abort(403)

    attempts = TrainingAttempt.query.filter_by(course_id=c.id, user_id=u.id).count()
    if attempts >= c.max_attempts:
        abort(429, description="Max attempts reached")
    return as_json({"ok": True, "attempts_used": attempts, "attempts_left": c.max_attempts - attempts})

# Сабмит квиза
@app.post("/api/training/courses/<int:course_id>/submit_quiz")
@login_required
def submit_training_quiz(course_id):
    require_json()
    u = current_user()
    c = db.session.get(TrainingCourse, course_id)
    if not c: abort(404)

    allowed = False
    if c.scope == "global": allowed = True
    if u.company_id and c.scope == "company" and c.company_id == u.company_id: allowed = True
    if not allowed and u.company_id and TrainingEnrollment.query.filter_by(course_id=c.id, target_type="company", target_id=u.company_id).first(): allowed = True
    if not allowed and TrainingEnrollment.query.filter_by(course_id=c.id, target_type="user", target_id=u.id).first(): allowed = True
    if not allowed: abort(403)

    attempts = TrainingAttempt.query.filter_by(course_id=c.id, user_id=u.id).count()
    if attempts >= c.max_attempts:
        abort(429, description="Max attempts reached")

    d = request.get_json()
    answers = d.get("answers") or []
    qlist = TrainingQuestion.query.filter_by(course_id=c.id).all()
    qmap = {q.id: q for q in qlist}
    correct = 0
    total = len(qlist) if qlist else 1
    chosen = {}
    for a in answers:
        qid = safe_int(a.get("question_id"), 0)
        oid = safe_int(a.get("option_id"), 0)
        if qid in qmap:
            chosen[qid] = oid
            opt = db.session.get(TrainingOption, oid)
            if opt and opt.question_id == qid and opt.is_correct:
                correct += 1
    score = int(round(100.0 * correct / max(1, total)))
    passed = score >= c.pass_score

    att = TrainingAttempt(course_id=c.id, user_id=u.id, score=score, passed=passed, answers_json=json.dumps(chosen))
    db.session.add(att)

    if passed:
        u.add_xp(max(0, c.xp_reward))
        db.session.add(ScoreEvent(
            user_id=u.id, source="training",
            points=max(0, c.xp_reward), coins=0,
            meta_json=json.dumps({"course_id": c.id, "title": c.title, "score": score})
        ))
        if c.achievement_code:
            ach = Achievement.query.filter_by(code=c.achievement_code).first()
            if ach and not UserAchievement.query.filter_by(user_id=u.id, achievement_id=ach.id).first():
                db.session.add(UserAchievement(user_id=u.id, achievement_id=ach.id))
                u.add_xp(ach.points)
                db.session.add(ScoreEvent(
                    user_id=u.id, source="achievement", points=ach.points, coins=0,
                    meta_json=json.dumps({"code": c.achievement_code})
                ))

    db.session.commit()
    return as_json({"attempt": attempt_to_dict(att), "passed": passed, "score": score})

# Прогресс пользователя по курсам
@app.get("/api/training/progress")
@login_required
def training_progress():
    u = current_user()
    atts = TrainingAttempt.query.filter_by(user_id=u.id).order_by(TrainingAttempt.created_at.desc()).all()
    return as_json({"attempts": [attempt_to_dict(a) for a in atts]})

# Статистика по компании (для руководителя/партнёра)
@app.get("/api/company/training/stats")
@company_manager_or_admin_required
def company_training_stats():
    cid = safe_int(request.args.get("company_id"), 0)
    if not cid: abort(400, description="company_id required")

    users = User.query.filter_by(company_id=cid).all()
    uids = [u.id for u in users]
    rows = TrainingAttempt.query.filter(TrainingAttempt.user_id.in_(uids)).all()

    by_user = {}
    for a in rows:
        by_user.setdefault(a.user_id, {"user": {"id": a.user_id, "display_name": a.user.display_name}, "total":0, "passed":0, "avg_score":0})
        rec = by_user[a.user_id]
        rec["total"] += 1
        rec["passed"] += 1 if a.passed else 0
        rec.setdefault("_scores", []).append(a.score)

    for rec in by_user.values():
        sc = rec.pop("_scores", [])
        rec["avg_score"] = round(sum(sc)/len(sc), 1) if sc else 0.0

    return as_json({"stats": list(by_user.values())})

# ------------ PAGES ------------
@app.get("/training")
@login_required_page
def page_training_list():
    return render_template("training_list.html")

@app.get("/training/<int:course_id>")
@login_required_page
def page_training_course(course_id):
    return render_template("training_course.html", course_id=course_id)

@app.get("/partner/login")
def page_partner_login():
    return render_template("partner_login.html")

@app.get("/partner/company")
def page_partner_company():
    # 1) партнёр-владелец: как и раньше
    p = current_partner()
    if p:
        comp = Company.query.filter_by(owner_partner_id=p.id).order_by(Company.id.asc()).first()
        if comp:
            return render_template("partner_company.html", company_id=comp.id, company_slug=comp.slug)
        # 🔽 фоллбэк: если партнёр без своей компании, но текущий пользователь состоит в компании — показываем её
        u = current_user()
        if u:
            if not u.company_id:
                _sync_user_company(u)  # <<< подтянем company_id из company_members при необходимости
            if u.company_id:
                c = db.session.get(Company, u.company_id)
                if c:
                    return render_template("partner_company.html", company_id=c.id, company_slug=c.slug)
        # не залогинен или без компании — показываем пустую страницу
        return render_template("partner_company.html", company_id=None, company_slug=None)

    # 2) обычный пользователь: показываем его компанию (если состоит), иначе заглушку
    u = current_user()
    if u and u.company_id:
        c = db.session.get(Company, u.company_id)
        if c:
            return render_template("partner_company.html", company_id=c.id, company_slug=c.slug)

    # не залогинен или без компании — показываем пустую страницу
    return render_template("partner_company.html", company_id=None, company_slug=None)

@app.get("/company/requests")
@login_required_page
def page_company_requests():
    return render_template("company_requests.html")

@app.get("/company/training/stats")
@login_required_page
def page_company_training_stats():
    return render_template("company_training_stats.html")

@app.get("/api/partners/company/<int:company_id>/dashboard")
def api_partner_company_dashboard(company_id):
    """
    Доступ: партнёр-владелец ИЛИ любой участник компании.
    Возвращает: KPI, топ-10 по XP за 30 дней, лента,
    задачи:
      - партнёр/админ/менеджер видят все активные;
      - обычный сотрудник — только назначенные ему.
    Доп. поля по задачам: is_due_passed, submittable (для сотрудника).
    """
    c = db.session.get(Company, company_id)
    if not c: abort(404)

    partner = current_partner()
    user = current_user()

    is_partner = bool(partner and c.owner_partner_id == partner.id)
    user_role = None
    if user and user.company_id == company_id:
        cm = CompanyMember.query.filter_by(company_id=company_id, user_id=user.id).first()
        user_role = (cm.role if cm else None)

    # теперь допускаем любого участника компании
    if not (is_partner or user_role):
        abort(403)

    # KPI
    members = User.query.filter_by(company_id=company_id).all()
    total_members = len(members)
    avg_level = 0 if total_members==0 else round(sum(m.level for m in members)/total_members, 2)
    last30 = now_utc() - timedelta(days=30)
    events_30d = ScoreEvent.query.join(User, ScoreEvent.user_id==User.id)\
                    .filter(User.company_id==company_id, ScoreEvent.created_at>=last30).count()

    # лидерборд 30д
    lb_rows = (db.session.query(User.id, User.display_name, func.sum(ScoreEvent.points).label("xp30"))
               .join(ScoreEvent, ScoreEvent.user_id==User.id)
               .filter(User.company_id==company_id, ScoreEvent.created_at>=last30)
               .group_by(User.id, User.display_name)
               .order_by(func.sum(ScoreEvent.points).desc())
               .limit(10).all())
    leaderboard = [{"user_id": r.id, "display_name": r.display_name, "xp_30d": int(r.xp30 or 0)} for r in lb_rows]

    # лента
    feed = (CompanyFeedPost.query.filter_by(company_id=company_id)
            .order_by(CompanyFeedPost.pinned.desc(), CompanyFeedPost.created_at.desc())
            .limit(20).all())
    can_manage = bool(is_partner or user_role in ("admin", "manager"))

    # лента с картинкой
    feed_out = [{
        "id": f.id,
        "author": f.author_name,
        "type": f.author_type,
        "text": f.text,
        "pinned": f.pinned,
        "created_at": f.created_at.isoformat(),
        "image_url": f.image_url  # <<< добавили
    } for f in feed]

    # задачи
    now = now_utc()
    tasks_out = []

    if is_partner or user_role in ("admin", "manager"):
        tasks = (CompanyTask.query
                 .filter_by(company_id=company_id, is_active=True)
                 .order_by(CompanyTask.created_at.desc()).all())
        for t in tasks:
            tasks_out.append({
                "id": t.id, "title": t.title, "description": t.description,
                "points_xp": t.points_xp, "coins": t.coins,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "priority": t.priority, "require_proof": t.require_proof,
                "reward_achievement_id": t.reward_achievement_id,
                "is_due_passed": bool(t.due_at and now >= t.due_at),
            })
    else:
        # обычный сотрудник — только назначенные ему
        rows = (db.session.query(CompanyTask, CompanyTaskAssign)
                .join(CompanyTaskAssign, CompanyTaskAssign.task_id == CompanyTask.id)
                .filter(CompanyTask.company_id == company_id,
                        CompanyTask.is_active.is_(True),
                        CompanyTaskAssign.user_id == user.id)
                .order_by(CompanyTask.created_at.desc())
                .all())
        for t, a in rows:
            is_due_passed = bool(t.due_at and now >= t.due_at)
            submittable = bool(t.require_proof and is_due_passed and a.status in ("assigned", "rejected"))
            tasks_out.append({
                "id": t.id, "title": t.title, "description": t.description,
                "points_xp": t.points_xp, "coins": t.coins,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "priority": t.priority, "require_proof": t.require_proof,
                "reward_achievement_id": t.reward_achievement_id,
                "assign_status": a.status,
                "is_due_passed": is_due_passed,
                "submittable": submittable,
            })

    return as_json({
        "company": company_public_to_dict(c),
        "kpi": {"members": total_members, "avg_level": avg_level, "events_30d": events_30d},
        "leaderboard": leaderboard,
        "feed": feed_out,
        "tasks": tasks_out,
        # <<< новый блок прав — чтобы фронт знал, показывать ли кнопки создания
        "permissions": {
            "is_partner": is_partner,
            "role": user_role,  # admin|manager|member|None
            "can_manage": can_manage,  # true -> показываем создание/редактирование
            "can_create_feed": can_manage,
            "can_create_tasks": can_manage
        }
    })

@app.post("/api/partners/company/<int:company_id>/feed")
@company_manager_or_admin_required
def api_partner_company_feed_create(company_id):
    # допускаем и партнёра, и менеджера (декоратор уже проверил права)
    c = db.session.get(Company, company_id)
    if not c: abort(404)

    # читаем данные из JSON или из multipart/form-data
    if request.is_json:
        d = request.get_json() or {}
        text = (d.get("text") or "").strip()
        pinned_raw = d.get("pinned", False)
    else:
        text = (request.form.get("text") or "").strip()
        pinned_raw = request.form.get("pinned", "0")

    def _is_true(v):
        return str(v).strip().lower() in ("1","true","yes","on")

    pinned = _is_true(pinned_raw)

    # файл (опционально)
    file = request.files.get("photo")
    image_url = None
    if file:
        up_dir = pathlib.Path(app.root_path) / "static" / "uploads" / "feed"
        up_dir.mkdir(parents=True, exist_ok=True)
        ext = (pathlib.Path(file.filename).suffix or ".jpg")[:10]
        fname = f"{uuid.uuid4().hex}{ext}"
        file.save(up_dir / fname)
        image_url = f"/static/uploads/feed/{fname}"

    # разрешаем пост без текста, если есть картинка
    if not text and not image_url:
        abort(400, description="text or image required")

    p = current_partner()
    u = current_user()
    author_type = "partner" if p else "manager"
    author_name = (p.display_name if p else (u.display_name if u else "System"))

    post = CompanyFeedPost(
        company_id=c.id,
        author_type=author_type,
        author_name=author_name,
        text=text or "",
        pinned=pinned,
        image_url=image_url
    )
    db.session.add(post); db.session.commit()
    return as_json({"post_id": post.id, "image_url": post.image_url})

@app.post("/api/partners/company/<int:company_id>/tasks")
def api_partner_company_task_create(company_id):
    """
    Создать задачу может: партнёр-владелец ИЛИ менеджер компании (user).
    """
    c = db.session.get(Company, company_id)
    if not c: abort(404)
    p = current_partner()
    u = current_user()
    if not p and not u: abort(401)
    if p:
        if c.owner_partner_id != p.id: abort(403)
    else:
        _manager_of_company_or_403(company_id)

    require_json()
    d = request.get_json()
    title = (d.get("title") or "").strip()
    if not title: abort(400, description="title required")
    due_at = None
    if d.get("due_at"):
        try:
            due_at = datetime.fromisoformat(d["due_at"].replace("Z","+00:00"))
        except Exception:
            pass
    task = CompanyTask(
        company_id=c.id, title=title, description=d.get("description"),
        points_xp=safe_int(d.get("points_xp"), 20),
        coins=safe_int(d.get("coins"), 5),
        due_at=due_at, is_active=True,
        priority=(d.get("priority") or "normal"),
        require_proof=bool(d.get("require_proof", True)),
        reward_achievement_id=safe_int(d.get("reward_achievement_id"), None),
        reward_item_payload=json.dumps(d.get("reward_item_payload")) if d.get("reward_item_payload") else None,
        created_by_partner_id=p.id if p else None,
        created_by_user_id=u.id if u else None
    )

    db.session.add(task); db.session.commit()
    return as_json({"task_id": task.id})

@app.post("/api/partners/company/<int:company_id>/tasks/<int:task_id>/assign")
@company_manager_or_admin_required
def api_partner_task_assign(company_id, task_id):
    t = db.session.get(CompanyTask, task_id)
    if not t or t.company_id != company_id:
        abort(404)

    data = request.get_json() or {}
    ids = list({safe_int(i, 0) for i in (data.get("user_ids") or []) if safe_int(i, 0) > 0})
    replace = bool(data.get("replace"))

    # оставляем только сотрудников этой компании
    valid_ids = {u.id for u in User.query.filter(User.company_id == company_id, User.id.in_(ids)).all()}

    if replace:
        CompanyTaskAssign.query.filter_by(task_id=task_id).delete()
        db.session.flush()

    existing = {a.user_id for a in CompanyTaskAssign.query.filter_by(task_id=task_id).all()}
    for uid in valid_ids:
        if uid not in existing:
            db.session.add(CompanyTaskAssign(task_id=task_id, user_id=uid, status="assigned"))

    db.session.commit()
    return as_json({"ok": True, "count": len(valid_ids)})

@app.post("/api/company/tasks/<int:task_id>/complete")
@login_required
def api_company_task_complete(task_id):
    u = current_user()
    a = CompanyTaskAssign.query.filter_by(task_id=task_id, user_id=u.id).first()
    if not a: abort(404)
    t = a.task
    # Если по задаче требуется отчёт — просим загрузить его через /submit
    if t.require_proof:
        abort(400, description="По этой задаче требуется отправить отчёт с фото. Используйте /api/company/tasks/<id>/submit.")
    # Иначе — старое поведение: зачесть сразу
    if a.status in ("approved","done"):
        return as_json({"ok": True, "already": True})
    a.status = "approved"
    a.completed_at = now_utc()
    u.add_xp(max(0, t.points_xp))
    u.add_coins(max(0, t.coins))
    db.session.add(ScoreEvent(
        user_id=u.id, source="task", points=t.points_xp, coins=t.coins,
        meta_json=json.dumps({"task_id": t.id, "title": t.title})
    ))
    # Уведомление пользователю о зачёте
    db.session.add(Notification(
        user_id=u.id, type="task_result",
        title="Задача зачтена", body=t.title,
        data_json=json.dumps({"task_id": t.id})
    ))
    db.session.commit()
    return as_json({"ok": True, "user": user_to_dict(u)})

@app.get("/api/partners/company/<int:company_id>/members")
@company_manager_or_admin_required
def api_partner_company_members(company_id):
    c = db.session.get(Company, company_id)
    if not c:
        abort(404)
    q = (request.args.get("query") or "").strip().lower()
    rows = (User.query.filter_by(company_id=company_id)
            .order_by(User.display_name.asc()).all())
    out = []
    for u in rows:
        name = (u.display_name or "").strip()
        mail = (u.email or "").strip()
        if q and (q not in name.lower()) and (q not in mail.lower()):
            continue
        out.append({"id": u.id, "display_name": name or f"User {u.id}", "email": mail})
    return as_json({"members": out})


def _invite_payload(inv: CompanyInvite | None, company: Company):
    if not inv or not inv.is_active:
        return {"active": False, "code": None, "invite_url": None}
    base = request.host_url.rstrip('/')
    return {"active": True, "code": inv.code, "invite_url": f"{base}/register?invite={inv.token}"}

@app.get("/api/partners/company/<int:company_id>/invite")
@company_manager_or_admin_required
def api_partner_company_invite_get(company_id):
    c = db.session.get(Company, company_id)
    if not c: abort(404)
    inv = get_active_invite(company_id)
    return as_json(_invite_payload(inv, c))

@app.post("/api/partners/company/<int:company_id>/invite/regenerate")
@company_manager_or_admin_required
def api_partner_company_invite_regenerate(company_id):
    c = db.session.get(Company, company_id)
    if not c: abort(404)
    inv = generate_company_invite(company_id)
    return as_json(_invite_payload(inv, c))

@app.post("/api/partners/company/<int:company_id>/invite/deactivate")
@company_manager_or_admin_required
def api_partner_company_invite_deactivate(company_id):
    c = db.session.get(Company, company_id)
    if not c: abort(404)
    CompanyInvite.query.filter_by(company_id=company_id, is_active=True).update({"is_active": False})
    db.session.commit()
    inv = get_active_invite(company_id)
    return as_json(_invite_payload(inv, c))

@app.put("/api/partners/company/<int:company_id>/tasks/<int:task_id>")
@company_manager_or_admin_required
def api_partner_task_update(company_id, task_id):
    t = db.session.get(CompanyTask, task_id)
    if not t or t.company_id != company_id:
        abort(404)

    data = request.get_json() or {}
    for field in ("title","description","points_xp","coins","priority","require_proof","reward_achievement_id"):
        if field in data:
            setattr(t, field, data[field])
    if "due_at" in data:
        t.due_at = parse_iso_dt(data["due_at"])

    db.session.commit()
    return as_json({"ok": True, "id": t.id})

@app.post("/api/company/tasks/<int:task_id>/submit")
@login_required
def api_company_task_submit(task_id):
    u = current_user()

    t = db.session.get(CompanyTask, task_id)
    if not t or not t.is_active:
        abort(404, description="Task not found")
    if not u.company_id or u.company_id != t.company_id:
        abort(403, description="Not your company")
    if not t.require_proof:
        abort(400, description="По этой задаче отчёт не требуется")

    # Разрешаем отправку ТОЛЬКО назначенному пользователю
    a = CompanyTaskAssign.query.filter_by(task_id=task_id, user_id=u.id).first()
    if not a:
        abort(403, description="Задача вам не назначена")

    # Проверка дедлайна: только после срока
    if not t.due_at:
        abort(400, description="Дедлайн не задан для задачи")
    if now_utc() < t.due_at:
        abort(400, description="Отправка отчёта доступна после дедлайна")

    # Повторные сабмиты — вежливо отсекаем
    if a.status in ("submitted", "approved"):
        return as_json({"ok": True, "already": True, "status": a.status})

    f = request.files.get("photo")
    if not f:
        abort(400, description="photo required")

    up_dir = pathlib.Path(app.root_path) / "static" / "uploads" / "task_proofs"
    up_dir.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(f.filename or "")[1].lower() or ".jpg"
    fn = f"{uuid.uuid4().hex}{ext}"
    f.save(up_dir / fn)

    a.status = "submitted"
    a.submitted_at = now_utc()
    sub = CompanyTaskSubmission(
        assign_id=a.id, user_id=u.id, task_id=task_id,
        image_url=f"/static/uploads/task_proofs/{fn}",
        comment=request.form.get("comment") or ""
    )
    db.session.add(sub)

    if t.partner:
        db.session.add(Notification(
            partner_id=t.partner.id, type="task_submitted",
            title="Новый отчёт по задаче", body=t.title,
            data_json=json.dumps({"task_id": t.id, "user_id": u.id})
        ))

    db.session.commit()
    return as_json({"ok": True, "status": a.status})

@app.get("/api/partners/company/<int:company_id>/tasks/<int:task_id>/assigns")
@partner_required
def api_partner_task_assigns(company_id, task_id):
    p = current_partner()
    c = db.session.get(Company, company_id)
    if not c or c.owner_partner_id != p.id: abort(403)
    rows = (CompanyTaskAssign.query.join(CompanyTask, CompanyTaskAssign.task_id==CompanyTask.id)
            .filter(CompanyTask.id==task_id, CompanyTask.company_id==company_id).all())
    out = []
    for r in rows:
        out.append({
            "user_id": r.user_id,
            "display_name": r.user.display_name if r.user else "",
            "status": r.status,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None
        })
    return as_json({"assigns": out})


@app.post("/api/partners/company/<int:company_id>/tasks/<int:task_id>/review")
@partner_required
def api_partner_company_task_review(company_id, task_id):
    p = current_partner()
    c = db.session.get(Company, company_id)
    if not c or c.owner_partner_id != p.id: abort(403)

    require_json()
    d = request.get_json()
    uid = safe_int(d.get("user_id"), 0)
    approve = bool(d.get("approve"))

    a = (CompanyTaskAssign.query.join(CompanyTask, CompanyTaskAssign.task_id==CompanyTask.id)
         .filter(CompanyTask.id==task_id, CompanyTask.company_id==company_id,
                 CompanyTaskAssign.user_id==uid).first())
    if not a: abort(404)
    t = a.task
    u = db.session.get(User, uid)
    if not u: abort(404)

    a.completed_at = now_utc()
    if approve:
        a.status = "approved"
        # Награды
        u.add_xp(max(0, t.points_xp))
        u.add_coins(max(0, t.coins))
        db.session.add(ScoreEvent(
            user_id=uid, source="task", points=t.points_xp, coins=t.coins,
            meta_json=json.dumps({"task_id": t.id, "title": t.title})
        ))
        if t.reward_achievement_id:
            if not UserAchievement.query.filter_by(user_id=uid, achievement_id=t.reward_achievement_id).first():
                db.session.add(UserAchievement(user_id=uid, achievement_id=t.reward_achievement_id))
        # Уведомление пользователю
        db.session.add(Notification(
            user_id=uid, type="task_result",
            title="Задача зачтена", body=t.title,
            data_json=json.dumps({"task_id": t.id})
        ))
    else:
        a.status = "rejected"
        db.session.add(Notification(
            user_id=uid, type="task_result",
            title="Задача отклонена", body=t.title,
            data_json=json.dumps({"task_id": t.id})
        ))

    db.session.commit()
    return as_json({"ok": True, "status": a.status})

@app.get("/api/notifications")
def api_notifications():
    u = current_user()
    p = current_partner()
    if u:
        q = Notification.query.filter_by(user_id=u.id)
    elif p:
        q = Notification.query.filter_by(partner_id=p.id)
    else:
        abort(401)
    items = q.order_by(Notification.created_at.desc()).limit(50).all()
    out = [{
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body or "",
        "data": json.loads(n.data_json or "{}"),
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat()
    } for n in items]
    return as_json({"notifications": out})


@app.post("/api/notifications/read")
def api_notifications_mark_read():
    u = current_user()
    p = current_partner()
    if u:
        Notification.query.filter_by(user_id=u.id, is_read=False).update({"is_read": True})
    elif p:
        Notification.query.filter_by(partner_id=p.id, is_read=False).update({"is_read": True})
    else:
        abort(401)
    db.session.commit()
    return as_json({"ok": True})

@app.get("/training/create")
@login_required_page
def page_training_create():
    u = current_user()
    if not u or not u.company_id:
        return redirect(url_for("page_training_list"))
    cm = CompanyMember.query.filter_by(user_id=u.id, company_id=u.company_id).first()
    if not cm or cm.role not in ("admin","manager"):
        return redirect(url_for("page_training_list"))
    return render_template("training_create.html", company_id=u.company_id)

@app.get("/partner/training/create")
def page_partner_training_create():
    p = current_partner()
    if not p:
        return redirect(url_for("page_partner_login"))
    companies = Company.query.filter_by(owner_partner_id=p.id).order_by(Company.name.asc()).all()
    # если только одна компания — можно сразу подставить
    return render_template("partner_training_create.html", companies=companies)



@app.get("/admin/login")
def page_admin_login():
    if current_admin():
        return redirect(url_for("page_admin_dashboard"))
    return render_template("admin_login.html")

@app.post("/api/admin/login")
def api_admin_login():
    require_json()
    d = request.get_json()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    a = AdminUser.query.filter_by(email=email).first()
    if not a or not check_password_hash(a.password, password):
        abort(401, description="Invalid credentials")
    session.clear()
    session["admin_uid"] = a.id
    return as_json({"ok": True})

@app.post("/api/admin/logout")
def api_admin_logout():
    session.pop("admin_uid", None)
    return as_json({"ok": True})

@app.get("/admin")
@admin_required
def page_admin_dashboard():
    partners = PartnerUser.query.order_by(PartnerUser.created_at.desc()).all()
    companies = Company.query.order_by(Company.created_at.desc()).all()
    return render_template("admin_dashboard.html", partners=partners, companies=companies)

# Создать партнёра + компанию в одном запросе
@app.post("/api/admin/partner_with_company")
@admin_required
def api_admin_partner_with_company():
    require_json()
    d = request.get_json()
    p_email = (d.get("partner_email") or "").strip().lower()
    p_pass  = d.get("partner_password") or ""
    p_name  = (d.get("partner_display_name") or "").strip()
    c_name  = (d.get("company_name") or "").strip()
    c_slug  = (d.get("company_slug") or "").strip().lower()

    if not all([p_email, p_pass, p_name, c_name, c_slug]):
        abort(400, description="All fields required")

    if PartnerUser.query.filter_by(email=p_email).first():
        abort(409, description="Partner email exists")
    if Company.query.filter(or_(Company.name==c_name, Company.slug==c_slug)).first():
        abort(409, description="Company exists")

    p = PartnerUser(email=p_email, password=generate_password_hash(p_pass), display_name=p_name)
    db.session.add(p); db.session.flush()
    c = Company(name=c_name, slug=c_slug, owner_partner_id=p.id, join_code=uuid.uuid4().hex[:8].upper())
    db.session.add(c); db.session.commit()
    return as_json({"partner": partner_to_dict(p), "company": company_public_to_dict(c)})

# ============================== ADMIN API (full control) ==============================
# Все эндпойнты требуют admin_required и работают в JSON.

def _get_user_or_404(uid: int) -> User:
    u = db.session.get(User, uid)
    if not u:
        abort(404, description="User not found")
    return u

def _get_company_or_404(cid: int) -> Company:
    c = db.session.get(Company, cid)
    if not c:
        abort(404, description="Company not found")
    return c

# ---- USERS ----
@app.get("/api/admin/users")
@admin_required
def admin_users_list():
    q = User.query
    email = (request.args.get("email") or "").strip().lower()
    name  = (request.args.get("name") or "").strip()
    company = (request.args.get("company") or "").strip().lower()
    if email:
        q = q.filter(User.email.ilike(f"%{email}%"))
    if name:
        q = q.filter(User.display_name.ilike(f"%{name}%"))
    if company:
        q = q.join(Company, isouter=True).filter(or_(Company.slug==company, Company.name.ilike(f"%{company}%")))
    q = q.order_by(User.created_at.desc()).limit(500)
    users = [user_to_dict(u) for u in q.all()]
    return as_json({"users": users})

@app.get("/api/admin/users/<int:user_id>")
@admin_required
def admin_user_get(user_id):
    u = _get_user_or_404(user_id)
    payload = user_to_dict(u)
    payload["avatar"] = user_avatar_to_dict(u.avatar) if u.avatar else {"user_id": u.id, "selected_by_slot": {}}
    cm = CompanyMember.query.filter_by(user_id=u.id).first()
    payload["company_role"] = (cm.role if cm else None)
    return as_json({"user": payload})

@app.post("/api/admin/users")
@admin_required
def admin_user_create():
    require_json()
    d = request.get_json()
    email = (d.get("email") or "").strip().lower()
    display_name = (d.get("display_name") or "").strip()
    password = d.get("password") or ""
    gender = (d.get("gender") or None)
    if not email or not password or not display_name:
        abort(400, description="email, password, display_name required")
    if User.query.filter_by(email=email).first():
        abort(409, description="Email exists")
    u = User(email=email, password=generate_password_hash(password), display_name=display_name, gender=gender)
    db.session.add(u); db.session.flush()
    # базовый аватар
    base = AvatarItem.query.filter_by(slot="base", key="base_t1").first()
    db.session.add(UserAvatar(user_id=u.id, selected_by_slot=json.dumps({"base": base.key if base else "base_t1"})))
    db.session.commit()
    return as_json({"user": user_to_dict(u)})

@app.patch("/api/admin/users/<int:user_id>")
@admin_required
def admin_user_update(user_id):
    require_json()
    u = _get_user_or_404(user_id)
    d = request.get_json()
    if "email" in d:
        new_email = (d["email"] or "").strip().lower()
        if new_email and new_email != u.email and User.query.filter_by(email=new_email).first():
            abort(409, description="Email already in use")
        u.email = new_email or u.email
    if "display_name" in d:
        u.display_name = (d["display_name"] or u.display_name).strip()
    if "gender" in d:
        u.gender = (d["gender"] or None)
    if "level" in d:
        u.level = max(1, int(d["level"]))
    if "xp" in d:
        u.xp = max(0, int(d["xp"]))
    if "coins" in d:
        u.coins = max(0, int(d["coins"]))
    if "password" in d and d["password"]:
        u.password = generate_password_hash(d["password"])
    db.session.commit()
    return as_json({"user": user_to_dict(u)})

@app.post("/api/admin/users/<int:user_id>/coins")
@admin_required
def admin_user_add_coins(user_id):
    require_json()
    u = _get_user_or_404(user_id)
    delta = safe_int(request.json.get("delta"), 0)
    u.add_coins(max(0, delta))
    db.session.add(ScoreEvent(user_id=u.id, source="bonus", points=0, coins=max(0, delta), meta_json=json.dumps({"admin": True})))
    db.session.commit()
    return as_json({"ok": True, "user": user_to_dict(u)})

@app.post("/api/admin/users/<int:user_id>/xp")
@admin_required
def admin_user_add_xp(user_id):
    require_json()
    u = _get_user_or_404(user_id)
    delta = safe_int(request.json.get("delta"), 0)
    u.add_xp(max(0, delta))
    db.session.add(ScoreEvent(user_id=u.id, source="bonus", points=max(0, delta), coins=0, meta_json=json.dumps({"admin": True})))
    db.session.commit()
    return as_json({"ok": True, "user": user_to_dict(u)})

@app.post("/api/admin/users/<int:user_id>/assign_company")
@admin_required
def admin_user_assign_company(user_id):
    require_json()
    u = _get_user_or_404(user_id)
    cid = safe_int(request.json.get("company_id"), 0)
    role = (request.json.get("role") or "member").strip()
    if role not in ("admin","manager","member"):
        abort(400, description="role must be admin|manager|member")
    c = _get_company_or_404(cid)
    u.company_id = c.id
    cm = CompanyMember.query.filter_by(company_id=c.id, user_id=u.id).first()
    if not cm:
        db.session.add(CompanyMember(company_id=c.id, user_id=u.id, role=role))
    else:
        cm.role = role
    db.session.commit()
    return as_json({"ok": True})

@app.delete("/api/admin/users/<int:user_id>/company")
@admin_required
def admin_user_unassign_company(user_id):
    u = _get_user_or_404(user_id)
    if u.company_id:
        CompanyMember.query.filter_by(company_id=u.company_id, user_id=u.id).delete()
        u.company_id = None
        db.session.commit()
    return as_json({"ok": True})

@app.post("/api/admin/users/<int:user_id>/achievements")
@admin_required
def admin_user_grant_achievement(user_id):
    require_json()
    u = _get_user_or_404(user_id)
    code = (request.json.get("code") or "").strip()
    a = Achievement.query.filter_by(code=code).first()
    if not a: abort(404, description="Achievement not found")
    if not UserAchievement.query.filter_by(user_id=u.id, achievement_id=a.id).first():
        db.session.add(UserAchievement(user_id=u.id, achievement_id=a.id))
        u.add_xp(a.points)
        db.session.add(ScoreEvent(user_id=u.id, source="achievement", points=a.points, coins=0, meta_json=json.dumps({"code": code, "admin": True})))
        db.session.commit()
    return as_json({"ok": True, "user": user_to_dict(u)})

@app.post("/api/admin/users/<int:user_id>/grant_item")
@admin_required
def admin_user_grant_item(user_id):
    """
    Выдать косметику напрямую (slot/key) ИЛИ подарить StoreItem (store_item_id) — он может автоприменить шкурку.
    """
    require_json()
    u = _get_user_or_404(user_id)
    slot = (request.json.get("slot") or "").strip()
    key  = (request.json.get("key") or "").strip()
    store_item_id = request.json.get("store_item_id")
    granted = []
    if slot and key:
        item = _grant_inventory(u.id, slot, key, gender=u.gender or "any")
        granted.append({"slot": item.slot, "key": item.key})
    if store_item_id:
        si = db.session.get(StoreItem, safe_int(store_item_id, 0))
        if not si: abort(404, description="StoreItem not found")
        # «бесплатная покупка» от админа
        p = Purchase(user_id=u.id, store_item_id=si.id, status="done")
        db.session.add(p)
        payload = _json_or_empty(si.payload)
        if si.type == "skin" and payload.get("slot") and payload.get("key"):
            _grant_inventory(u.id, payload["slot"], payload["key"], gender=payload.get("gender","any"), min_level=int(payload.get("min_level",1)))
            if bool(payload.get("auto_equip", True)):
                _equip_selected(u, payload["slot"], payload["key"])
        granted.append({"gift": si.title})
    u.updated_at = now_utc()
    db.session.commit()
    return as_json({"ok": True, "granted": granted})

@app.delete("/api/admin/users/<int:user_id>")
@admin_required
def admin_user_delete(user_id):
    u = _get_user_or_404(user_id)
    # каскады: UserAchievement, Inventory, ScoreEvent, TrainingAttempt, ContestEntry, CompanyMember…
    CompanyMember.query.filter_by(user_id=u.id).delete()
    ContestEntry.query.filter_by(user_id=u.id).delete()
    ScoreEvent.query.filter_by(user_id=u.id).delete()
    TrainingAttempt.query.filter_by(user_id=u.id).delete()
    Inventory.query.filter_by(user_id=u.id).delete()
    UserAchievement.query.filter_by(user_id=u.id).delete()
    if u.avatar: db.session.delete(u.avatar)
    db.session.delete(u)
    db.session.commit()
    return as_json({"ok": True})

# ---- COMPANIES ----
@app.get("/api/admin/companies")
@admin_required
def admin_companies_list():
    items = Company.query.order_by(Company.created_at.desc()).all()
    return as_json({"companies": [company_public_to_dict(c) for c in items]})

@app.post("/api/admin/companies")
@admin_required
def admin_company_create():
    require_json()
    d = request.get_json()
    name = (d.get("name") or "").strip()
    slug = (d.get("slug") or "").strip().lower()
    plan = (d.get("plan") or "starter").strip()
    owner_partner_id = d.get("owner_partner_id")
    if not name or not slug:
        abort(400, description="name, slug required")
    if Company.query.filter(or_(Company.name==name, Company.slug==slug)).first():
        abort(409, description="Company exists")
    c = Company(name=name, slug=slug, plan=plan, owner_partner_id=owner_partner_id, join_code=uuid.uuid4().hex[:8].upper())
    db.session.add(c); db.session.commit()
    return as_json({"company": company_public_to_dict(c)})

@app.patch("/api/admin/companies/<int:company_id>")
@admin_required
def admin_company_update(company_id):
    require_json()
    c = _get_company_or_404(company_id)
    d = request.get_json()
    if "name" in d and d["name"]:
        c.name = d["name"].strip()
    if "slug" in d and d["slug"]:
        s = d["slug"].strip().lower()
        if Company.query.filter(Company.slug==s, Company.id!=c.id).first():
            abort(409, description="Slug exists")
        c.slug = s
    if "plan" in d and d["plan"]:
        c.plan = d["plan"].strip()
    if "billing_email" in d:
        c.billing_email = (d["billing_email"] or None)
    if "owner_partner_id" in d:
        c.owner_partner_id = safe_int(d["owner_partner_id"], None)
    db.session.commit()
    return as_json({"company": company_public_to_dict(c)})

@app.post("/api/admin/companies/<int:company_id>/regen_code")
@admin_required
def admin_company_regen_code(company_id):
    c = _get_company_or_404(company_id)
    c.join_code = uuid.uuid4().hex[:8].upper()
    db.session.commit()
    return as_json({"company": company_public_to_dict(c)})

@app.delete("/api/admin/companies/<int:company_id>")
@admin_required
def admin_company_delete(company_id):
    c = _get_company_or_404(company_id)
    # отключаем участников
    User.query.filter_by(company_id=c.id).update({User.company_id: None})
    CompanyMember.query.filter_by(company_id=c.id).delete()
    Contest.query.filter_by(company_id=c.id).delete()
    CompanyFeedPost.query.filter_by(company_id=c.id).delete()
    CompanyTaskAssign.query.join(CompanyTask, CompanyTaskAssign.task_id==CompanyTask.id).filter(CompanyTask.company_id==c.id).delete(synchronize_session=False)
    CompanyTask.query.filter_by(company_id=c.id).delete()
    TrainingEnrollment.query.filter_by(target_type="company", target_id=c.id).delete()
    db.session.delete(c); db.session.commit()
    return as_json({"ok": True})

@app.post("/api/admin/companies/<int:company_id>/feed")
@admin_required
def admin_company_post(company_id):
    c = _get_company_or_404(company_id)
    require_json()
    text = (request.json.get("text") or "").strip()
    pinned = bool(request.json.get("pinned", False))
    if not text: abort(400, description="text required")
    post = CompanyFeedPost(company_id=c.id, author_type="partner", author_name="Admin", text=text, pinned=pinned)
    db.session.add(post); db.session.commit()
    return as_json({"post_id": post.id})

@app.post("/api/admin/companies/<int:company_id>/tasks")
@admin_required
def admin_company_task(company_id):
    c = _get_company_or_404(company_id)
    require_json()
    d = request.get_json()
    title = (d.get("title") or "").strip()
    if not title: abort(400, description="title required")
    due_at = None
    if d.get("due_at"):
        try: due_at = datetime.fromisoformat(d["due_at"].replace("Z","+00:00"))
        except Exception: pass
    task = CompanyTask(
        company_id=c.id, title=title, description=d.get("description"),
        points_xp=safe_int(d.get("points_xp"), 20), coins=safe_int(d.get("coins"), 5),
        due_at=due_at, is_active=True, created_by_user_id=None, created_by_partner_id=None
    )
    db.session.add(task); db.session.commit()
    return as_json({"task_id": task.id})

@app.post("/api/admin/companies/<int:company_id>/assign_course")
@admin_required
def admin_company_assign_course(company_id):
    c = _get_company_or_404(company_id)
    require_json()
    course_id = safe_int(request.json.get("course_id"), 0)
    if not db.session.get(TrainingCourse, course_id):
        abort(404, description="Course not found")
    if not TrainingEnrollment.query.filter_by(course_id=course_id, target_type="company", target_id=c.id).first():
        db.session.add(TrainingEnrollment(course_id=course_id, target_type="company", target_id=c.id))
        db.session.commit()
    return as_json({"ok": True})

# ---- TRAINING (ADMIN as global author) ----
@app.get("/api/admin/training/courses")
@admin_required
def admin_training_list():
    items = TrainingCourse.query.order_by(TrainingCourse.created_at.desc()).all()
    return as_json({"courses": [course_to_dict(c, with_questions=False) for c in items]})

@app.post("/api/admin/training/courses")
@admin_required
def admin_training_create():
    require_json()
    d = request.get_json()
    title = (d.get("title") or "").strip()
    if not title: abort(400, description="title required")
    c = TrainingCourse(
        title=title,
        description=d.get("description"),
        content_md=d.get("content_md"),
        youtube_url=d.get("youtube_url"),
        pass_score=safe_int(d.get("pass_score"), 80),
        max_attempts=safe_int(d.get("max_attempts"), 3),
        xp_reward=safe_int(d.get("xp_reward"), 50),
        achievement_code=(d.get("achievement_code") or "").strip() or None,
        scope="global",
        created_by_admin=True
    )
    db.session.add(c); db.session.flush()
    for idx, q in enumerate(d.get("questions") or []):
        tq = TrainingQuestion(course_id=c.id, text=(q.get("text") or "").strip(), order_index=idx)
        db.session.add(tq); db.session.flush()
        for opt in (q.get("options") or []):
            db.session.add(TrainingOption(
                question_id=tq.id,
                text=(opt.get("text") or "").strip(),
                is_correct=bool(opt.get("is_correct", False))
            ))
    db.session.commit()
    return as_json({"course": course_to_dict(c, with_questions=True)})

@app.patch("/api/admin/training/courses/<int:course_id>")
@admin_required
def admin_training_update(course_id):
    require_json()
    c = db.session.get(TrainingCourse, course_id)
    if not c: abort(404)
    d = request.get_json()
    for f in ("title","description","content_md","youtube_url","achievement_code","scope"):
        if f in d:
            setattr(c, f, d[f])
    if "pass_score" in d: c.pass_score = safe_int(d["pass_score"], c.pass_score)
    if "max_attempts" in d: c.max_attempts = safe_int(d["max_attempts"], c.max_attempts)
    if "xp_reward" in d: c.xp_reward = safe_int(d["xp_reward"], c.xp_reward)
    if c.scope == "company":
        c.company_id = safe_int(d.get("company_id"), c.company_id)
    db.session.commit()
    return as_json({"course": course_to_dict(c, with_questions=False)})

@app.delete("/api/admin/training/courses/<int:course_id>")
@admin_required
def admin_training_delete(course_id):
    c = db.session.get(TrainingCourse, course_id)
    if not c: abort(404)
    TrainingOption.query.join(TrainingQuestion, TrainingOption.question_id==TrainingQuestion.id).filter(TrainingQuestion.course_id==c.id).delete(synchronize_session=False)
    TrainingQuestion.query.filter_by(course_id=c.id).delete()
    TrainingAttempt.query.filter_by(course_id=c.id).delete()
    TrainingEnrollment.query.filter_by(course_id=c.id).delete()
    db.session.delete(c); db.session.commit()
    return as_json({"ok": True})

@app.post("/api/admin/training/courses/<int:course_id>/questions")
@admin_required
def admin_training_add_question(course_id):
    require_json()
    c = db.session.get(TrainingCourse, course_id)
    if not c: abort(404)
    text = (request.json.get("text") or "").strip()
    if not text: abort(400, description="text required")
    idx = safe_int(request.json.get("order_index"), 0)
    q = TrainingQuestion(course_id=c.id, text=text, order_index=idx)
    db.session.add(q); db.session.commit()
    return as_json({"question_id": q.id})

@app.post("/api/admin/training/questions/<int:question_id>/options")
@admin_required
def admin_training_add_option(question_id):
    require_json()
    q = db.session.get(TrainingQuestion, question_id)
    if not q: abort(404)
    text = (request.json.get("text") or "").strip()
    if not text: abort(400, description="text required")
    opt = TrainingOption(question_id=q.id, text=text, is_correct=bool(request.json.get("is_correct", False)))
    db.session.add(opt); db.session.commit()
    return as_json({"option_id": opt.id})

@app.delete("/api/admin/training/questions/<int:question_id>")
@admin_required
def admin_training_delete_question(question_id):
    q = db.session.get(TrainingQuestion, question_id)
    if not q: abort(404)
    TrainingOption.query.filter_by(question_id=q.id).delete()
    db.session.delete(q); db.session.commit()
    return as_json({"ok": True})

@app.post("/api/admin/training/courses/<int:course_id>/reset_attempts")
@admin_required
def admin_training_reset_attempts(course_id):
    TrainingAttempt.query.filter_by(course_id=course_id).delete()
    db.session.commit()
    return as_json({"ok": True})

# ---- STORE / AVATARS / ACHIEVEMENTS / PARTNERS / CONTESTS ----
@app.get("/api/admin/store_items")
@admin_required
def admin_store_list():
    items = StoreItem.query.order_by(StoreItem.created_at.desc()).all()
    return as_json({"items": [store_item_to_dict(i) for i in items]})

@app.post("/api/admin/store_items")
@admin_required
def admin_store_create():
    require_json()
    d = request.get_json()
    i = StoreItem(
        type=(d.get("type") or "skin"),
        title=(d.get("title") or "").strip(),
        cost_coins=safe_int(d.get("cost_coins"), 0),
        stock=d.get("stock"),
        partner_id=d.get("partner_id"),
        payload=json.dumps(d.get("payload") or {}),
        min_level=safe_int(d.get("min_level"), 1),
    )
    if not i.title: abort(400, description="title required")
    db.session.add(i); db.session.commit()
    return as_json({"item": store_item_to_dict(i)})

@app.patch("/api/admin/store_items/<int:item_id>")
@admin_required
def admin_store_update(item_id):
    require_json()
    i = db.session.get(StoreItem, item_id)
    if not i: abort(404)
    d = request.get_json()
    for f in ("type","title","stock"):
        if f in d: setattr(i, f, d[f])
    if "cost_coins" in d: i.cost_coins = safe_int(d["cost_coins"], i.cost_coins)
    if "min_level" in d: i.min_level = safe_int(d["min_level"], i.min_level)
    if "payload" in d: i.payload = json.dumps(d["payload"] or None)
    if "partner_id" in d: i.partner_id = d["partner_id"]
    db.session.commit()
    return as_json({"item": store_item_to_dict(i)})

@app.delete("/api/admin/store_items/<int:item_id>")
@admin_required
def admin_store_delete(item_id):
    i = db.session.get(StoreItem, item_id)
    if not i: abort(404)
    Purchase.query.filter_by(store_item_id=i.id).delete()
    db.session.delete(i); db.session.commit()
    return as_json({"ok": True})

@app.get("/api/admin/avatar_items")
@admin_required
def admin_avatar_items():
    items = AvatarItem.query.order_by(AvatarItem.slot.asc(), AvatarItem.min_level.asc()).all()
    return as_json({"items": [avatar_item_to_dict(x) for x in items]})

@app.post("/api/admin/avatar_items")
@admin_required
def admin_avatar_item_create():
    require_json()
    d = request.get_json()
    slot = (d.get("slot") or "").strip()
    key  = (d.get("key") or "").strip()
    if not slot or not key: abort(400, description="slot, key required")
    if AvatarItem.query.filter_by(slot=slot, key=key).first():
        abort(409, description="Item exists")
    item = AvatarItem(
        slot=slot, key=key,
        gender=(d.get("gender") or "any"),
        rarity=(d.get("rarity") or "common"),
        min_level=safe_int(d.get("min_level"), 1),
        asset_url=(d.get("asset_url") or f"/static/avatars/layers/{slot}/{key}.svg")
    )
    db.session.add(item); db.session.commit()
    return as_json({"item": avatar_item_to_dict(item)})

@app.delete("/api/admin/avatar_items/<int:item_id>")
@admin_required
def admin_avatar_item_delete(item_id):
    it = db.session.get(AvatarItem, item_id)
    if not it: abort(404)
    Inventory.query.filter_by(item_id=it.id).delete()
    db.session.delete(it); db.session.commit()
    return as_json({"ok": True})

@app.get("/api/admin/achievements")
@admin_required
def admin_achievements_list():
    items = Achievement.query.order_by(Achievement.points.desc()).all()
    return as_json({"achievements": [achievement_to_dict(a) for a in items]})

@app.post("/api/admin/achievements")
@admin_required
def admin_achievement_create():
    require_json()
    d = request.get_json()
    code = (d.get("code") or "").strip().upper()
    title = (d.get("title") or "").strip()
    if not code or not title:
        abort(400, description="code, title required")
    if Achievement.query.filter_by(code=code).first():
        abort(409, description="code exists")
    a = Achievement(code=code, title=title, points=safe_int(d.get("points"), 50), rarity=(d.get("rarity") or "common"),
                    description=d.get("description"))
    db.session.add(a); db.session.commit()
    return as_json({"achievement": achievement_to_dict(a)})

@app.delete("/api/admin/achievements/<int:ach_id>")
@admin_required
def admin_achievement_delete(ach_id):
    a = db.session.get(Achievement, ach_id)
    if not a: abort(404)
    UserAchievement.query.filter_by(achievement_id=a.id).delete()
    db.session.delete(a); db.session.commit()
    return as_json({"ok": True})

@app.get("/api/admin/partners")
@admin_required
def admin_partners_list():
    items = PartnerUser.query.order_by(PartnerUser.created_at.desc()).all()
    return as_json({"partners": [partner_to_dict(p) for p in items]})

@app.post("/api/admin/partners")
@admin_required
def admin_partner_create():
    require_json()
    d = request.get_json()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    display_name = (d.get("display_name") or "").strip()
    if not email or not password or not display_name:
        abort(400, description="email, password, display_name required")
    if PartnerUser.query.filter_by(email=email).first():
        abort(409, description="Email exists")
    p = PartnerUser(email=email, password=generate_password_hash(password), display_name=display_name)
    db.session.add(p); db.session.commit()
    return as_json({"partner": partner_to_dict(p)})

@app.delete("/api/admin/partners/<int:pid>")
@admin_required
def admin_partner_delete(pid):
    p = db.session.get(PartnerUser, pid)
    if not p: abort(404)
    Company.query.filter_by(owner_partner_id=p.id).update({Company.owner_partner_id: None})
    db.session.delete(p); db.session.commit()
    return as_json({"ok": True})

@app.get("/api/admin/contests")
@admin_required
def admin_contests_list():
    items = Contest.query.order_by(Contest.start_at.desc()).all()
    return as_json({"contests": [contest_to_dict(c) for c in items]})

@app.post("/api/admin/contests")
@admin_required
def admin_contest_create():
    require_json()
    d = request.get_json()
    title = (d.get("title") or "").strip()
    if not title: abort(400, description="title required")
    c = Contest(
        title=title,
        description=d.get("description"),
        start_at=datetime.fromisoformat(d["start_at"].replace("Z","+00:00")),
        end_at=datetime.fromisoformat(d["end_at"].replace("Z","+00:00")),
        prize=d.get("prize"),
        min_rating=safe_int(d.get("min_rating"), None),
        is_company_only=bool(d.get("is_company_only", False)),
        company_id=d.get("company_id"),
    )
    db.session.add(c); db.session.commit()
    return as_json({"contest": contest_to_dict(c)})

@app.delete("/api/admin/contests/<int:contest_id>")
@admin_required
def admin_contest_delete(contest_id):
    ContestEntry.query.filter_by(contest_id=contest_id).delete()
    c = db.session.get(Contest, contest_id)
    if c: db.session.delete(c)
    db.session.commit()
    return as_json({"ok": True})

# ---- DIAGNOSTICS / CLEANUP ----
@app.get("/api/admin/score_events")
@admin_required
def admin_score_events():
    uid = request.args.get("user_id", type=int)
    q = ScoreEvent.query.order_by(ScoreEvent.created_at.desc())
    if uid: q = q.filter_by(user_id=uid)
    q = q.limit(1000)
    out = []
    for ev in q.all():
        out.append({
            "id": ev.id, "user_id": ev.user_id, "source": ev.source,
            "points": ev.points, "coins": ev.coins,
            "meta": parse_json(ev.meta_json) or {},
            "created_at": ev.created_at.isoformat()
        })
    return as_json({"events": out})

@app.get("/api/admin/audit")
@admin_required
def admin_audit_list():
    rows = AuditEvent.query.order_by(AuditEvent.created_at.desc()).limit(1000).all()
    return as_json({"audit": [
        {"id":r.id,"user_id":r.user_id,"type":r.type,"signal":r.signal,"score":r.score,"notes":r.notes,"created_at":r.created_at.isoformat()}
        for r in rows
    ]})

@app.delete("/api/admin/training/attempts/<int:attempt_id>")
@admin_required
def admin_training_attempt_delete(attempt_id):
    a = db.session.get(TrainingAttempt, attempt_id)
    if not a: abort(404)
    db.session.delete(a); db.session.commit()
    return as_json({"ok": True})
# ============================ /ADMIN API END ============================



# NEW: присоединиться по коду/токену (для авторизованного пользователя)
@app.route("/api/company/join", methods=["POST"])
@login_required
def api_company_join():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    token = (payload.get("token") or "").strip()
    company, status = join_company_by_invite(current_user.id, code=code or None, token=token or None)
    if status == "NO_CODE":
        return jsonify({"ok": False, "error": "NO_CODE"}), 400
    if status == "NOT_FOUND":
        return jsonify({"ok": False, "error": "INVALID"}), 404
    if status == "ALREADY_MEMBER":
        return jsonify({"ok": True, "already_member": True, "company_id": company.id}), 200
    return jsonify({"ok": True, "company_id": company.id}), 200

# NEW: распознать токен (чтобы на регистрации показать имя компании)
@app.route("/api/company/resolve-invite/<token>", methods=["GET"])
def api_company_resolve_invite(token):
    inv = CompanyInvite.query.filter_by(token=token, is_active=True).first()
    if not inv:
        return jsonify({"active": False}), 200
    return jsonify({"active": True, "company_id": inv.company_id, "company_name": inv.company.name, "code": inv.code}), 200

@app.get("/api/partners/company/<int:company_id>/invite")
@company_manager_or_admin_required
def api_company_invite_get(company_id):
    c = db.session.get(Company, company_id)
    if not c: abort(404)
    inv = get_active_invite(company_id)
    if not inv:
        return as_json({"active": False})
    url = url_for("page_register", _external=True) + f"?invite={inv.token}" if "page_register" in app.view_functions else (request.url_root.rstrip("/") + f"/register?invite={inv.token}")
    return as_json({
        "active": True,
        "code": inv.code,
        "token": inv.token,
        "invite_url": url,
        "company_id": company_id
    })

@app.post("/api/partners/company/<int:company_id>/invite/regenerate")
@company_manager_or_admin_required
def api_company_invite_regenerate(company_id):
    c = db.session.get(Company, company_id)
    if not c: abort(404)
    inv = generate_company_invite(company_id)
    url = url_for("page_register", _external=True) + f"?invite={inv.token}" if "page_register" in app.view_functions else (request.url_root.rstrip("/") + f"/register?invite={inv.token}")
    return as_json({
        "active": True,
        "code": inv.code,
        "token": inv.token,
        "invite_url": url,
        "company_id": company_id
    })

@app.post("/api/partners/company/<int:company_id>/invite/deactivate")
@company_manager_or_admin_required
def api_company_invite_deactivate(company_id):
    c = db.session.get(Company, company_id)
    if not c: abort(404)
    CompanyInvite.query.filter_by(company_id=company_id, is_active=True).update({"is_active": False})
    db.session.commit()
    return as_json({"active": False, "company_id": company_id})

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
