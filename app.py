from datetime import datetime, timedelta, timezone
from typing import List, Optional
from enum import Enum
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey, Enum as SQLEnum, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL = "sqlite:///alerts.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Enums
class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class AudienceType(str, Enum):
    ORG = "org"
    TEAM = "team"
    USER = "user"

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    team = Column(String, nullable=True)

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(SQLEnum(Severity), nullable=False, default=Severity.INFO)
    start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expiry_time = Column(DateTime, nullable=True)
    reminder_enabled = Column(Boolean, default=True)
    audience_type = Column(SQLEnum(AudienceType), nullable=False)
    audience_ids = Column(JSON, nullable=True)  # List of IDs
    is_archived = Column(Boolean, default=False)

class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class UserAlertPreference(Base):
    __tablename__ = "user_alert_preferences"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    is_read = Column(Boolean, default=False)
    snoozed_until = Column(DateTime, nullable=True)

Base.metadata.create_all(bind=engine)

# Schemas
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
        orm_mode = True

class SnoozeRequest(BaseModel):
    pass  # Placeholder if needed

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# User Authentication (Simplified: Bearer token is just the username)
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization header")
    
    username = auth.removeprefix("Bearer ").strip()
    if not username:
        raise HTTPException(status_code=401, detail="Username missing in token")
    
    user = db.query(User).filter(User.name == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

# Helper functions
def get_relevant_users(db: Session, alert: Alert) -> List[User]:
    if alert.audience_type == AudienceType.ORG:
        return db.query(User).all()
    elif alert.audience_type == AudienceType.TEAM:
        if alert.audience_ids:
            return db.query(User).filter(User.team.in_(alert.audience_ids)).all()
        else:
            return []
    elif alert.audience_type == AudienceType.USER:
        if alert.audience_ids:
            return db.query(User).filter(User.id.in_(alert.audience_ids)).all()
        else:
            return []
    return []

def should_send_reminder(db: Session, user_id: int, alert: Alert) -> bool:
    now = datetime.now(timezone.utc)
    if alert.expiry_time and now > alert.expiry_time:
        return False
    if not alert.reminder_enabled:
        return False
    pref = db.query(UserAlertPreference).filter_by(user_id=user_id, alert_id=alert.id).first()
    if pref and pref.snoozed_until and now < pref.snoozed_until:
        return False
    last_delivery = db.query(NotificationDelivery).filter_by(user_id=user_id, alert_id=alert.id).order_by(NotificationDelivery.sent_at.desc()).first()
    if not last_delivery or (now - last_delivery.sent_at) >= timedelta(hours=2):
        return True
    return False

def send_in_app_alert(db: Session, user_id: int, alert_id: int):
    delivery = NotificationDelivery(user_id=user_id, alert_id=alert_id, sent_at=datetime.now(timezone.utc))
    db.add(delivery)
    # Commit will be done by caller

# Routes
@app.post("/admin/alerts", response_model=AlertOut)
def create_alert(alert_create: AlertCreate, db: Session = Depends(get_db)):
    alert = Alert(
        title=alert_create.title,
        message=alert_create.message,
        severity=alert_create.severity,
        audience_type=alert_create.audience_type,
        audience_ids=alert_create.audience_ids,
        expiry_time=alert_create.expiry_time,
        reminder_enabled=True,
        start_time=datetime.now(timezone.utc),
        is_archived=False
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    # Send initial notifications
    users = get_relevant_users(db, alert)
    for user in users:
        send_in_app_alert(db, user.id, alert.id)
    db.commit()

    return alert

@app.get("/admin/alerts", response_model=List[AlertOut])
def list_alerts(db: Session = Depends(get_db)):
    return db.query(Alert).filter(Alert.is_archived == False).all()

@app.delete("/admin/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.is_archived == False).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_archived = True
    db.commit()
    return {"status": "deleted"}

@app.get("/user/alerts")
def get_user_alerts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    all_alerts = db.query(Alert).filter(
        Alert.is_archived == False,
        Alert.start_time <= now,
        or_(Alert.expiry_time == None, Alert.expiry_time > now)
    ).all()
    alerts = []
    for alert in all_alerts:
        users = get_relevant_users(db, alert)
        if any(u.id == current_user.id for u in users):
            pref = db.query(UserAlertPreference).filter_by(user_id=current_user.id, alert_id=alert.id).first()
            alerts.append({
                "alert": alert,
                "is_read": pref.is_read if pref else False,
                "snoozed_until": pref.snoozed_until if pref else None
            })
    return alerts

@app.post("/user/alerts/{alert_id}/snooze")
def snooze_alert(alert_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
    pref = db.query(UserAlertPreference).filter_by(user_id=current_user.id, alert_id=alert_id).first()
    if not pref:
        pref = UserAlertPreference(user_id=current_user.id, alert_id=alert_id)
        db.add(pref)
    pref.snoozed_until = end_of_day
    db.commit()
    return {"status": "snoozed"}

@app.post("/user/alerts/{alert_id}/read")
def mark_read(alert_id: int, read: bool = True, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pref = db.query(UserAlertPreference).filter_by(user_id=current_user.id, alert_id=alert_id).first()
    if not pref:
        pref = UserAlertPreference(user_id=current_user.id, alert_id=alert_id)
        db.add(pref)
    pref.is_read = read
    db.commit()
    return {"status": "updated"}

@app.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    total_alerts = db.query(Alert).count()
    delivered = db.query(NotificationDelivery).count()
    read = db.query(UserAlertPreference).filter(UserAlertPreference.is_read == True).count()
    snoozed = db.query(UserAlertPreference).filter(UserAlertPreference.snoozed_until != None).count()
    by_severity = {sev: db.query(Alert).filter(Alert.severity == sev).count() for sev in Severity}
    return {
        "total_alerts": total_alerts,
        "delivered": delivered,
        "read": read,
        "snoozed": snoozed,
        "by_severity": by_severity
    }

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open("static/index.html") as f:
        return f.read()

@app.get("/user", response_class=HTMLResponse)
def user_page():
    with open("static/user.html") as f:
        return f.read()

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