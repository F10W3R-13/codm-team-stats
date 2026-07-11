# CODM 도메인 컨텍스트 (Domain Context for AI Prompts)
#
# 이 팀의 코칭 VOD 전사문 분석 결과 + 코칭 브레인(coaching brain/knowledge/)을 바탕으로,
# GPT가 "CODM 팀 코치의 시각"으로 인사이트/요약을 생성하도록 지식을 주입한다.
#
# 갱신 3계층:
#   - 정적 (수동): 계산 지표 정의(metrics.py 동기화)·발음변형 맵.
#   - 코칭 브레인 (런타임): coaching_brain_loader가 coaching brain/knowledge/에서
#     영역별로 읽어 mtime 자동 캐싱. 코치가 Obsidian에서 수정하면 다음 호출에 반영.
#   - 동적 (자동): 팀 로스터·역할·스탯 → 매 호출마다 DB에서 조회.
#   - 시점 (자동): 현재 날짜 → 메타 시점 고정.
#
# analytics_insights.py의 모든 GPT 호출이 build_system_prompt()를 거친다.

import datetime

import coaching_brain_loader

# 전사문 발음 오류 매핑 (OCR/Alias 스킬과 연계)
# refresh_domain_context.py 실행으로 새 변형을 발견해 여기에 추가.
_PLAYER_IGN_MAP = {
    "Shisui": ["Shizi", "she-she", "she she", "Shishi", "Shisi", "Chisu", "Shane",
               "쉬스이", "시스이"],
    "Maozyn": ["Mao", "Maozen", "Mazin", "Maoz", "마오진", "마오즌"],
    "Cartels": ["Cartel", "cartilage", "cartos", "카르텔"],
    "Kingz": ["Kings", "King", "Kingsui", "킹즈"],
    "Exile": ["Exhale", "엑자일"],
    "unravel": ["Unravel", "언래블", "Jason", "제이슨"],  # Jason은 unravel의 실명
}

# 계산 지표 정의 — metrics.py 공식과 정확히 동기화.
# 코칭 통찰(역학·용어·코칭톤·맵)은 코칭 브레인에서 로드 (coaching_brain_loader).
_METRIC_DEFINITIONS = """# CODM Metric Definitions (authoritative — matches metrics.py)

You are advising a competitive Call of Duty Mobile (CODM) team. Use this domain knowledge to ground every insight in real game understanding.

## Game & Modes
CODM competitive uses two modes:
- HP (Hardpoint / 거점): capture rotating hills P1→P2→P3→P4, ~60s each. OBJ = hill time in seconds (higher = better). CapKill = bonus-score kills (multikills, trades, top-enemy kills, in-hill kills) — NOT pure objective time. "hill"/"언덕" = the current active point.
- SND (Search & Destroy / 폭파): alternating attack/defense, round-based. FK = First Blood (first kill), LWW = Lone Wolf Win, ADR = avg damage per round.

## Key Metric Definitions (don't recompute — interpret the numbers provided)
- ZCS (HP only) = max(0, 1.1·OBJ + 8·CapKill + 4.1·K − 5·D). Team avg ~150–200; 250+ = ace-level zone control; <100 = low impact.
  ZCS measures ZONE CONTROL CONTRIBUTION — how much a player helped OWN the hill.
  CapKill ×8 (highest weight): bonus-score kills are HIGH-QUALITY objective-tied kills.
  K ×4.1: standard kills — half the value of a CapKill (context matters).
  OBJ ×1.1: hill time — pure presence, alone low-value.
  D ×5 (heavier than K's 4.1): deaths penalized MORE than kills rewarded.
  → Modest K/D + high CapKill density + rare hill deaths = high ZCS. Raw fragging with low OBJ/CapKill = lower ZCS.
- RDS (SND only) = max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D). SND 제1 지표 (ZCS의 SND 대응).
  FK ×14, LWW ×20: opening duels and clutches weigh heavily — round-swinging events.
- K/D: ~1.0 avg, 1.3+ strong, <0.8 weak.
- DPK (dmg/kills): LOWER is better (finishing ability). ~700–1100.
- DPD (dmg/deaths): HIGHER is better (value per life). ~800–1300.
- Impact = min(200, 73 + 2.6K − 3.1D + 0.92·OBJ + 0.009·dmg). 150+ = excellent.
- AP% = (CapKill / K) × 100 — kill quality density. HIGH = kills are objective-relevant.
- Direction: HIGHER better = ZCS, RDS, DPD, Impact, OBJ, K/D. LOWER better = DPK, deaths.
"""

# domains=None일 때 기본 코칭 브레인 영역 (항상 깔리는 최소 통찰)
_DEFAULT_DOMAINS = ["principles", "mechanics-core"]


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


def build_system_prompt(task: str, lang: str = "ko", domains: list = None) -> str:
    """모든 AI 호출용 system 프롬프트 조합.

    계산 지표 정의 + IGN 변형 맵 + 코칭 브레인 통찰(선택적) + 날짜 + 동적 로스터 + 작업 지시문.
    task: 각 함수의 개별 지시문 (길이·포커스). lang: ko/en/es.
    domains: 주입할 코칭 브레인 영역 키 리스트 (예: ["principles","maps:Combine"]).
             None이면 _DEFAULT_DOMAINS(principles + mechanics-core) 사용.
             코칭 브레인 로드 실패 시 통찰 없이 지표+로스터만으로 동작 (실패 안전).
    """
    today = datetime.date.today().isoformat()
    lang_note = {"ko": "Korean (한국어)", "en": "English", "es": "Spanish (español)"}.get(lang, "Korean (한국어)")

    # 코칭 브레인 영역 로드 (실패 시 "" — 정상 동작 유지)
    try:
        insight_context = coaching_brain_loader.get_domains(
            domains if domains is not None else _DEFAULT_DOMAINS, lang
        )
    except Exception as e:
        print(f"[prompt_context] coaching_brain_loader fail (fallback to metrics-only): {e}", flush=True)
        insight_context = ""

    parts = [
        _METRIC_DEFINITIONS,
        _format_ign_map(),
        insight_context,
        f"\n## Current Date (meta snapshot): {today}",
        team_roster_context(),
        f"\n## Task\n{task}",
        f"\nRespond in {lang_note}.",
    ]
    return "\n".join(p for p in parts if p)
