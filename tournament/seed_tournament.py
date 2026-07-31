"""대회 시드 스크립트 — 표준명을 players 메인으로, IGN을 alias로 등록.

이렇게 하면:
- 화면/순위표엔 깔끔한 표준명(Karpe, 지호, Guri)이 뜸
- GPT가 스크린샷에서 읽은 IGN(Fz.Karpe, 桜雅, Guri狸)이 alias로 매칭됨
- 클랜태그 유무와 무관하게 둘 다 매칭 (안전망)
"""
import db

# 표준명 → IGN 매핑 (표준명이 players 메인, IGN이 alias)
SEED = [
    ("Team Virtual", [
        ("Ichi",   "V1 Ichi"),
        ("Acedia", "V1 Acedia"),
        ("Annoxi", "V1 Annoxi"),
        ("Zodiac", "V1 Zodiac"),
        ("Syniez", "V1 Syniez"),
        ("Rush9",  "V1 Rush9"),
    ]),
    ("Team Fabriz", [
        ("Karpe",  "Fz.Karpe"),
        ("Sica",   "Fz.Sica"),
        ("Bang",   "Fz.Bang"),
        ("Serebi", "Fz.Serebi"),
        ("Uhoo",   "Fz.Uhoo"),
        ("Gamdo",  "Fz.Gamdo"),
    ]),
    ("Calorys", [
        ("LL",        "CLRS.LL"),
        ("LaToon",    "CLRS.LaToon"),
        ("Ryojo",     "CLRS.Ryojo"),
        ("Fomalhaut", "CLRS.Fomalhaut"),
        ("CMa",       "CLRS.CMa"),
        ("박민재",     "CLRS.박민재"),
    ]),
    ("4uNion", [
        ("지호",    "桜雅"),
        ("Vexter",  "4uNi.Vexter"),
        ("LoseJai", "4uNi.LoseJai"),
        ("Limit",   "4uNi.Limit"),
        ("xsn1x",   "4uNi.xsn1x"),
    ]),
    ("YetoTense", [
        ("소액",   "OrochiM4RU"),   # 본명 소액 (IGN OrochiM4RU)
        ("상준",   "Madara"),       # 본명 상준
        ("해파리", "Itachi"),       # 본명 해파리
        ("자갈치", "Hashirama"),    # 본명 자갈치
        ("리그렛", "Hiruzen"),      # 본명 리그렛
        ("민구리", "Guri狸"),       # 본명 민구리
    ]),
]


def main():
    import sys
    import sqlite3
    db.init_db()
    conn = sqlite3.connect(db.DEFAULT_PATH)

    # 안전장치: 이미 매치 데이터가 있으면 초기화 중단 (데이터 보호)
    match_count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    if match_count > 0:
        force = "--force" in sys.argv
        if not force:
            conn.close()
            print("=" * 60)
            print(f"⚠️  이미 {match_count}개의 매치가 기록되어 있습니다!")
            print("   매치 데이터가 전부 날아갑니다. 정말 초기화하려면:")
            print("   python seed_tournament.py --force")
            print()
            print("   선수만 추가/교체하려면 admin(매치 기록 페이지)이나")
            print("   수동 DB 편집을 사용하세요.")
            print("=" * 60)
            sys.exit(1)
        print(f"⚠️  --force: {match_count}개 매치 포함 전체 초기화 진행\n")

    conn.executescript("""
        DELETE FROM player_stats_hp;
        DELETE FROM player_stats_snd;
        DELETE FROM aliases;
        DELETE FROM players;
        DELETE FROM matches;
        DELETE FROM teams;
    """)
    conn.commit()
    conn.close()
    print("기존 데이터 초기화 완료\n")

    for i, (team_name, roster) in enumerate(SEED):
        tid = db.insert_team(team_name, seed=i + 1)
        print(f"[{team_name}] (id={tid})")
        for std, ign in roster:
            pid = db.insert_player(std, tid)
            db.insert_alias(ign, pid)        # IGN을 alias로
            if std != ign:
                db.insert_alias(std, pid)    # 표준명도 alias로 (이중 매칭 안전망)
            marker = " ← IGN 다름" if std != ign else ""
            print(f"    표준={std:<12} IGN={ign}{marker}")
        print()

    # 검증
    teams = db.list_teams()
    players = db.list_players()
    print(f"✅ 시드 완료: 팀 {len(teams)}개 · 선수 {len(players)}명")
    for t in teams:
        ps = db.list_players(t["id"])
        print(f"    {t['name']}: {[p['name'] for p in ps]}")


if __name__ == "__main__":
    main()
