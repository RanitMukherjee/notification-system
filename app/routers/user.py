from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, timezone
from typing import List
from ..dependencies import get_db, get_current_user
from ..models import Alert, User, UserAlertPreference
from ..schemas import SnoozeRequest
from ..helpers import get_relevant_users

router = APIRouter(prefix="/user", tags=["user"])

@router.get("/alerts")
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

@router.post("/alerts/{alert_id}/snooze")
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

@router.post("/alerts/{alert_id}/read")
def mark_read(alert_id: int, read: bool = True, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pref = db.query(UserAlertPreference).filter_by(user_id=current_user.id, alert_id=alert_id).first()
    if not pref:
        pref = UserAlertPreference(user_id=current_user.id, alert_id=alert_id)
        db.add(pref)
    pref.is_read = read
    db.commit()
    return {"status": "updated"}