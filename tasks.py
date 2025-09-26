from celery import Celery
from sqlalchemy.orm import sessionmaker
from app import Alert, User, NotificationDelivery, UserAlertPreference, get_relevant_users, should_send_reminder, send_in_app_alert, DATABASE_URL, engine, SessionLocal

celery_app = Celery("tasks", broker="amqp://guest@localhost:5672//")


@celery_app.task
# Use context manager for DB session to ensure proper closure
# Commit once per task after all alerts and notifications processed

def send_reminders():
    db = SessionLocal()
    try:
        active_alerts = db.query(Alert).filter(Alert.is_archived == False, Alert.reminder_enabled == True).all()
        for alert in active_alerts:
            users = get_relevant_users(db, alert)
            for user in users:
                if should_send_reminder(db, user.id, alert):
                    send_in_app_alert(db, user.id, alert.id)
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()