from datetime import datetime, timezone
from app import db

class AmoConn(db.Model):
    __tablename__ = "amocrm_connections"
    id           = db.Column(db.Integer, primary_key=True)
    company_id   = db.Column(db.Integer, nullable=False, index=True, unique=True)
    base_domain  = db.Column(db.String(255), nullable=False)  # myco.kommo.com | myco.amocrm.ru
    access_token = db.Column(db.Text, nullable=False)
    refresh_token= db.Column(db.Text, nullable=False)
    expires_at   = db.Column(db.DateTime(timezone=True), nullable=False)
    last_sync_at = db.Column(db.DateTime(timezone=True))

    @property
    def is_expired(self):
        return datetime.now(timezone.utc) >= (self.expires_at or datetime.now(timezone.utc))

class AmoUserMap(db.Model):
    __tablename__ = "amocrm_user_map"
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, index=True, nullable=False)
    platform_user_id = db.Column(db.Integer, index=True, nullable=False)
    amocrm_user_id   = db.Column(db.Integer, index=True, nullable=False)

class AmoMetricsDaily(db.Model):
    __tablename__ = "amocrm_metrics_daily"
    id             = db.Column(db.Integer, primary_key=True)
    company_id     = db.Column(db.Integer, index=True, nullable=False)
    amocrm_user_id = db.Column(db.Integer, index=True, nullable=False)
    date           = db.Column(db.Date, index=True, nullable=False)
    won_count      = db.Column(db.Integer, default=0)
    won_sum        = db.Column(db.Numeric(14, 2), default=0)
    lost_count     = db.Column(db.Integer, default=0)
    lost_sum       = db.Column(db.Numeric(14, 2), default=0)

    __table_args__ = (
        db.UniqueConstraint("company_id", "amocrm_user_id", "date", name="uq_metrics_scope"),
    )

class AmoSyncCursor(db.Model):
    __tablename__ = "amocrm_sync_cursor"
    id         = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, index=True, unique=True, nullable=False)
    updated_since = db.Column(db.DateTime(timezone=True))  # для инкрементальной выборки
