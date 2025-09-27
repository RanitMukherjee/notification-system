from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy import Enum as SQLEnum, or_
from sqlalchemy.orm import Session
from .database import Base
from datetime import datetime, timezone

class Severity(str, PyEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class AudienceType(str, PyEnum):
    ORG = "org"
    TEAM = "team"
    USER = "user"

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