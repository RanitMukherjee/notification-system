from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..dependencies import get_db
from ..models import Alert, NotificationDelivery, UserAlertPreference, Severity

router = APIRouter(tags=["analytics"])

@router.get("/analytics")
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