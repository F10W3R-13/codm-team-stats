# prompt_context 도메인 통합 테스트
#
# 실행: pytest test_prompt_context_domains.py -v
#
# 검증:
#  - build_system_prompt가 domains 파라미터를 받는다 (하위 호환: None OK)
#  - domains 전달 시 코칭 브레인 내용이 프롬프트에 포함된다
#  - domains=None → 기본 세트(principles+mechanics-core) 주입
#  - 지표 정의(ZCS/RDS 공식)는 항상 포함
#  - _MAP_META 제거 확인

import prompt_context as pc


def test_build_prompt_accepts_domains_param():
    """build_system_prompt(task, lang, domains) 시그니처 동작."""
    result = pc.build_system_prompt("do thing", "ko", domains=["principles"])
    assert isinstance(result, str)
    assert "do thing" in result


def test_domains_none_backward_compatible():
    """domains 생략(기본값 None) → 기본 세트 주입, 에러 없음."""
    result = pc.build_system_prompt("task", "ko")
    assert "task" in result
    # 기본 세트 = principles + mechanics-core
    assert "원칙" in result or "코칭" in result


def test_coaching_brain_content_included():
    """domains로 전달한 영역의 코칭 브레인 내용이 프롬프트에 들어간다."""
    result = pc.build_system_prompt("task", "ko", domains=["maps:Combine"])
    # maps/Combine.md 내용이 들어가야 함 (P3 스폰 등)
    assert "P3" in result or "스폰" in result or "Combine" in result


def test_metric_definitions_always_present():
    """ZCS/RDS 공식 정의는 domains와 무관하게 항상 포함."""
    result = pc.build_system_prompt("task", "ko", domains=[])
    assert "ZCS" in result
    assert "RDS" in result
    # ZCS 공식 검증 (metrics.py와 정합)
    assert "1.1" in result and "8" in result and "4.1" in result


def test_map_meta_removed():
    """_MAP_META (구 맵 tendency 딕셔너리) 제거 확인."""
    assert not hasattr(pc, "_MAP_META"), "_MAP_META는 코칭 브레인으로 이관되어 제거되어야 함"


def test_default_domains_constant():
    """_DEFAULT_DOMAINS 상수 존재 + 기본 세트."""
    assert hasattr(pc, "_DEFAULT_DOMAINS")
    assert "principles" in pc._DEFAULT_DOMAINS
    assert "mechanics-core" in pc._DEFAULT_DOMAINS


def test_metric_definitions_have_no_fixed_ranges():
    """시즌마다 낡는 고정 수치(ZCS ~120, DPK 700–1100 등)를 정의에 두지 않는다 — 기준선은 DB에서."""
    for stale in ("~120", "700", "1100", "1300", "150+"):
        assert stale not in pc._METRIC_DEFINITIONS, stale


def test_baselines_injected_and_rules_last(monkeypatch):
    """기준선이 주입되고, 작업 지시·출력 규칙은 참고 자료 뒤(맨 끝)에 온다."""
    import queries
    d = {"n": 40, "mean": 70.0, "p25": 14.1, "p50": 56.3, "p75": 111.2, "p90": 157.5}
    monkeypatch.setattr(queries, "metric_baselines",
                        lambda season=None: {"season": "s2", "HP": {"zcs": d}, "SND": {}})
    monkeypatch.setitem(pc._baseline_cache, "text", "")
    result = pc.build_system_prompt("do thing", "ko", domains=["principles"], rules=["Plain text only"])
    assert "HP ZCS: 14.1 / 56.3 / 111.2 / 157.5" in result
    assert result.index("## Task") > result.index("Current Season Baselines")
    assert result.index("## Output Rules") > result.index("## Task")
    assert result.rstrip().endswith("Respond in Korean (한국어).")
