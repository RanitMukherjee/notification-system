from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import User

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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