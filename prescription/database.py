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

def ensure_schema_compatibility(target_engine):
    if not target_engine:
        return
    try:
        from sqlalchemy import text, inspect
        inspector = inspect(target_engine)
        if "users" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("users")]
            with target_engine.connect() as conn:
                if "failed_login_attempts" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0"))
                if "locked_until" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN locked_until TIMESTAMP"))
                if "last_failed_attempt" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN last_failed_attempt TIMESTAMP"))
                if "remembered_device_id" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN remembered_device_id VARCHAR(255)"))
                if "two_factor_enabled" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN DEFAULT 0"))
                conn.commit()
    except Exception as e:
        print(f"[DB Schema Notice] Schema check skipped: {e}")

def init_db():
    global engine, SessionLocal
    if DATABASE_URL:
        try:
            test_engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
            with test_engine.connect():
                pass
            engine = test_engine
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            ensure_schema_compatibility(engine)
            return
        except Exception:
            # Fallback to local dev SQLite when cloud host is unreachable on local network
            pass

    dev_db = Path(__file__).resolve().parent / "prescription_dev.db"
    engine = create_engine(f"sqlite:///{dev_db}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    ensure_schema_compatibility(engine)

init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
