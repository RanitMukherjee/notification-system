from typing import List
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from .models import Alert, User, NotificationDelivery, UserAlertPreference

def get_relevant_users(db: Session, alert: Alert) -> List[User]:
    if alert.audience_type == "org":
        return db.query(User).all()
    elif alert.audience_type == "team":
        if alert.audience_ids:
            return db.query(User).filter(User.team.in_(alert.audience_ids)).all()
        else:
            return []
    elif alert.audience_type == "user":
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