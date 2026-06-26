# 구글 시트 → SQLite 일회성 import 스크립트
#
# 사용법:  python import_sheets.py
#
# 구글 시트의 Database_HP / Database_SND / Alias 를 읽어 codm.db 로 옮긴다.
# 같은 매치의 5명(또는 그 이상) 행을 날짜+모드 단위로 하나의 match로 묶어 저장한다.
# (구글 시트에는 match_id가 없으므로, 연속된 같은 날짜 그룹을 한 매치로 간주한다.)
#
# 주의: 재실행 시 중복을 막기 위해 DB를 매번 새로 만든다(기존 codm.db 삭제).

import os
import re
import sys
from datetime import datetime

import gspread
from dotenv import load_dotenv

load_dotenv()

import config
import db


def parse_date(raw: str):
    """구글 시트 날짜 문자열을 ISO(YYYY-MM-DD)로 변환. 실패 시 None.

    예) '2026. 3. 12' / '2026. 6. 5' / '2026-03-12'
    """
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    # 구글 시트 한국 포맷: "2026. 3. 12"
    m = re.match(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def to_int(v):
    try:
        return int(float(str(v).strip())) if str(v).strip() else None
    except (ValueError, TypeError):
        return None


def to_float(v):
    try:
        return float(str(v).strip()) if str(v).strip() else None
    except (ValueError, TypeError):
        return None


def _gspread_client():
    """환경에 따라 gspread 클라이언트 생성.
    - 배포: GOOGLE_SERVICE_ACCOUNT_JSON (JSON 내용 통째로) 사용
    - 로컬: GOOGLE_SERVICE_ACCOUNT_FILE (파일 경로) 사용
    """
    if config.SERVICE_ACCOUNT_JSON:
        from io import BytesIO
        import json
        return gspread.service_account_from_dict(json.loads(config.SERVICE_ACCOUNT_JSON))
    return gspread.service_account(filename=config.SERVICE_ACCOUNT_FILE)


def fetch_sheets():
    """구글 시트에서 HP/SND/Alias 원본 행 리스트를 가져온다."""
    gc = _gspread_client()
    ss = gc.open_by_key(config.SPREADSHEET_ID)

    hp_rows = ss.worksheet("Database_HP").get_all_values()
    snd_rows = ss.worksheet("Database_SND").get_all_values()
    alias_rows = ss.worksheet("Alias").get_all_values()
    # 첫 행(헤더) 제거
    return hp_rows[1:], snd_rows[1:], alias_rows[1:]


# 모드별 매치당 행 수.
# HP 시트는 4행(스크림 4인 체제), SND 시트는 5행(정규 5v5) 단위로 한 매치가 들어온다.
PLAYERS_PER_MATCH = {"HP": 4, "SND": 5}


# 선수 이름 정규화 맵 — 구글 시트에 대소문자가 섞여 있어 다른 선수로 인식되는 것을 방지.
# 표준 이름(소문자 기준 canonical)로 통일한다.
NAME_NORMALIZE = {
    "cartels": "Cartels",
    "unravel": "unravel",
    "shisui": "Shisui",
    "kingz": "Kingz",
    "maozyn": "Maozyn",
    "exile": "Exile",
    "ayeraph": "AyeoRaph",
    "swish": "Swish",
}


def normalize_name(name: str) -> str:
    """대소문자 무시 정규화. 'Unravel'/'unravel' → 'unravel', 'cartels'/'Cartels' → 'Cartels'."""
    if not name:
        return name
    key = name.strip().lower()
    return NAME_NORMALIZE.get(key, name.strip())


def _row_fields(row, mode):
    """HP/SND 컬럼 인덱스 차이를 흡수해서 공통 필드를 뽑는다."""
    if mode == "HP":
        return {
            "ign": (row[0] if len(row) > 0 else "").strip(),
            "actual": (row[1] if len(row) > 1 else "").strip(),
            "date_raw": (row[10] if len(row) > 10 else "").strip(),
            "map": (row[11] if len(row) > 11 else "").strip(),
        }
    # SND
    return {
        "ign": (row[0] if len(row) > 0 else "").strip(),
        "actual": (row[1] if len(row) > 1 else "").strip(),
        "date_raw": (row[11] if len(row) > 11 else "").strip(),
        "map": (row[12] if len(row) > 12 else "").strip(),
    }


def group_matches(rows, mode):
    """선수 이름 반복을 기준으로 매치를 분리한다.

    구글 시트의 HP/SND 데이터는 한 매치의 선수들이 연속된 행으로 들어오고,
    다음 매치는 다시 첫 선수부터 반복되는 패턴을 가진다.
    (예: Cartels→Unravel→Shisui→Maozyn | Cartels→Unravel→... )
    따라서 "이전 매치에 이미 등장한 선수가 다시 나오면 새 매치 시작"으로 분리한다.
    한 날짜에 매치 인원수가 4명/5명으로 바뀌어도 정확히 분리된다.

    반환: list of (date_raw, map_hint, [player_rows])
    """
    # 유효한(이름이 있는) 행만 먼저 필터
    valid = []
    for row in rows:
        f = _row_fields(row, mode)
        if f["ign"] or f["actual"]:
            valid.append(row)

    matches = []
    current = []
    seen_in_current = set()

    for row in valid:
        f = _row_fields(row, mode)
        name = normalize_name(f["actual"] or f["ign"])
        # 현재 매치에 이미 있는 선수가 또 나오면 → 새 매치 시작
        if name and name in seen_in_current:
            matches.append(_finalize_match(current, mode))
            current = []
            seen_in_current = set()
        current.append(row)
        if name:
            seen_in_current.add(name)

    if current:
        matches.append(_finalize_match(current, mode))

    return matches


def _finalize_match(player_rows, mode):
    """한 매치의 행들에서 대표 date/map을 뽑아 튜플로 반환."""
    date_raw = ""
    map_name = ""
    for r in player_rows:
        f = _row_fields(r, mode)
        if not date_raw and f["date_raw"]:
            date_raw = f["date_raw"]
        if not map_name and f["map"]:
            map_name = f["map"]
    return (date_raw, map_name or None, player_rows)


def insert_aliases(conn, alias_rows):
    """Alias 시트 → players + aliases."""
    n = 0
    for row in alias_rows:
        if len(row) < 2:
            continue
        ign = (row[0] or "").strip()
        actual = (row[1] or "").strip()
        if not ign or not actual:
            continue
        pid = db.resolve_player_id(conn, actual, ign_raw=ign)
        n += 1
    return n


def insert_stat_rows(conn, rows, mode):
    """HP/SND 행들을 matches + player_stats_* 테이블로 저장."""
    n_matches = 0
    n_stats = 0

    for date_raw, map_hint, player_rows in group_matches(rows, mode):
        iso_date = parse_date(date_raw)
        match_id = conn.execute_returning_id(
            "INSERT INTO matches(mode, map_name, match_date, raw_date) VALUES (?,?,?,?)",
            (mode, map_hint, iso_date, date_raw or None),
        )
        n_matches += 1

        for row in player_rows:
            f = _row_fields(row, mode)
            ign = f["ign"]
            actual = normalize_name(f["actual"] or ign)  # 대소문자 정규화 + actual 비면 IGN
            name_for_id = actual or normalize_name(ign)
            pid = db.resolve_player_id(conn, name_for_id, ign_raw=ign if ign and normalize_name(ign) != actual else None)

            if mode == "HP":
                conn.upsert(
                    "player_stats_hp",
                    ["match_id", "player_id", "ign_raw", "kills", "deaths", "kd_ratio",
                     "obj_time", "score", "impact", "total_damage", "capture_kill"],
                    (
                        match_id, pid, ign or None,
                        to_int(row[2]) if len(row) > 2 else None,
                        to_int(row[3]) if len(row) > 3 else None,
                        to_float(row[4]) if len(row) > 4 else None,
                        to_int(row[5]) if len(row) > 5 else None,   # OBJ(time)
                        to_int(row[6]) if len(row) > 6 else None,
                        to_float(row[7]) if len(row) > 7 else None,
                        to_int(row[8]) if len(row) > 8 else None,
                        to_int(row[9]) if len(row) > 9 else None,
                    ),
                    conflict_col="match_id, player_id",
                    update_cols=["ign_raw", "kills", "deaths", "kd_ratio",
                                 "obj_time", "score", "impact", "total_damage", "capture_kill"],
                )
            else:  # SND
                conn.upsert(
                    "player_stats_snd",
                    ["match_id", "player_id", "ign_raw", "kills", "deaths", "assists",
                     "kd_ratio", "score", "impact", "adr", "first_kill", "lone_wolf_win"],
                    (
                        match_id, pid, ign or None,
                        to_int(row[2]) if len(row) > 2 else None,
                        to_int(row[3]) if len(row) > 3 else None,
                        to_int(row[4]) if len(row) > 4 else None,
                        to_float(row[5]) if len(row) > 5 else None,
                        to_int(row[6]) if len(row) > 6 else None,
                        to_float(row[7]) if len(row) > 7 else None,
                        to_float(row[8]) if len(row) > 8 else None,
                        to_int(row[9]) if len(row) > 9 else None,
                        to_int(row[10]) if len(row) > 10 else None,
                    ),
                    conflict_col="match_id, player_id",
                    update_cols=["ign_raw", "kills", "deaths", "assists", "kd_ratio",
                                 "score", "impact", "adr", "first_kill", "lone_wolf_win"],
                )
            n_stats += 1

    return n_matches, n_stats


def main():
    # 배포 환경(railway run)에서는 DATABASE_URL 이 주입되어 Postgres 로 동작.
    # 로컬에서는 codm.db (SQLite) 로 동작.
    using_pg = db.USE_POSTGRES
    target = "Postgres" if using_pg else f"SQLite ({db.DB_PATH})"
    print(f"== 구글 시트 → {target} 마이그레이션 ==")

    if not using_pg:
        # 로컬 SQLite: 기존 파일 삭제 후 새로 생성 (중복 방지)
        if os.path.exists(db.DB_PATH):
            os.remove(db.DB_PATH)
            print(f"기존 DB 삭제: {db.DB_PATH}")
    else:
        # Postgres: 스키마만 보장 (데이터는 이미 비어 있다고 가정;
        # 재실행 시 중복이 생기지 않도록 upsert 사용)
        print("Postgres 모드 — 기존 데이터는 upsert 로 갱신됩니다")

    db.init_db()
    print(f"DB 준비 완료: {target}")

    print("구글 시트 읽는 중...")
    hp_rows, snd_rows, alias_rows = fetch_sheets()
    print(f"  HP: {len(hp_rows)}행, SND: {len(snd_rows)}행, Alias: {len(alias_rows)}행")

    with db.get_conn() as conn:
        n_alias = insert_aliases(conn, alias_rows)
        print(f"Alias: {n_alias}건 등록")

        n_hp_m, n_hp_s = insert_stat_rows(conn, hp_rows, "HP")
        print(f"HP: 매치 {n_hp_m}건, 스탯 {n_hp_s}행")

        n_snd_m, n_snd_s = insert_stat_rows(conn, snd_rows, "SND")
        print(f"SND: 매치 {n_snd_m}건, 스탯 {n_snd_s}행")

        # 검증 요약
        print()
        print("== 결과 요약 ==")
        for q in [
            ("players", "SELECT COUNT(*) c FROM players"),
            ("aliases", "SELECT COUNT(*) c FROM aliases"),
            ("matches", "SELECT COUNT(*) c FROM matches"),
            ("matches(HP)", "SELECT COUNT(*) c FROM matches WHERE mode='HP'"),
            ("matches(SND)", "SELECT COUNT(*) c FROM matches WHERE mode='SND'"),
            ("player_stats_hp", "SELECT COUNT(*) c FROM player_stats_hp"),
            ("player_stats_snd", "SELECT COUNT(*) c FROM player_stats_snd"),
        ]:
            c = conn.execute(q[1]).fetchone()["c"]
            print(f"  {q[0]:<16}: {c}")

    print()
    print("완료!")


if __name__ == "__main__":
    main()
