# 시즌 아카이빙 사전 점검 (읽기 전용)
#
# 목적: 2026-09-05 시즌 경계를 기준으로 매치 분포를 확인해 s1/s2 분류 정책을 확정한다.
#   - match_date 기준 분포 + NULL 목록
#   - created_at(기록 시점) 기준 교차 검증 — "9/5 이후 신규 작성" 정책과의 불일치 탐지
#   - 경계 부근 매치 상세 (id, 날짜, 모드, 맵)
#
# 실행 (배포 DB):
#   railway run --service Postgres python scripts/season_boundary_check.py
#
# ⚠️ SELECT만 한다. 데이터를 변경하지 않는다.

import os
import sqlite3
import sys

CUTOFF = "2026-09-05"


def get_conn():
    for var in ("DATABASE_PUBLIC_URL", "DATABASE_URL"):
        url = os.environ.get(var)
        if not url:
            continue
        try:
            import psycopg2
            try:
                return psycopg2.connect(url, sslmode="require"), "Postgres(배포)"
            except Exception:
                return psycopg2.connect(url), f"Postgres(배포, {var})"
        except ImportError:
            print(f"[경고] psycopg2 없음 — {var}가 있어도 접속 불가")
            break
    path = os.environ.get("CODM_DB_PATH", "codm.db")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True), f"로컬 SQLite({path}) ⚠️스태일 가능"


def rows(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    out = cur.fetchall()
    cur.close()
    return out


def scalar(conn, sql, params=()):
    r = rows(conn, sql, params)
    return r[0][0] if r else 0


def post_deploy_report(conn, target):
    """배포 후 검증: season 태그 분포. NULL=0이어야 정상 (init_db 백필 완료 증거)."""
    print(f"=== 시즌 태그 배포 후 검증 ({target}) ===\n")
    total = scalar(conn, "SELECT COUNT(*) FROM matches")
    print(f"전체 매치: {total}")
    tagged = 0
    for season, n in rows(
        conn, "SELECT season, COUNT(*) FROM matches GROUP BY season ORDER BY season"
    ):
        print(f"  season={season!r}: {n}")
        tagged += n
    untagged = total - tagged
    print(f"  미태그(NULL): {untagged}")
    if untagged:
        print("\n[경고] 미태그 행이 남아있다 — init_db 백필이 아직 안 돌았거나 실패.")
        print("       재기동(마이그레이션 재실행) 후 다시 검증할 것.")
        return 1
    print("\n[통과] NULL 0건 — 전 행 태그 완료.")
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--post-deploy", action="store_true",
                    help="배포 후 검증 모드: season 태그 분포만 출력 (SELECT만)")
    args = ap.parse_args()

    conn, target = get_conn()
    if args.post_deploy:
        code = post_deploy_report(conn, target)
        conn.close()
        sys.exit(code)

    print(f"=== 시즌 경계 점검 (기준일 {CUTOFF}, {target}) ===\n")

    total = scalar(conn, "SELECT COUNT(*) FROM matches")
    print(f"전체 매치: {total}")

    print("\n-- ① match_date 기준 분포 --")
    for label, cond in [
        ("시즌1 후보 (date < 기준일)", f"match_date < '{CUTOFF}'"),
        ("시즌2 (date >= 기준일)", f"match_date >= '{CUTOFF}'"),
        ("날짜 NULL", "match_date IS NULL"),
    ]:
        print(f"  {label}: {scalar(conn, f'SELECT COUNT(*) FROM matches WHERE {cond}')}")

    print("\n-- ② created_at(기록 시점) 기준 분포 --")
    for label, cond in [
        ("기준일 전 생성", f"created_at < '{CUTOFF}'"),
        ("기준일 이후 생성", f"created_at >= '{CUTOFF}'"),
    ]:
        print(f"  {label}: {scalar(conn, f'SELECT COUNT(*) FROM matches WHERE {cond}')}")

    print("\n-- ③ 두 기준 불일치 (경기일 vs 기록일) --")
    late_rec = scalar(
        conn,
        f"SELECT COUNT(*) FROM matches WHERE match_date < '{CUTOFF}' AND created_at >= '{CUTOFF}'",
    )
    early_rec = scalar(
        conn,
        f"SELECT COUNT(*) FROM matches WHERE match_date >= '{CUTOFF}' AND created_at < '{CUTOFF}'",
    )
    print(f"  기준일 전 경기인데 이후 기록(복기 등): {late_rec}")
    print(f"  기준일 이후 경기인데 이전 기록(시계 오류 의심): {early_rec}")
    if late_rec:
        for r in rows(
            conn,
            f"SELECT id, match_date, created_at, mode, map_name FROM matches "
            f"WHERE match_date < '{CUTOFF}' AND created_at >= '{CUTOFF}' ORDER BY id",
        ):
            print(f"    id={r[0]} date={r[1]} created={r[2]} {r[3]} {r[4]}")

    print("\n-- ④ 날짜 NULL 매치 --")
    null_rows = rows(
        conn,
        "SELECT id, created_at, mode, map_name FROM matches WHERE match_date IS NULL ORDER BY id",
    )
    print(f"  {len(null_rows)}건")
    for r in null_rows[:20]:
        print(f"    id={r[0]} created={r[1]} {r[2]} {r[3]}")
    if len(null_rows) > 20:
        print(f"    ... 외 {len(null_rows) - 20}건")

    print("\n-- ⑤ 경계 부근 상세 (8/25 ~ 9/12) --")
    for r in rows(
        conn,
        "SELECT id, match_date, created_at, mode, map_name, result FROM matches "
        "WHERE match_date BETWEEN '2026-08-25' AND '2026-09-12' ORDER BY match_date, id",
    ):
        print(f"  id={r[0]} date={r[1]} created={str(r[2])[:10]} {r[3]} {r[4]} result={r[5]}")

    print("\n-- ⑥ 경계 id (match_date 기준) --")
    last_s1 = scalar(
        conn, f"SELECT MAX(id) FROM matches WHERE match_date < '{CUTOFF}'"
    )
    first_s2 = scalar(
        conn, f"SELECT MIN(id) FROM matches WHERE match_date >= '{CUTOFF}'"
    )
    print(f"  시즌1 최대 id: {last_s1} / 시즌2 최소 id: {first_s2}")
    overlap = scalar(
        conn,
        "SELECT COUNT(*) FROM matches m WHERE m.match_date IS NOT NULL AND EXISTS ("
        "  SELECT 1 FROM matches o WHERE o.match_date IS NOT NULL"
        "  AND ((m.match_date < '" + CUTOFF + "' AND m.id > o.id AND o.match_date >= '" + CUTOFF + "')"
        "    OR (m.match_date >= '" + CUTOFF + "' AND m.id < o.id AND o.match_date < '" + CUTOFF + "')))",
    )
    print(f"  id 순서·날짜 순서 역전 쌍 존재 매치: {overlap}")

    print("\n-- ⑦ 구간별 스탯 행 --")
    for tbl in ("player_stats_hp", "player_stats_snd"):
        s1 = scalar(
            conn,
            f"SELECT COUNT(*) FROM {tbl} s JOIN matches m ON s.match_id=m.id "
            f"WHERE m.match_date < '{CUTOFF}'",
        )
        s2 = scalar(
            conn,
            f"SELECT COUNT(*) FROM {tbl} s JOIN matches m ON s.match_id=m.id "
            f"WHERE m.match_date >= '{CUTOFF}'",
        )
        nul = scalar(
            conn,
            f"SELECT COUNT(*) FROM {tbl} s JOIN matches m ON s.match_id=m.id "
            f"WHERE m.match_date IS NULL",
        )
        print(f"  {tbl}: s1={s1} s2={s2} NULL소속={nul}")

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)
