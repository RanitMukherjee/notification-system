from datetime import datetime, timedelta, timezone
from typing import List, Optional
from enum import Enum
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import jwt
import os
from celery import Celery

# ----------------------------
# Config
# ----------------------------
SECRET_KEY = "alert-secret"
ALGORITHM = "HS256"
DATABASE_URL = "sqlite:///./alerts.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# ----------------------------
# Models
# ----------------------------
class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class AudienceType(str, Enum):
    ORG = "org"
    TEAM = "team"
    USER = "user"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    team = Column(String)

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    message = Column(Text)
    severity = Column(SQLEnum(Severity))
    start_time = Column(DateTime, default=datetime.utcnow)
    expiry_time = Column(DateTime, nullable=True)
    reminder_enabled = Column(Boolean, default=True)
    audience_type = Column(SQLEnum(AudienceType))
    audience_ids = Column(JSON, nullable=True)  # list of IDs
    is_archived = Column(Boolean, default=False)

class NotificationDelivery(Base):
    __tablename__ = "deliveries"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    alert_id = Column(Integer, ForeignKey("alerts.id"))
    sent_at = Column(DateTime, default=datetime.utcnow)

class UserAlertPreference(Base):
    __tablename__ = "preferences"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    alert_id = Column(Integer, ForeignKey("alerts.id"))
    is_read = Column(Boolean, default=False)
    snoozed_until = Column(DateTime, nullable=True)  # end of day

Base.metadata.create_all(bind=engine)

# ----------------------------
# Pydantic Schemas
# ----------------------------
class AlertCreate(BaseModel):
    title: str
    message: str
    severity: Severity
    audience_type: AudienceType
    audience_ids: Optional[List[int]] = None
    expiry_time: Optional[datetime] = None

class AlertOut(BaseModel):
    id: int
    title: str
    message: str
    severity: Severity
    start_time: datetime
    expiry_time: Optional[datetime]
    audience_type: AudienceType
    audience_ids: Optional[List[int]]

    class Config:
        from_attributes = True

class SnoozeRequest(BaseModel):
    pass

# ----------------------------
# Dependencies
# ----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=401, detail="No token")
    try:
        payload = jwt.decode(token.replace("Bearer ", ""), SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(User).filter(User.name == payload["sub"]).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

# ----------------------------
# Helper Functions
# ----------------------------
def get_relevant_users(db: Session, alert: Alert) -> List[User]:
    if alert.audience_type == AudienceType.ORG:
        return db.query(User).all()
    elif alert.audience_type == AudienceType.TEAM:
        return db.query(User).filter(User.team.in_(alert.audience_ids or [])).all()
    elif alert.audience_type == AudienceType.USER:
        return db.query(User).filter(User.id.in_(alert.audience_ids or [])).all()
    return []

def should_send_reminder(db: Session, user_id: int, alert: Alert) -> bool:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if alert.expiry_time and now > alert.expiry_time:
        return False
    if not alert.reminder_enabled:
        return False

    pref = db.query(UserAlertPreference).filter_by(user_id=user_id, alert_id=alert.id).first()
    if pref and pref.snoozed_until and now < pref.snoozed_until:
        return False

    last_delivery = db.query(NotificationDelivery)\
        .filter_by(user_id=user_id, alert_id=alert.id)\
        .order_by(NotificationDelivery.sent_at.desc())\
        .first()
    if not last_delivery or (now - last_delivery.sent_at) > timedelta(hours=2):
        return True
    return False

def send_in_app_alert(db: Session, user_id: int, alert_id: int):
    delivery = NotificationDelivery(user_id=user_id, alert_id=alert_id)
    db.add(delivery)
    db.commit()

# ----------------------------
# Admin Routes (no auth)
# ----------------------------
@app.post("/admin/alerts", response_model=AlertOut)
def create_alert(alert: AlertCreate, db: Session = Depends(get_db)):
    db_alert = Alert(**alert.model_dump())
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    # Trigger first delivery
    users = get_relevant_users(db, db_alert)
    for u in users:
        send_in_app_alert(db, u.id, db_alert.id)
    return db_alert

@app.get("/admin/alerts", response_model=List[AlertOut])
def list_alerts(db: Session = Depends(get_db)):
    return db.query(Alert).filter(Alert.is_archived == False).all()

# ----------------------------
# User Routes (JWT auth)
# ----------------------------
@app.get("/user/alerts")
def get_user_alerts(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    alerts = []
    all_alerts = db.query(Alert).filter(
        Alert.is_archived == False,
        Alert.start_time <= datetime.utcnow(),
        (Alert.expiry_time.is_(None)) | (Alert.expiry_time > datetime.utcnow())
    ).all()
    for a in all_alerts:
        if current_user.id in [u.id for u in get_relevant_users(db, a)]:
            pref = db.query(UserAlertPreference).filter_by(user_id=current_user.id, alert_id=a.id).first()
            alerts.append({
                "alert": AlertOut.model_validate(a),
                "is_read": pref.is_read if pref else False,
                "snoozed_until": pref.snoozed_until if pref else None
            })
    return alerts

@app.post("/user/alerts/{alert_id}/snooze")
def snooze_alert(alert_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
    pref = db.query(UserAlertPreference).filter_by(user_id=current_user.id, alert_id=alert_id).first()
    if not pref:
        pref = UserAlertPreference(user_id=current_user.id, alert_id=alert_id)
        db.add(pref)
    pref.snoozed_until = end_of_day
    db.commit()
    return {"status": "snoozed"}

@app.post("/user/alerts/{alert_id}/read")
def mark_read(alert_id: int, read: bool = True, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    pref = db.query(UserAlertPreference).filter_by(user_id=current_user.id, alert_id=alert_id).first()
    if not pref:
        pref = UserAlertPreference(user_id=current_user.id, alert_id=alert_id)
        db.add(pref)
    pref.is_read = read
    db.commit()
    return {"status": "updated"}

# ----------------------------
# Analytics
# ----------------------------
@app.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    total_alerts = db.query(Alert).count()
    delivered = db.query(NotificationDelivery).count()
    read = db.query(UserAlertPreference).filter_by(is_read=True).count()
    snoozed = db.query(UserAlertPreference).filter(UserAlertPreference.snoozed_until.isnot(None)).count()
    by_severity = {}
    for s in Severity:
        by_severity[s] = db.query(Alert).filter_by(severity=s).count()
    return {
        "total_alerts": total_alerts,
        "delivered": delivered,
        "read": read,
        "snoozed": snoozed,
        "by_severity": by_severity
    }

# ----------------------------
# Auth Helper (for testing)
# ----------------------------
@app.get("/token/{username}")
def get_token(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.name == username).first()
    if not user:
        raise HTTPException(404, "User not found")
    token = jwt.encode({"sub": username}, SECRET_KEY, algorithm=ALGORITHM)
    return {"token": token}

# ----------------------------
# UI (Admin Dashboard)
# ----------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open("static/index.html") as f:
        return f.read()

# ----------------------------
# Seed on first run
# ----------------------------
def seed_data(db: Session):
    if db.query(User).count() == 0:
        users = [
            User(name="alice", team="Engineering"),
            User(name="bob", team="Marketing"),
            User(name="charlie", team="Engineering")
        ]
        for u in users:
            db.add(u)
        db.commit()

seed_data(SessionLocal())