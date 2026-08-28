# 배포 Postgres 전체를 로컬 JSON 파일로 덤프/복원 (Railway 스냅샷 Pro 전용 대체)
# 사용:
#   백업: python scripts/backup_db.py            → backups/backup_YYYYMMDD_HHMMSS.json
#   복원: python scripts/backup_db.py backups/backup_....json --restore
# 접속: railway variables --service Postgres 의 DATABASE_PUBLIC_URL 사용 (env 우선)
import json
import os
import sys
import subprocess
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")


def get_public_url() -> str:
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("BACKUP_DATABASE_URL")
    if url:
        return url
    try:
        out = subprocess.run(
            ["railway.exe", "variables", "--service", "Postgres", "--json"],
            capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        out = subprocess.run(
            'railway variables --service Postgres --json',
            capture_output=True, text=True, shell=True, check=True).stdout
    return json.loads(out)["DATABASE_PUBLIC_URL"]


def json_default(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


def backup():
    import psycopg2
    import psycopg2.extras

    url = get_public_url()
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                   ORDER BY table_name""")
    tables = [r["table_name"] for r in cur.fetchall()]
    dump = {"_meta": {"created": datetime.now().isoformat(), "tables": tables}, "data": {}}
    total_rows = 0
    for t in tables:
        cur.execute(f'SELECT * FROM "{t}"')
        rows = [dict(r) for r in cur.fetchall()]
        dump["data"][t] = rows
        total_rows += len(rows)
        print(f"  {t}: {len(rows)}행", flush=True)
    conn.close()

    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, f"backup_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, default=json_default)
    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"백업 완료: {path} ({len(tables)}테이블, {total_rows}행, {size_mb:.1f}MB)", flush=True)


def restore(path: str):
    import psycopg2
    import psycopg2.extras

    with open(path, encoding="utf-8") as f:
        dump = json.load(f)
    url = get_public_url()
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    for t in dump["_meta"]["tables"]:
        rows = dump["data"].get(t, [])
        if not rows:
            continue
        cols = list(rows[0].keys())
        col_list = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        cur.execute(f'DELETE FROM "{t}"')
        for r in rows:
            cur.execute(f'INSERT INTO "{t}" ({col_list}) VALUES ({placeholders})',
                        tuple(r[c] for c in cols))
        print(f"  {t}: {len(rows)}행 복원", flush=True)
    conn.commit()
    conn.close()
    print("복원 완료", flush=True)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[2] == "--restore":
        restore(sys.argv[1])
    else:
        backup()
