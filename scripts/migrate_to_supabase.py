"""Migrate all data and settings from local SQLite (hti_study.db) to Supabase / PostgreSQL.

Usage:
    python scripts/migrate_to_supabase.py [DATABASE_URL]

Or set DATABASE_URL (or SUPABASE_DATABASE_URL) in your .env file and run:
    python scripts/migrate_to_supabase.py
"""
import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, select, delete
from app import db, config

TABLE_ORDER = [
    ("settings", db.settings_t),
    ("audit", db.audit),
    ("llm_cache", db.llm_cache),
    ("participants", db.participants),
    ("tasks", db.tasks),
    ("event_batches", db.event_batches),
    ("popups", db.popups),
    ("ai_requests", db.ai_requests),
    ("labels", db.labels),
    ("responses", db.responses),
]


def format_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def migrate(dest_url: str, wipe_dest: bool = False):
    src_db_path = ROOT / "hti_study.db"
    if not src_db_path.exists():
        print(f"[Error] Local SQLite database not found at {src_db_path}")
        return False

    dest_url = format_url(dest_url)
    print(f"\n Connecting to target database...")
    print(f"Target: {dest_url.split('@')[-1] if '@' in dest_url else dest_url}")

    src_engine = create_engine(f"sqlite:///{src_db_path}", connect_args={"check_same_thread": False})
    dest_engine = create_engine(
        dest_url,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
    )

    # 1. Create tables on destination
    print("\n Ensuring tables exist in target database...")
    db.md.create_all(dest_engine)
    print(" Tables verified.")

    # 2. Check if destination already has data
    with dest_engine.connect() as dest_conn:
        p_count = dest_conn.execute(select(db.participants.c.id)).rowcount
        if p_count > 0 and not wipe_dest:
            print(f"\n[Notice] Target database already has data.")
            ans = input("Do you want to overwrite existing target data? (y/N): ").strip().lower()
            if ans != "y":
                print("Migration cancelled.")
                return False
            wipe_dest = True

    if wipe_dest:
        print("\n Clearing target tables in reverse dependency order...")
        with dest_engine.begin() as dest_conn:
            for name, table in reversed(TABLE_ORDER):
                dest_conn.execute(delete(table))
        print(" Target cleared.")

    # 3. Migrate tables
    print("\n Migrating data from SQLite to Supabase...")
    total_migrated = 0
    with src_engine.connect() as src_conn, dest_engine.begin() as dest_conn:
        for name, table in TABLE_ORDER:
            rows = src_conn.execute(select(table)).all()
            if not rows:
                print(f"  • {name:15s}: 0 rows (empty)")
                continue
            mappings = [dict(r._mapping) for r in rows]
            # Insert in chunks of 500 to stay well within Postgres parameter limits
            chunk_size = 500
            for i in range(0, len(mappings), chunk_size):
                chunk = mappings[i:i + chunk_size]
                dest_conn.execute(table.insert(), chunk)
            print(f"  • {name:15s}: {len(mappings)} rows copied")
            total_migrated += len(mappings)

    # 4. Synchronize PostgreSQL auto-increment sequences
    print("\n Synchronizing PostgreSQL sequences...")
    from sqlalchemy import text
    seq_tables = ['participants', 'tasks', 'event_batches', 'popups', 'ai_requests', 'labels', 'responses', 'audit']
    with dest_engine.begin() as dest_conn:
        for t in seq_tables:
            dest_conn.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence('{t}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {t}), 0) + 1,
                    false
                );
            """))
    print(" Sequences synchronized.")

    # 5. Ensure frozen settings reflect updated 1.5 threshold & compulsory rule
    seed_path = ROOT / "app" / "data" / "frozen_seed.json"
    if seed_path.exists():
        import json
        with open(seed_path, "r", encoding="utf-8") as f:
            seed = json.load(f)
        with dest_engine.begin() as dest_conn:
            for k in ("frozen", "detector", "pilot_analysis_last"):
                if seed.get(k):
                    dest_conn.execute(text("""
                        INSERT INTO settings (key, value) VALUES (:k, :v)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """), {"k": k, "v": json.dumps(seed[k])})
        print(" Updated frozen settings in Supabase to threshold 1.5 and compulsory rule.")

    print(f"\n Migration complete! Total rows copied: {total_migrated}")
    print(" The main study is ready and pilot settings are frozen on Supabase.\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate local SQLite study data to Supabase/PostgreSQL.")
    parser.add_argument("url", nargs="?", help="Supabase/PostgreSQL connection string")
    parser.add_argument("--wipe", action="store_true", help="Automatically wipe destination before migrating")
    args = parser.parse_args()

    target_url = (
        args.url
        or os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DATABASE_URL")
        or os.getenv("POSTGRES_URL")
    )
    if not target_url or target_url.startswith("sqlite"):
        print("\nNo remote database connection string provided.")
        print("Please provide your Supabase connection string as an argument or in .env:")
        print("  python scripts/migrate_to_supabase.py 'postgresql://postgres:password@...pooler.supabase.com:6543/postgres'")
        sys.exit(1)

    migrate(target_url, wipe_dest=args.wipe)
