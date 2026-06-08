from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from starlette.staticfiles import StaticFiles
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import Base, engine, get_engine
from models import Base
from routers import auth, admin, users, posts, chats, messages, reactions, uploads, ai
from routers.assignments import router as assignments_router
from routers.classes import router as classes_router, rating_router
from routers.rag import router as rag_router
from websocket import router as ws_router
from sqlalchemy import text
from services.deadline_checker import deadline_checker_loop

logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)

def _check_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logging.info("Database connection OK")
    except Exception as e:
        logging.error(f"Database connection failed: {e}")

_check_db()

def _ensure_schemas():
    if not str(engine.url).startswith("postgresql"):
        return
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS university"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS school"))
            conn.commit()
        for org in ["university", "school"]:
            Base.metadata.create_all(bind=get_engine(org))
        logging.info("Schemas ready: university, school")
    except Exception as e:
        logging.warning(f"Schema init skipped: {e}")

_ensure_schemas()

_cors_raw = os.getenv("CORS_ORIGINS", "*")
_cors_origins = [o.strip() for o in _cors_raw.split(",")] if _cors_raw != "*" else ["*"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(deadline_checker_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Chatra API", version="3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(chats.router)
app.include_router(messages.router)
app.include_router(ws_router)
app.include_router(reactions.router)
app.include_router(uploads.router)
app.include_router(ai.router)
app.include_router(assignments_router)
app.include_router(classes_router)
app.include_router(rating_router)
app.include_router(rag_router)

_upload_dir = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(_upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_upload_dir), name="uploads")


@app.get("/health")
def health():
    return {"status": "ok"}
