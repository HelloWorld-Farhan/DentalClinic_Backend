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

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = None
SessionLocal = None
Base = declarative_base()

def ensure_schema_compatibility(target_engine):
    if not target_engine:
        return
    try:
        from sqlalchemy import text, inspect
        # Ensure all models are registered and tables exist
        import prescription.models  # noqa: F401
        Base.metadata.create_all(bind=target_engine)

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
                    conn.execute(text("ALTER TABLE users ADD COLUMN remembered_device_id TEXT"))
                else:
                    try:
                        conn.execute(text("ALTER TABLE users ALTER COLUMN remembered_device_id TYPE TEXT"))
                    except Exception:
                        pass
                if "two_factor_enabled" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN DEFAULT FALSE"))
                if "age" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN age INTEGER"))
                if "gender" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN gender VARCHAR(20)"))
                if "height" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN height VARCHAR(20)"))
                if "weight" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN weight VARCHAR(20)"))
                if "has_allergies" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN has_allergies BOOLEAN DEFAULT FALSE"))
                if "allergies_description" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN allergies_description VARCHAR(500)"))
                if "profile_completed" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN profile_completed BOOLEAN DEFAULT FALSE"))
                if "is_google_linked" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_google_linked BOOLEAN DEFAULT FALSE"))
                if "license_number" in columns:
                    conn.execute(text("ALTER TABLE users DROP COLUMN license_number"))
                if "clinic_id" in columns:
                    conn.execute(text("ALTER TABLE users DROP COLUMN clinic_id"))
                conn.commit()
    except Exception as e:
        print(f"[DB Schema Notice] Schema check: {e}")

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
            print("[Database] Successfully connected to Supabase PostgreSQL.")
            return
        except Exception as e:
            print(f"[Database Warning] Database connection error: {e}")

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    ensure_schema_compatibility(engine)

init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
