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
    if not deaths:
        return None
    return round(total_damage / deaths, 2)


def compute_dpk(total_damage, kills) -> float:
    """Damage Per Kill = Total Damage / Kills (낮을수록 좋음).
    total_damage=0은 보통 데이터 누락 — 0/kills=0이 '낮을수록 좋음' 체계에서
    1등으로 왜곡되므로 None 처리."""
    if not total_damage or not kills:
        return None
    return round(total_damage / kills, 2)


def compute_id(impact, score) -> float:
    """Impact Delta = Impact − Score/34."""
    if impact is None:
        return None
    return round(impact - (score or 0) / 34, 2)


def compute_ap_pct(capture_kill, kills) -> float:
    """Assist Percentage = (Capture Kill / Kills) × 100."""
    if capture_kill is None or not kills:
        return None
    return round(capture_kill / kills * 100, 2)


def compute_zcs(obj_time, capture_kill, kills, deaths) -> float:
    """Zone Control Score = max(0, 1.1·OBJ + 8·CK + 4.1·K − 5·D).

    ⚠️ HP 전용 지표 — SND 매치/선수 데이터로는 호출 금지.
    SND에는 OBJ/캡처킬이 없어 4.1·K − 5·D만 남은 의미 없는 점수가 됨.
    외부에서 직접 호출하지 말 것 — all_hp_metrics() 경유로만 사용.
    """
    if any(v is None for v in (obj_time, capture_kill, kills, deaths)):
        return None
    val = 1.1 * obj_time + 8 * capture_kill + 4.1 * kills - 5 * deaths
    return round(max(0, val), 2)


def compute_rds(kills, assists, first_kill, lone_wolf_win, adr, deaths) -> float:
    """Round Domination Score = max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D).

    SND 전용 제1 지표 — ZCS와 대칭. 라운드 장악력(오프닝·듀얼·클러치 종합).
    ⚠️ SND 전용 — HP 데이터로 호출 금지.
    가중치는 경험적 매그니튜드 (승패 데이터 충분 시 로지스틱 회귀로 재튜닝 TODO).
    """
    if any(v is None for v in (kills, assists, first_kill, lone_wolf_win, adr, deaths)):
        return None
    val = (4.1 * kills + 3.5 * assists + 14 * first_kill
           + 20 * lone_wolf_win + 0.12 * adr - 5 * deaths)
    return round(max(0, val), 2)


def all_hp_metrics(kills, deaths, obj_time, score, impact, total_damage, capture_kill) -> dict:
    """HP 매치 한 선수분의 모든 커스텀 지표를 한 번에 계산.

    ⚠️ HP 전용 — SND 스탯으로 호출하지 말 것.
    impact가 None이면 공식으로 계산한다.
    """
    imp = impact if impact is not None else compute_impact(kills, deaths, obj_time, total_damage)
    return {
        "dpd": compute_dpd(total_damage, deaths),
        "dpk": compute_dpk(total_damage, kills),
        "impact_delta": compute_id(imp, score),
        "ap_pct": compute_ap_pct(capture_kill, kills),
        "zcs": compute_zcs(obj_time, capture_kill, kills, deaths),
        "impact": imp,
    }


def all_snd_metrics(kills, assists, first_kill, lone_wolf_win, adr, deaths) -> dict:
    """SND 매치 한 선수분의 커스텀 지표를 한 번에 계산.

    ⚠️ SND 전용 — HP 스탯으로 호출하지 말 것.
    현재는 RDS만 포함 (향후 SND 보조 지표 추가 시 여기에 확장).
    """
    return {
        "rds": compute_rds(kills, assists, first_kill, lone_wolf_win, adr, deaths),
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


def role_spectrum_pos(slay_score: float, obj_score: float) -> float:
    """역할 스펙트럼 바 위 마커 위치(%, 5~95).

    slay_score / obj_score: 팀 평균 대비 비율(team_role_distribution과 동일 로직).
    반환: 5.0(순 OBJ) ~ 95.0(순 Slayer). 양쪽 극단은 clamp.
    허브(coaching_hub.html) 인라인 공식과 동일 — 단일 진실.
    """
    ss = slay_score if slay_score else 1.0
    os_ = obj_score if obj_score else 1.0
    norm = (ss - os_) / (ss + os_)  # -1(순obj) ~ +1(순slay)
    return round(max(5, min(95, 50 + norm * 450)), 1)
