from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from .database import engine, SessionLocal, Base
from .models import User
from .routers import admin, user, analytics

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(admin.router)
app.include_router(user.router)
app.include_router(analytics.router)

# Create tables
Base.metadata.create_all(bind=engine)

# HTML routes
@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open("static/index.html") as f:
        return f.read()

@app.get("/user", response_class=HTMLResponse)
def user_page():
    with open("static/user.html") as f:
        return f.read()

# Seed data
def seed_data(db_session: SessionLocal):
    with db_session() as db:
        if db.query(User).count() == 0:
            users = [
                User(name="alice", team="Engineering"),
                User(name="bob", team="Marketing"),
                User(name="charlie", team="Engineering")
            ]
            for u in users:
                db.add(u)
            db.commit()

seed_data(SessionLocal)