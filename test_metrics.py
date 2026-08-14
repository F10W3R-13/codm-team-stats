# metrics.py 커스텀 지표 공식 고정 테스트 (characterization test)
#
# 목적: ZCS/RDS/Impact 등 공식이 실수로 바뀌는 것을 방지.
# 기대값은 AGENTS.md·metrics.py 문서 공식을 손계산한 것.
# 공식을 의도적으로 변경하는 리팩터링이라면 이 테스트를 함께 수정해야 한다.

import metrics


# ── ZCS (HP 제1 지표) ──────────────────────────────────────────────────────

def test_zcs_typical():
    # 1.1*100 + 8*3 + 4.1*20 - 5*10 = 110 + 24 + 82 - 50 = 166.0
    assert metrics.compute_zcs(100, 3, 20, 10) == 166.0

def test_zcs_clamp_zero():
    # 음수는 0으로 clamp: 4.1*1 - 5*10 = -45.9 → 0
    assert metrics.compute_zcs(0, 0, 1, 10) == 0.0

def test_zcs_rounding():
    # 1.1 + 8 + 4.1 - 5 = 8.2
    assert metrics.compute_zcs(1, 1, 1, 1) == 8.2

def test_zcs_none_input():
    assert metrics.compute_zcs(None, 3, 20, 10) is None
    assert metrics.compute_zcs(100, None, 20, 10) is None
    assert metrics.compute_zcs(100, 3, None, 10) is None
    assert metrics.compute_zcs(100, 3, 20, None) is None

def test_zcs_weight_ratio():
    # 캡처킬 1점 = 킬 8/4.1 ≈ 1.951킬 (가중치 상대 비율 고정)
    a = metrics.compute_zcs(0, 1, 0, 0)
    b = metrics.compute_zcs(0, 0, 8 / 4.1, 0)
    assert abs(a - b) < 0.01


# ── RDS (SND 제1 지표) ─────────────────────────────────────────────────────

def test_rds_typical():
    # 4.1*20 + 3.5*5 + 14*3 + 20*1 + 0.12*1800 - 5*10
    # = 82 + 17.5 + 42 + 20 + 216 - 50 = 327.5
    assert metrics.compute_rds(20, 5, 3, 1, 1800, 10) == 327.5

def test_rds_clamp_zero():
    # 4.1 + 0.12*100 - 5*10 = -33.9 → 0
    assert metrics.compute_rds(1, 0, 0, 0, 100, 10) == 0.0

def test_rds_none_input():
    assert metrics.compute_rds(None, 5, 3, 1, 1800, 10) is None
    assert metrics.compute_rds(20, 5, 3, 1, None, 10) is None
    assert metrics.compute_rds(20, 5, 3, 1, 1800, None) is None

def test_rds_fk_worth_approx_3_4_kills():
    # FK 가중치 14 ≈ 3.4 × 킬 가중치 4.1 (문서화된 매그니튜드)
    a = metrics.compute_rds(0, 0, 1, 0, 0, 0)   # FK 1회 = 14
    b = metrics.compute_rds(3.4, 0, 0, 0, 0, 0)  # 킬 3.4회 = 13.94
    assert abs(a - b) < 0.1


# ── 보조 지표 ──────────────────────────────────────────────────────────────

def test_impact_typical():
    # 73 + 2.6*10 - 3.1*8 + 0.92*50 + 0.009*2000 = 73+26-24.8+46+18 = 138.2
    assert metrics.compute_impact(10, 8, 50, 2000) == 138.2

def test_impact_cap_200():
    # 73 + 52 - 31 + 92 + 27 = 213 → 상한 200
    assert metrics.compute_impact(20, 10, 100, 3000) == 200.0

def test_impact_none():
    assert metrics.compute_impact(None, 8, 50, 2000) is None

def test_dpd():
    assert metrics.compute_dpd(3000, 10) == 300.0
    assert metrics.compute_dpd(3000, 0) is None  # 0데스 방어

def test_dpk():
    assert metrics.compute_dpk(3000, 20) == 150.0
    assert metrics.compute_dpk(0, 20) is None    # 딜 누락 방어 (낮을수록 좋음 체계 왜곡 방지)
    assert metrics.compute_dpk(3000, 0) is None

def test_id():
    assert metrics.compute_id(138.2, 1700) == 88.2   # 138.2 - 50
    assert metrics.compute_id(None, 1700) is None
    assert metrics.compute_id(100.0, None) == 100.0  # score 없으면 0 처리

def test_ap_pct():
    assert metrics.compute_ap_pct(3, 20) == 15.0
    assert metrics.compute_ap_pct(None, 20) is None
    assert metrics.compute_ap_pct(3, 0) is None

def test_all_hp_metrics_keys_and_consistency():
    m = metrics.all_hp_metrics(
        kills=20, deaths=10, obj_time=100, score=2500,
        impact=None, total_damage=3000, capture_kill=3)
    assert set(m.keys()) == {"dpd", "dpk", "impact_delta", "ap_pct", "zcs", "impact"}
    assert m["zcs"] == metrics.compute_zcs(100, 3, 20, 10)
    assert m["dpd"] == 300.0
    assert m["dpk"] == 150.0
    # impact None → 공식으로 재계산 (상한 200)
    assert m["impact"] == metrics.compute_impact(20, 10, 100, 3000)

def test_all_snd_metrics():
    m = metrics.all_snd_metrics(20, 5, 3, 1, 1800, 10)
    assert m["rds"] == metrics.compute_rds(20, 5, 3, 1, 1800, 10)


# ── 역할 분류 ──────────────────────────────────────────────────────────────

def test_classify_role_objective():
    player = {"avg_k": 1.0, "avg_dmg": 1.0, "avg_obj": 2.0, "avg_capture": 2.0}
    team = {"avg_k": 1.0, "avg_dmg": 1.0, "avg_obj": 1.0, "avg_capture": 1.0}
    assert metrics.classify_role(player, team) == "objective"

def test_classify_role_slayer():
    player = {"avg_k": 2.0, "avg_dmg": 2.0, "avg_obj": 1.0, "avg_capture": 1.0}
    team = {"avg_k": 1.0, "avg_dmg": 1.0, "avg_obj": 1.0, "avg_capture": 1.0}
    assert metrics.classify_role(player, team) == "slayer"

def test_classify_role_balanced():
    same = {"avg_k": 1.0, "avg_dmg": 1.0, "avg_obj": 1.0, "avg_capture": 1.0}
    assert metrics.classify_role(same, dict(same)) == "balanced"

def test_classify_role_zero_team_defensive():
    # 팀 평균 0 → ratio 1.0으로 방어 (ZeroDivisionError 없어야 함)
    player = {"avg_k": 5.0, "avg_dmg": 5000.0, "avg_obj": 5.0, "avg_capture": 5.0}
    team = {"avg_k": 0, "avg_dmg": 0, "avg_obj": 0, "avg_capture": 0}
    assert metrics.classify_role(player, team) == "balanced"


# ── 역할 스펙트럼 위치 ─────────────────────────────────────────────────────

def test_role_spectrum_center():
    assert metrics.role_spectrum_pos(1.0, 1.0) == 50.0

def test_role_spectrum_clamp():
    assert metrics.role_spectrum_pos(2.0, 0) == 95.0   # 0 → 1.0 폴백 후 slayer 극단
    assert metrics.role_spectrum_pos(0, 2.0) == 5.0
