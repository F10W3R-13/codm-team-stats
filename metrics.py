# 커스텀 스탯 지표 공식
#
# 구글 시트 Dashboard에서 직접 사용하던 역공식들을 파이썬 함수로 구현.
# 출처: "2026 NA data management" Dashboard 시트의 공식 정의(행 23, 40-53).
#
# 공식:
#   Impact ≈ min(200, 73 + 2.6·K − 3.1·D + 0.92·OBJ + 0.009·TD)
#   DPD  = Total Damage / Deaths          (라이프당 딜)
#   DPK  = Total Damage / Kills           (킬당 필요 딜)
#   ID   = Impact − Score/34              (점수 대비 임팩트 초과분)
#   AP%  = Capture Kill / Kills × 100     (킬 대비 캡처킬 비율 = 목표 기여도)
#   ZCS  = max(0, 1.1·OBJ + 8·CK + 4.1·K − 5·D)   (존 컨트롤 기여 점수)


def compute_impact(kills, deaths, obj_time, total_damage) -> float:
    """임팩트 역공식 (스크린샷에서 직접 계산할 때 사용). 상한 200."""
    if any(v is None for v in (kills, deaths, obj_time, total_damage)):
        return None
    val = 73 + 2.6 * kills - 3.1 * deaths + 0.92 * obj_time + 0.009 * total_damage
    return round(min(200, val), 2)


def compute_dpd(total_damage, deaths) -> float:
    """Damage Per Death = Total Damage / Deaths."""
    if not total_damage or not deaths:
        return None
    return round(total_damage / deaths, 2)


def compute_dpk(total_damage, kills) -> float:
    """Damage Per Kill = Total Damage / Kills."""
    if not total_damage or not kills:
        return None
    return round(total_damage / kills, 2)


def compute_id(impact, score) -> float:
    """Impact Delta = Impact − Score/34."""
    if impact is None or not score:
        return None
    return round(impact - score / 34, 2)


def compute_ap_pct(capture_kill, kills) -> float:
    """Assist Percentage = (Capture Kill / Kills) × 100."""
    if capture_kill is None or not kills:
        return None
    return round(capture_kill / kills * 100, 2)


def compute_zcs(obj_time, capture_kill, kills, deaths) -> float:
    """Zone Control Score = max(0, 1.1·OBJ + 8·CK + 4.1·K − 5·D)."""
    if any(v is None for v in (obj_time, capture_kill, kills, deaths)):
        return None
    val = 1.1 * obj_time + 8 * capture_kill + 4.1 * kills - 5 * deaths
    return round(max(0, val), 2)


def all_hp_metrics(kills, deaths, obj_time, score, impact, total_damage, capture_kill) -> dict:
    """HP 매치 한 선수분의 모든 커스텀 지표를 한 번에 계산.

    impact가 None이면 공식으로 계산한다.
    """
    imp = impact if impact is not None else compute_impact(kills, deaths, obj_time, total_damage)
    return {
        "dpd": compute_dpd(total_damage, deaths),
        "dpk": compute_dpk(total_damage, kills),
        "id": compute_id(imp, score),
        "ap_pct": compute_ap_pct(capture_kill, kills),
        "zcs": compute_zcs(obj_time, capture_kill, kills, deaths),
        "impact": imp,
    }


# ── 역할(Role) 분류 ────────────────────────────────────────────────────────
# HP 전용 — OBJ 시간/캡처킬(목표 기여) vs 킬/딜(처치 기여) 비중으로 역할 추정.
# 기준: 팀 평균 대비 비율. 팀 컨텍스트가 있어야 의미 있음.
#
# 역할 정의:
#   slayer     — 킬·딜 비중 높음 (처치 집중형)
#   objective  — OBJ·캡처킬 비중 높음 (목표 기여형, anchor)
#   balanced   — 양쪽 고르게 (flex)
ROLE_THRESHOLD = 1.08  # 팀 평균 대비 8% 이상 높으면 그 역할로 분류


def classify_role(player_hp: dict, team_hp: dict) -> str:
    """선수의 HP 역할 분류.

    player_hp: {avg_k, avg_obj, avg_dmg, avg_capture, ...} (개인 평균)
    team_hp:   동일 키의 팀 평균 (벤치마크)
    반환: "slayer" | "objective" | "balanced"
    """
    def _ratio(indiv, team):
        if not indiv or not team:
            return 1.0
        return indiv / team

    # 처치 지향 점수 = 킬 비율 + 딜 비율 평균
    slay = (_ratio(player_hp.get("avg_k"), team_hp.get("avg_k")) +
            _ratio(player_hp.get("avg_dmg"), team_hp.get("avg_dmg"))) / 2
    # 목표 지향 점수 = OBJ 비율 + 캡처킬 비율 평균
    obj = (_ratio(player_hp.get("avg_obj"), team_hp.get("avg_obj")) +
           _ratio(player_hp.get("avg_capture"), team_hp.get("avg_capture"))) / 2

    if obj >= ROLE_THRESHOLD and obj > slay:
        return "objective"
    if slay >= ROLE_THRESHOLD and slay > obj:
        return "slayer"
    return "balanced"
