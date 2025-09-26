from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import (
    Alert, User, NotificationDelivery, UserAlertPreference,
    get_relevant_users, should_send_reminder, send_in_app_alert,
    DATABASE_URL
)

celery_app = Celery("tasks", broker="amqp://guest@localhost:5672//")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

@celery_app.task
def send_reminders():
    db = SessionLocal()
    try:
        active_alerts = db.query(Alert).filter(
            Alert.is_archived == False,
            Alert.reminder_enabled == True
        ).all()
        for alert in active_alerts:
            users = get_relevant_users(db, alert)
            for user in users:
                if should_send_reminder(db, user.id, alert):
                    send_in_app_alert(db, user.id, alert.id)
        db.commit()
    finally:
        db.close()