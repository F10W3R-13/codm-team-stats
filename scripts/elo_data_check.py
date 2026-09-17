# ELO 개발용 데이터 기준선 점검 스크립트 (읽기 전용)
#
# 목적: ELO 학습에 쓸 수 있는 매치가 실제로 얼마나 되는지 확인.
#   - 전체 매치 / 승패(result) 입력 매치 / 스코어 입력 매치
#   - 모드(HP/SND)별 분포, 날짜 범위, 선수 수
#
# 실행 (배포 DB):
#   railway run --service Postgres python scripts/elo_data_check.py
#
# ⚠️ SELECT만 한다. 데이터를 변경하지 않는다.

import os
import sqlite3
import sys


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


def main():
    conn, target = get_conn()
    print(f"=== ELO 데이터 기준선 ({target}) ===\n")

    total = scalar(conn, "SELECT COUNT(*) FROM matches")
    with_result = scalar(conn, "SELECT COUNT(*) FROM matches WHERE result IS NOT NULL")
    with_score = scalar(
        conn,
        "SELECT COUNT(*) FROM matches WHERE team_score IS NOT NULL AND opponent_score IS NOT NULL",
    )
    print(f"전체 매치:            {total}")
    print(f"승패(result) 입력:    {with_result} ({with_result * 100.0 / max(total, 1):.0f}%)")
    print(f"스코어 양쪽 입력:     {with_score}")

    print("\n-- result 값 분포 --")
    for val, n in rows(conn, "SELECT result, COUNT(*) FROM matches GROUP BY result ORDER BY COUNT(*) DESC"):
        print(f"  {val!r}: {n}")

    print("\n-- 모드별 분포 (전체 / 승패입력) --")
    for mode, n_all, n_res in rows(
        conn,
        "SELECT mode, COUNT(*), SUM(CASE WHEN result IS NOT NULL THEN 1 ELSE 0 END) "
        "FROM matches GROUP BY mode",
    ):
        print(f"  {mode}: {n_all} / {n_res}")

    print("\n-- 날짜 범위 --")
    lo = scalar(conn, "SELECT MIN(match_date) FROM matches WHERE match_date IS NOT NULL")
    hi = scalar(conn, "SELECT MAX(match_date) FROM matches WHERE match_date IS NOT NULL")
    no_date = scalar(conn, "SELECT COUNT(*) FROM matches WHERE match_date IS NULL")
    print(f"  {lo} ~ {hi}  (날짜 NULL: {no_date})")

    print("\n-- 선수·스탯 규모 --")
    players = scalar(conn, "SELECT COUNT(*) FROM players")
    hp_rows = scalar(conn, "SELECT COUNT(*) FROM player_stats_hp")
    snd_rows = scalar(conn, "SELECT COUNT(*) FROM player_stats_snd")
    orphan_hp = scalar(
        conn,
        "SELECT COUNT(*) FROM player_stats_hp s LEFT JOIN matches m ON s.match_id=m.id "
        "WHERE m.id IS NULL OR m.result IS NULL",
    )
    orphan_snd = scalar(
        conn,
        "SELECT COUNT(*) FROM player_stats_snd s LEFT JOIN matches m ON s.match_id=m.id "
        "WHERE m.id IS NULL OR m.result IS NULL",
    )
    print(f"  등록 선수: {players}, HP 스탯행: {hp_rows} (승패 없는 매치 소속: {orphan_hp})")
    print(f"  SND 스탯행: {snd_rows} (승패 없는 매치 소속: {orphan_snd})")

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)
