"""Reset the demo data: empty all tables and load seed.sql again.

Usage:
  python reset_demo.py local          show what would happen (changes nothing)
  python reset_demo.py neon           show what would happen (changes nothing)
  python reset_demo.py neon --yes     really reset Neon

"local" uses DATABASE_URL and "neon" uses NEON_DATABASE_URL from .env.
WARNING: a reset deletes every row, including all tickets.
"""
import sys
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, text

TARGETS = {"local": "DATABASE_URL", "neon": "NEON_DATABASE_URL"}
TABLES = ["tickets", "plans", "services", "orders", "memberships", "customers"]


def main():
    args = sys.argv[1:]
    if not args or args[0] not in TARGETS:
        print(__doc__)
        sys.exit(1)
    target = args[0]
    project = Path(__file__).parent
    url = dotenv_values(project / ".env").get(TARGETS[target])
    if not url:
        sys.exit(f"{TARGETS[target]} is missing from .env")

    engine = create_engine(url)
    if "--yes" not in args:
        print(f"Dry run on {target}. Nothing was changed.")
        print_counts(engine, "Rows now:")
        print(f"A reset would DELETE all rows in {', '.join(TABLES)}, then load seed.sql.")
        print(f"To do it, run: python reset_demo.py {target} --yes")
        return

    seed = (project / "seed.sql").read_text(encoding="utf-8")
    # One transaction: if anything fails, nothing is deleted.
    with engine.begin() as conn:
        conn.exec_driver_sql(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY")
        conn.exec_driver_sql(seed)  # exec_driver_sql: "14:30:00" in seed.sql isn't a placeholder
    print(f"Reset done on {target}.")
    print_counts(engine, "Rows now:")


def print_counts(engine, title):
    with engine.connect() as conn:
        counts = [f"{t}={conn.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()}" for t in TABLES]
        statuses = conn.execute(text(
            "SELECT c.name, m.tier, m.status FROM memberships m JOIN customers c ON c.id = m.customer_id ORDER BY m.id"
        )).all()
    print(title, ", ".join(counts))
    print("Memberships:", ", ".join(f"{name} {tier} {status}" for name, tier, status in statuses))


if __name__ == "__main__":
    main()
