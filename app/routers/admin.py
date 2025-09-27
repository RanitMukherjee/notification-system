from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ..dependencies import get_db
from ..models import Alert
from ..schemas import AlertCreate, AlertOut
from ..helpers import get_relevant_users, send_in_app_alert

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/alerts", response_model=AlertOut)
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

@router.get("/alerts", response_model=List[AlertOut])
def list_alerts(db: Session = Depends(get_db)):
    return db.query(Alert).filter(Alert.is_archived == False).all()

@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.is_archived == False).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_archived = True
    db.commit()
    return {"status": "deleted"}