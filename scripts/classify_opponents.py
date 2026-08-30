# 상대팀 로스터 선입력 → 기존 OCR enemy 선수 분류·병합·매치 귀속 (재사용 스크립트).
#
# 사용:
#   python scripts/classify_opponents.py           # 드라이런 (계획만 출력, DB 변경 없음)
#   python scripts/classify_opponents.py --apply   # 실제 반영
#
# 단계:
#   1) TEAMS 명단대로 opponent_teams / 로스터 선수 등록 (source='manual')
#   2) 기존 opponent_players(스크린샷 OCR로 쌓인 변형)를 로스터명에 매칭
#      - 매칭 키: NFKC → 괄호 제거 → 선행 팀태그 제거 → OCR 숫자 음역(1→i 등)
#        → 영숫자 → 끝의 레벨 숫자 제거. 태그 유무와 무관하게 [전체키, 태그떼기키]
#        두 가지로 비교해 최고 점수 사용.
#      - AUTO(≥0.75 & 마진≥0.05): 변형들을 canonical로 병합(스탯·alias 흡수) 후
#        표기명을 로스터명으로 정규화. REVIEW(≥0.60): 출력만 하고 건드리지 않음.
#      - 다른 팀 태그가 붙은 행은 그 팀 후보로 절대 병합 안 함.
#   3) 태그는 인식되지만 로스터명에 없는 선수(sub/게스트) → 해당 팀 로스터에
#      source='match'로 추가 (이름 변경 없음 — 스코어보드 태그가 진실).
#   4) enemy 스탯이 있는 매치의 opponent_team_id를 다수결(identify_opponent_team)로
#      소급 귀속 → /versus H2H에 반영.
import difflib
import re
import sys
import unicodedata

ROOT = __file__.rsplit("\\", 2)[0] if "\\" in __file__ else "/".join(__file__.split("/")[:-2])
sys.path.insert(0, ROOT)

# ── 코치 선입력 명단 (여기만 수정하고 재실행하면 증분 반영) ─────────────────
TEAMS = {
    "uD (unDream)":    ["Shane", "Swish", "Legacy", "Puedes", "Dakoda"],
    "KYA (KYA Nation)": ["AmPrayer", "Polel", "Blez", "Rush", "Fabuloso", "Piti"],
    "AMG (Amigos)":    ["R4F4", "Sapuka", "Spadez", "KiNg", "Krozin", "Zeus"],
    "ANM (Animus)":    ["Guithila", "Naarkz", "Sh4Rk", "Saturn", "Kayru"],
    "EXCL (Exclusive)": ["vere", "Neil", "Sawo", "Saze", "wCeesarr", "Lighty"],
    "GodL (Godlike)":  ["Learn", "Abhiz", "Prevail", "SkullG", "Warden", "Viper"],
    "PDX (Paradox)":   ["8PL", "Darroks", "Eyur", "Karizma", "Mxntra", "Ruin"],
    "WT (Wanted)":     ["Bellingham", "AxiSz", "Mute", "Chxmpi", "Sanic"],
    "xT":              ["Badu", "Galleta", "gVo", "Waze", "Yuji"],
}
TAGS = ["uD", "KYA", "AMG", "ANM", "EXCL", "GodL", "PDX", "WT", "xT"]

AUTO_T, REVIEW_T, MARGIN = 0.75, 0.60, 0.05
TRANSLIT = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b"})

# ── 배포 DB 직접 연결 (db.py import 전에 환경변수) ──────────────────────────
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402

if not os.environ.get("DATABASE_URL"):
    out = subprocess.run(
        "railway variables --service Postgres --json",
        capture_output=True, text=True, shell=True, check=True).stdout
    os.environ["DATABASE_URL"] = json.loads(out)["DATABASE_PUBLIC_URL"]
    print("배포 Postgres 공개 URL로 연결", flush=True)

import db  # noqa: E402


def split_tag(s: str):
    """(태그, 나머지) 분리: 'uD Shane', 'AmG.KiNg', 'GodLAbh1z' 형태 모두.
    붙여쓰기(구분자 없음)는 다음 글자가 대문자일 때만 — 'XTjr' 같은 오탈자 방지."""
    low = s.lower()
    for t in sorted(TAGS, key=len, reverse=True):
        for sep in (" ", ".", "-", "_"):
            pre = t.lower() + sep
            if low.startswith(pre) and len(s) > len(pre):
                return t, s[len(pre):]
        if low.startswith(t.lower()) and len(s) > len(t) and s[len(t)].isupper():
            return t, s[len(t):]
    return None, s


def keys_for(raw: str) -> list:
    """OCR 표기 → 비교키 후보 ([전체, 태그떼기] 조합, 중복 제거)."""
    s = unicodedata.normalize("NFKC", (raw or "").strip())
    s = re.sub(r"\([^)]*\)", "", s)                      # 괄호 주석 (Shane(Shane))
    s = re.sub(r"[^\x00-\x7F]", "", s)                   # 상표/위첨자 아이콘 (ᴳ 등)
    parts = s.split(None, 1)
    bases = {s, parts[1] if len(parts) > 1 else s, split_tag(s)[1]}
    out = set()
    for base in bases:
        k = base.lower().translate(TRANSLIT)
        k = re.sub(r"[^a-z0-9]+", "", k)
        k = re.sub(r"\d+$", "", k)                       # 끝의 레벨 배지 숫자
        if len(k) >= 2:
            out.add(k)
    return list(out)


def sim(name_roster: str, raw: str) -> float:
    """로스터명 ↔ OCR 표기 유사도 (양쪽 모두 키화 후 최고 조합)."""
    best = 0.0
    for kr in keys_for(name_roster):
        for kc in keys_for(raw):
            if kr == kc:
                return 1.0
            best = max(best, difflib.SequenceMatcher(None, kr, kc).ratio())
    return best


def row_tag(raw: str):
    """행 이름의 선행 팀태그. 없으면 None."""
    s = unicodedata.normalize("NFKC", (raw or "").strip())
    return split_tag(s)[0]


def build_plan(conn):
    """읽기 전용으로 전체 계획 수립. 반환: (team_plans, tag_extras, review, unmatched)
    이미 로스터에 등록된 선수는 제외 — 이름 정규화로 태그가 사라진 canonical이
    재매칭 풀에 들어가 타팀 유사명(Rush↔Ruin 등)과 오병합되는 것을 방지."""
    players = conn.execute(
        "SELECT id, name FROM opponent_players ORDER BY id").fetchall()
    rostered = {r["player_id"] for r in conn.execute(
        "SELECT player_id FROM opponent_team_rosters").fetchall()}
    avail = {p["id"]: p["name"] for p in players if p["id"] not in rostered}
    team_plans, tag_extras, review = {}, [], []

    for team_name, roster in TEAMS.items():
        tag = next(t for t in TAGS if team_name.lower().startswith(t.lower()))
        plan = []
        for roster_name in roster:
            scored = []
            for pid, raw in avail.items():
                if row_tag(raw) not in (None, tag):
                    continue                              # 다른 팀 태그 — 금지
                s = sim(roster_name, raw)
                if s >= REVIEW_T:
                    scored.append((s, pid, raw))
            scored.sort(reverse=True)
            if not scored:
                plan.append({"roster": roster_name, "action": "create"})
                continue
            # 같은 태그(또는 무태그) 풀 안의 ≥AUTO_T 행은 전부 같은 선수의 변형으로
            # 간주해 병합한다 — 다수 동점이 '경쟁 후보'가 아니라 '변형'이므로
            # 마진 검사는 생략 (다른 팀 태그는 위에서 이미 차단).
            if scored[0][0] >= AUTO_T:
                variants = [p for p in scored if p[0] >= AUTO_T]
                # canonical: 이름이 가장 짧은 것 (가장 깨끗한 표기)
                variants.sort(key=lambda p: (len(p[2]), -p[0]))
                canon = variants[0]
                others = [p for p in variants if p[1] != canon[1]]
                for p in others:
                    avail.pop(p[1], None)
                avail.pop(canon[1], None)
                plan.append({"roster": roster_name, "action": "merge",
                             "canonical": canon, "variants": others})
            else:
                review.append((team_name, roster_name,
                               [(round(s, 2), raw) for s, _pid, raw in scored[:3]]))
                plan.append({"roster": roster_name, "action": "create"})
        team_plans[team_name] = {"tag": tag, "plan": plan}

    # 태그 인식 잔여 → sub/게스트로 팀 로스터에 추가
    for pid, raw in list(avail.items()):
        t = row_tag(raw)
        if t:
            tag_extras.append((t, pid, raw))
            avail.pop(pid, None)
    unmatched = [(pid, raw) for pid, raw in sorted(avail.items())]
    return team_plans, tag_extras, review, unmatched


def apply_plan(conn, team_plans, tag_extras):
    # 1) 팀 등록
    team_ids = {}
    for team_name in TEAMS:
        row = conn.execute(db._adapt_sql(
            "SELECT id FROM opponent_teams WHERE name = ?"), (team_name,)).fetchone()
        if row:
            team_ids[team_name] = row["id"]
        else:
            team_ids[team_name] = conn.execute_returning_id(
                "INSERT INTO opponent_teams(name) VALUES (?)", (team_name,))
            print(f"  팀 등록: {team_name} (id={team_ids[team_name]})")

    # 2) 로스터: 병합(변형 흡수) → 이름 정규화 → 로스터 등록 → 신규 생성
    for team_name, tp in team_plans.items():
        tid = team_ids[team_name]
        for item in tp["plan"]:
            roster_name = item["roster"]
            if item["action"] == "merge":
                canon_id, canon_raw = item["canonical"][1], item["canonical"][2]
                for _s, vid, vraw in item["variants"]:
                    db.merge_opponent_player(vid, canon_id)
                    print(f"  병합: '{vraw}' → {roster_name}")
                # 표기 정규화 (충돌 없을 때만)
                clash = conn.execute(db._adapt_sql(
                    "SELECT 1 FROM opponent_players WHERE name = ? AND id <> ?"),
                    (roster_name, canon_id)).fetchone()
                if not clash:
                    db._learn_opponent_alias(conn, canon_raw, canon_id, "Manual")
                    conn.execute(db._adapt_sql(
                        "UPDATE opponent_players SET name = ? WHERE id = ?"),
                        (roster_name, canon_id))
                pid = canon_id
            else:
                # 이미 같은 이름의 선수가 있으면(재실행 등) 재사용 — UNIQUE 충돌 방지
                row = conn.execute(db._adapt_sql(
                    "SELECT id FROM opponent_players WHERE name = ?"),
                    (roster_name,)).fetchone()
                pid = row["id"] if row else conn.execute_returning_id(
                    "INSERT INTO opponent_players(name) VALUES (?)", (roster_name,))
            conn.upsert("opponent_team_rosters",
                        ["team_id", "player_id", "source"], (tid, pid, "manual"),
                        conflict_col="team_id, player_id")
            print(f"  로스터: {team_name} + {roster_name} (pid={pid})")

    # 3) 태그 잔여 → sub/게스트 로스터 추가
    tag_of = {tp["tag"]: name for name, tp in team_plans.items()}
    for tag, pid, raw in tag_extras:
        conn.upsert("opponent_team_rosters",
                    ["team_id", "player_id", "source"],
                    (team_ids[tag_of[tag]], pid, "match"),
                    conflict_col="team_id, player_id")
        print(f"  sub/게스트: {tag} + '{raw}' (pid={pid})")

    # 4) 매치 소급 귀속 (다수결)
    mids = [r["match_id"] for r in conn.execute(db._adapt_sql(
        "SELECT DISTINCT match_id FROM opponent_stats_hp UNION "
        "SELECT DISTINCT match_id FROM opponent_stats_snd")).fetchall()]
    attributed = 0
    for mid in mids:
        row = conn.execute(db._adapt_sql(
            "SELECT opponent_team_id FROM matches WHERE id = ?"), (mid,)).fetchone()
        if not row or row["opponent_team_id"] is not None:
            continue
        names = []
        for tbl in ("opponent_stats_hp", "opponent_stats_snd"):
            names += [r["ign_raw"] for r in conn.execute(db._adapt_sql(
                f"SELECT ign_raw FROM {tbl} WHERE match_id = ?"), (mid,)).fetchall()]
        team_id = db.identify_opponent_team(conn, names)
        if team_id:
            conn.execute(db._adapt_sql(
                "UPDATE matches SET opponent_team_id = ? WHERE id = ?"), (team_id, mid))
            attributed += 1
    print(f"  매치 팀 귀속: {attributed}매치")


def main():
    apply = "--apply" in sys.argv
    with db.get_conn() as conn:
        team_plans, tag_extras, review, unmatched = build_plan(conn)

    print(f"\n===== 계획 ({'적용' if apply else '드라이런'}) =====")
    for team_name, tp in team_plans.items():
        merges = [i for i in tp["plan"] if i["action"] == "merge"]
        creates = [i["roster"] for i in tp["plan"] if i["action"] == "create"]
        print(f"\n[{team_name}]")
        for m in merges:
            vs = ", ".join(f"'{v[2]}'({v[0]:.2f})" for v in m["variants"])
            print(f"  {m['roster']} ← canonical '{m['canonical'][2]}'"
                  f"({m['canonical'][0]:.2f})" + (f" + 변형: {vs}" if vs else ""))
        if creates:
            print(f"  신규 등록(매칭 없음): {', '.join(creates)}")
    if tag_extras:
        print("\n[sub/게스트 — 태그로 팀 추가]")
        for tag, pid, raw in tag_extras:
            print(f"  {tag}: '{raw}' (pid={pid})")
    if review:
        print("\n[REVIEW — 애매해서 건드리지 않음]")
        for team_name, roster_name, cands in review:
            print(f"  {team_name} {roster_name}: 후보 {cands}")
    if unmatched:
        print("\n[미분류 — 알 수 없는 팀/OCR 깨짐]")
        for pid, raw in unmatched:
            print(f"  pid={pid} '{raw}'")

    if not apply:
        print("\n드라이런 완료 — DB 변경 없음. --apply로 반영.")
        return
    with db.get_conn() as conn:
        apply_plan(conn, team_plans, tag_extras)
    print("\n적용 완료.")


if __name__ == "__main__":
    main()
