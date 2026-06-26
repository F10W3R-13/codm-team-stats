# 일회성: 퇴단 선수 데이터 삭제
#
# 사용법:
#   로컬(SQLite):  python scripts/remove_player.py
#   Postgres:      DATABASE_URL=... python scripts/remove_player.py
#
# 매치 자체는 유지하고 해당 선수의 스탯/alias/players 행만 삭제 (FK 순서 준수).
# 스탯이 지워진 매치는 다른 선수들의 기록은 그대로 남음.

import sys
import os

# 프로젝트 루트를 path에 추가 (scripts/ 안에서 실행해도 동작)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

PLAYER_NAME = "AyeoRaph"  # 정확한 이름 (대소문자 구분 주의)


def remove_player(name: str):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM players WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            # 대소문자 무시로 재시도 (Postgres는 ILIKE 필요 — 직접 처리)
            if db.USE_POSTGRES:
                row = conn.execute(
                    "SELECT id FROM players WHERE name ILIKE %s", (name,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM players WHERE name = ? COLLATE NOCASE", (name,)
                ).fetchone()
        if not row:
            print(f"선수 '{name}' 을(를) 찾을 수 없습니다")
            return False
        pid = row["id"]

        # FK 순서: stats → aliases → players
        hp_n = conn.execute(
            "SELECT COUNT(*) c FROM player_stats_hp WHERE player_id=?", (pid,)
        ).fetchone()["c"]
        snd_n = conn.execute(
            "SELECT COUNT(*) c FROM player_stats_snd WHERE player_id=?", (pid,)
        ).fetchone()["c"]
        alias_n = conn.execute(
            "SELECT COUNT(*) c FROM aliases WHERE player_id=?", (pid,)
        ).fetchone()["c"]

        conn.execute("DELETE FROM player_stats_hp  WHERE player_id=?", (pid,))
        conn.execute("DELETE FROM player_stats_snd WHERE player_id=?", (pid,))
        conn.execute("DELETE FROM aliases            WHERE player_id=?", (pid,))
        conn.execute("DELETE FROM players            WHERE id=?",         (pid,))

        print(f"삭제 완료: {name} (id={pid})")
        print(f"  player_stats_hp  : {hp_n}행")
        print(f"  player_stats_snd : {snd_n}행")
        print(f"  aliases          : {alias_n}행")
        return True


if __name__ == "__main__":
    target = "Postgres" if db.USE_POSTGRES else f"SQLite ({db.DB_PATH})"
    print(f"== {target} : '{PLAYER_NAME}' 삭제 ==")
    remove_player(PLAYER_NAME)
