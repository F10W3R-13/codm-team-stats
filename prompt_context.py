# CODM 도메인 컨텍스트 (Domain Context for AI Prompts)
#
# 이 팀의 코칭 VOD 전사문 4샘플(~4,900줄) 분석 결과를 바탕으로,
# GPT가 "CODM 팀 코치의 시각"으로 인사이트/요약을 생성하도록 도메인 지식을 주입한다.
#
# 갱신 3계층:
#   - 정적 (수동): 게임 메타·전술 용어·코칭 톤·발음변형 맵·맵 메타
#     → 새 전사문 누적·CODM 시즌 패치 시 이 파일 편집. scripts/refresh_domain_context.py가 제안.
#   - 동적 (자동): 팀 로스터·역할·스탯 → 매 호출마다 DB에서 조회.
#   - 시점 (자동): 현재 날짜 → 메타 시점 고정.
#
# analytics_insights.py의 모든 GPT 호출이 build_system_prompt()를 거친다.

import datetime

# 전사문 발음 오류 매핑 (OCR/Alias 스킬과 연계)
# refresh_domain_context.py 실행으로 새 변형을 발견해 여기에 추가.
_PLAYER_IGN_MAP = {
    "Shisui": ["Shizi", "she-she", "she she", "Shishi", "Shisi", "Chisu", "Shane",
               "쉬스이", "시스이"],
    "Maozyn": ["Mao", "Maozen", "Mazin", "Maoz", "마오진", "마오즌"],
    "Cartels": ["Cartel", "cartilage", "cartos", "카르텔"],
    "Kingz": ["Kings", "King", "Kingsui", "킹즈"],
    "Exile": ["Exhale", "엑자일"],
    "unravel": ["Unravel", "언래블"],
}

# 맵별 tendency (VOD에서 반복 논의된 핵심 플랜)
_MAP_META = {
    "Combine": "P3 스폰 통제가 핵심. 언덕 전환마다 스폰 사이드가 결과 좌우.",
    "Summit": "P3/P4에서 스폰이 결정적. War Machine을 P2에 배치해 가치 극대화 권장.",
    "Standoff": "S&D 공수 밸런스. 콜아웃 밀도가 승패를 가름.",
    "Raid": "거점 회전 속도전. AR의 진입 타이밍이 중요.",
    "Arsenal": "P2 확보 시 yellow spawn 필수.",
}

_STATIC_DOMAIN_CONTEXT = """# CODM Team Coaching Domain Guide

You are advising a competitive Call of Duty Mobile (CODM) team. Use this domain knowledge to ground every insight in real game understanding.

## Game & Modes
CODM competitive uses two modes:
- HP (Hardpoint / 거점): capture rotating hills P1→P2→P3→P4, ~60s each. OBJ = hill time in seconds (higher = better). CapKill = bonus-score kills (multikills, trades, top-enemy kills, in-hill kills) — NOT pure objective time. "hill"/"언덕" = the current active point. "hill time" = 거점 시간.
- SND (Search & Destroy / 폭파): alternating attack/defense, round-based. FK = First Blood (first kill), LWW = Lone Wolf Win, ADR = avg damage per round.

## Key Metric Benchmarks (interpret numbers, don't just list them)
- K/D: ~1.0 average, 1.3+ strong, <0.8 weak.
- ZCS (HP only) = max(0, 1.1·OBJ + 8·CapKill + 4.1·K − 5·D). Team avg ~150–200; 250+ = ace-level zone control; <100 = low impact. High ZCS = strong hill control + kill contribution.
- DPK (dmg/kills): LOWER is better (less damage needed per kill = finishing ability). ~700–1100.
- DPD (dmg/deaths): HIGHER is better (more value per life). ~800–1300.
- Impact: composite contribution (0–200 cap). 150+ = excellent.
- OBJ time (HP): seconds on hill — high = objective contribution.

## Roles / Positions (CODM meta)
- AR (assault rifle): primary slayer role, high kills/damage share. ≈ slayer.
- OBJ / anchor (옵 / 앵커): hill defense & capture, high OBJ/CapKill share.
- sniper: long-range control, info + picks.
- balanced / flex: even contribution.
- IGL (In-Game Leader): in-game shotcaller, usually a veteran (e.g. Cartels).
- entry: takes first contact on push (SND first-kill adjacent).

## Tactical Terms (as actually used in VOD/transcripts)
- spawn (스폰): respawn location. "flip spawn", "secure spawn", "spawn trap".
- push (푸시): drive into enemy territory.
- rotation (로테): move to the next hill.
- retake (리테): recapture a lost hill.
- trade (교환): teammate dies → ally avenges. "2 for 2" = even trade. High trade ratio = team focus.
- flank (플랭크): side attack.
- pinch (핀치): squeeze from two sides.
- hold (홀드): lock down a position.
- peek / peak (피크): aim around cover. "wide peek", "jiggle".
- head glitch: cover showing only head (advantageous angle).
- hill / point: current hardpoint. "money hill" = highest-value scoring point.
- momentum: kill-streak flow.

## CODM Mechanics
- scorestreak / operator: score-triggered abilities. Tempest (lightning pistol), War Machine (grenade launcher), Equalizer (minigun), Death Machine, Sparrow (bow), UAV.
- trophy (트로피): equipment that neutralizes scorestreaks.
- Meta awareness: Tempest was 6 rounds + strong aim-assist (overpowered) → now 4 rounds + countered by 2 trophies. Judge meta by the current date provided.
- halftime (하프타임): HP first/second half transition.

## Coaching Tone
- Coach phrasing: reason-attached directives ("we have to ~ because ~"), suggestions ("let's try"), hypotheses ("maybe ~").
- Philosophy: "there's no right answer in Hardpoint, only tendencies." Seek middle ground, not absolutes.
- Constructive feedback, psychological safety ("safe place").
- BRIDGE quantitative stats with qualitative VOD observation — explain WHY a number matters tactically.
- Refine slang/profanity (bro, man, fuck) into a clean coaching register — convey the point without vulgarity.
"""


def _format_ign_map() -> str:
    """발음 변형 맵을 GPT가 읽을 텍스트로 포맷."""
    if not _PLAYER_IGN_MAP:
        return ""
    lines = ["", "## Player Name Variants (transcript/voice pronunciation drift)"]
    for ign, variants in _PLAYER_IGN_MAP.items():
        if variants:
            lines.append(f"- {ign}: {', '.join(variants)}")
    lines.append("When you see a variant in a transcript, treat it as the formal IGN and use the formal name in output.")
    return "\n".join(lines)


def _format_map_meta() -> str:
    """맵별 tendency를 텍스트로 포맷."""
    if not _MAP_META:
        return ""
    lines = ["", "## Map Tendencies (team's observed plans)"]
    for map_name, tip in _MAP_META.items():
        lines.append(f"- {map_name}: {tip}")
    return "\n".join(lines)


def team_roster_context() -> str:
    """동적 팀 로스터 (DB에서 자동 조회).

    all_players_overview("HP") + classify_role()로 현재 로스터·역할·평균 스탯을 가져옴.
    새 선수 영입·역할 변경·스탯 변화는 DB 반영 즉시 자동 반영.
    조회 실패 시 빈 문자열 (정적 컨텍스트만으로 동작).
    """
    try:
        import queries
        import metrics
        players = queries.all_players_overview("HP")
        team_avg = queries.team_averages("HP")
        if not players:
            return ""
        lines = ["", f"## Current Team Roster (HP, as of {datetime.date.today().isoformat()})"]
        for p in players[:8]:
            name = p.get("name")
            matches = p.get("matches", 0)
            kd = p.get("avg_kd")
            # all_players_overview는 avg_ck로 반환 → classify_role 호환을 위해 복사
            p_norm = dict(p)
            if "avg_ck" in p_norm and "avg_capture" not in p_norm:
                p_norm["avg_capture"] = p_norm["avg_ck"]
            role = metrics.classify_role(p_norm, team_avg) if team_avg else "balanced"
            lines.append(
                f"- {name} — {role}, {matches} HP matches, avg K/D {kd}"
            )
        return "\n".join(lines)
    except Exception:
        return ""


def build_system_prompt(task: str, lang: str = "ko") -> str:
    """모든 AI 호출용 system 프롬프트 조합.

    정적 도메인 컨텍스트 + IGN 변형 맵 + 맵 메타 + 현재 날짜 + 동적 로스터 + 작업별 지시문.
    task: 각 함수의 개별 지시문 (길이·포커스). lang: ko/en/es.
    """
    today = datetime.date.today().isoformat()
    lang_note = {"ko": "Korean (한국어)", "en": "English", "es": "Spanish (español)"}.get(lang, "Korean (한국어)")
    parts = [
        _STATIC_DOMAIN_CONTEXT,
        _format_ign_map(),
        _format_map_meta(),
        f"\n## Current Date (meta snapshot): {today}",
        team_roster_context(),
        f"\n## Task\n{task}",
        f"\nRespond in {lang_note}.",
    ]
    return "\n".join(parts)
