import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment secrets
env_file = Path(__file__).resolve().parent / ".env"
if env_file.exists():
    load_dotenv(env_file, override=False)
else:
    load_dotenv(override=False)

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = None
SessionLocal = None
Base = declarative_base()

def init_db():
    global engine, SessionLocal
    if DATABASE_URL:
        try:
            test_engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
            with test_engine.connect():
                pass
            engine = test_engine
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            return
        except Exception:
            # Fallback to local dev SQLite when cloud host is unreachable on local network
            pass

    dev_db = Path(__file__).resolve().parent / "prescription_dev.db"
    engine = create_engine(f"sqlite:///{dev_db}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
