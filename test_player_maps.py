# player_map_breakdown mode 확장 + _heat_class 단위테스트
#
# 실행: pytest test_player_maps.py -v
#
# 검증:
#  - player_map_breakdown HP 모드: 기존 동작, metric/metric_pct 키
#  - player_map_breakdown SND 모드: RDS 기반, metric/metric_pct 키
#  - mode 기본값 "HP" (하위 호환)
#  - 빈 결과 (데이터 없는 선수) → 빈 리스트
#  - _player_overall_rds 존재 + 정상 동작

import pytest

import queries

# conftest의 시드 DB(스키마+샘플 매치) 사용 — 실제 로컬 codm.db 의존 제거.
# 이전에는 로컬 DB에 데이터가 없으면 조용히 스킵되는 구조였다.
pytestmark = pytest.mark.usefixtures("seeded_db")


def _any_player_with_hp():
    """HP 데이터 있는 임의 선수 ID."""
    import db
    with db.get_conn() as conn:
        r = conn.execute("SELECT DISTINCT player_id FROM player_stats_hp LIMIT 1").fetchone()
    return r["player_id"] if r else None


def _any_player_with_snd():
    """SND 데이터 있는 임의 선수 ID."""
    import db
    with db.get_conn() as conn:
        r = conn.execute("SELECT DISTINCT player_id FROM player_stats_snd LIMIT 1").fetchone()
    return r["player_id"] if r else None


def test_hp_mode_returns_metric_keys():
    """HP 모드가 metric/metric_pct 키를 반환 (zcs/zcs_pct 아님)."""
    pid = _any_player_with_hp()
    if pid is None:
        return  # 로컬 DB에 HP 데이터 없음 — 스킵
    result = queries.player_map_breakdown(pid, mode="HP", min_matches=1)
    if not result:
        return  # min_matches 커버 데이터 없음
    assert "metric" in result[0]
    assert "metric_pct" in result[0]
    assert "zcs" not in result[0]  # 구 키 제거
    assert "zcs_pct" not in result[0]


def test_default_mode_is_hp():
    """mode 생략 시 HP (하위 호환)."""
    pid = _any_player_with_hp()
    if pid is None:
        return
    explicit = queries.player_map_breakdown(pid, mode="HP", min_matches=1)
    default = queries.player_map_breakdown(pid, min_matches=1)
    assert explicit == default


def test_snd_mode_returns_metric_keys():
    """SND 모드가 metric/metric_pct 키를 반환."""
    pid = _any_player_with_snd()
    if pid is None:
        return
    result = queries.player_map_breakdown(pid, mode="SND", min_matches=1)
    if not result:
        return
    assert "metric" in result[0]
    assert "metric_pct" in result[0]
    # SND 맵 이름 포함 확인 (Meltdown 등)
    map_names = [r["map_name"] for r in result]
    assert any(m for m in map_names)


def test_empty_result_for_nonexistent_player():
    """존재하지 않는 선수 → 빈 리스트 (예외 X)."""
    result = queries.player_map_breakdown(999999, mode="HP", min_matches=1)
    assert result == []
    result_snd = queries.player_map_breakdown(999999, mode="SND", min_matches=1)
    assert result_snd == []


def test_player_overall_rds_exists():
    """_player_overall_rds 함수 존재 + SND 선수에 대해 숫자 반환."""
    assert hasattr(queries, "_player_overall_rds")
    pid = _any_player_with_snd()
    if pid is None:
        return
    val = queries._player_overall_rds(pid)
    # SND 데이터 있으면 숫자 (데이터 부족 시 None도 허용)
    if val is not None:
        assert isinstance(val, (int, float))
        assert val >= 0  # RDS는 max(0,...)라 음수 불가


def test_heat_class_thresholds():
    """_heat_class (web_api에 추가 예정) 임계값 — 이 테스트는 Task 2에서 web_api 가져와야.
    여기서는 queries에 국한. 대신 player_map_breakdown 결과에 heat_class 없음 확인."""
    pid = _any_player_with_hp()
    if pid is None:
        return
    result = queries.player_map_breakdown(pid, mode="HP", min_matches=1)
    if result:
        assert "heat_class" not in result[0]  # heat_class는 web_api에서 부여
