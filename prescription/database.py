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

def seed_initial_clinicians(target_engine):
    if not target_engine:
        return
    try:
        from sqlalchemy import text
        with target_engine.connect() as conn:
            # 1. Master Clinician: farhankhalid17968@gmail.com (Password: Farhan@123)
            row = conn.execute(text("SELECT id FROM users WHERE email = 'farhankhalid17968@gmail.com'")).fetchone()
            if not row:
                conn.execute(text("""
                    INSERT INTO users (id, email, full_name, hashed_password, role, license_number, clinic_id, is_verified, failed_login_attempts, two_factor_enabled)
                    VALUES ('usr_farhan_master', 'farhankhalid17968@gmail.com', 'Farhan Khalid', '$2b$12$1WPxu2QMz9G9vE.iQtBbjuCYinL.zCtoighm2POWezA5tngYuQP6q', 'DENTIST', '1982740928', 'CLINIC-MAIN', TRUE, 0, FALSE)
                """))
            else:
                conn.execute(text("""
                    UPDATE users SET is_verified = TRUE, failed_login_attempts = 0, locked_until = NULL, last_failed_attempt = NULL, two_factor_enabled = FALSE
                    WHERE email = 'farhankhalid17968@gmail.com'
                """))

            # 2. Institutional Demo Clinician: dr.smith@smileclinic.com
            smith = conn.execute(text("SELECT id FROM users WHERE email = 'dr.smith@smileclinic.com'")).fetchone()
            if not smith:
                conn.execute(text("""
                    INSERT INTO users (id, email, full_name, hashed_password, role, license_number, clinic_id, is_verified, failed_login_attempts, two_factor_enabled)
                    VALUES ('usr_smith_demo', 'dr.smith@smileclinic.com', 'Dr. Sarah Smith, DDS', '$2b$12$1WPxu2QMz9G9vE.iQtBbjuCYinL.zCtoighm2POWezA5tngYuQP6q', 'DENTIST', '1982740928', 'CLINIC-MAIN', TRUE, 0, FALSE)
                """))
            else:
                conn.execute(text("""
                    UPDATE users SET is_verified = TRUE, failed_login_attempts = 0, locked_until = NULL, last_failed_attempt = NULL, two_factor_enabled = FALSE
                    WHERE email = 'dr.smith@smileclinic.com'
                """))
            conn.commit()
    except Exception as e:
        print(f"[DB Seed Notice] Seed check: {e}")

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
                    conn.execute(text("ALTER TABLE users ADD COLUMN remembered_device_id VARCHAR(255)"))
                if "two_factor_enabled" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN DEFAULT FALSE"))
                conn.commit()

        # Seed essential clinician records
        seed_initial_clinicians(target_engine)
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
