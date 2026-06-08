import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chatra.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_engine(org_type: str = "university"):
    if DATABASE_URL.startswith("sqlite"):
        return engine
    schema = "school" if org_type == "school" else "university"
    return create_engine(
        DATABASE_URL,
        connect_args={"options": f"-csearch_path={schema},public"},
    )

def get_session_for_org(org_type: str):
    eng = get_engine(org_type)
    OrgSession = sessionmaker(bind=eng)
    return OrgSession()
