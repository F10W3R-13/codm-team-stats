

def test_path_setup_enables_parent_metrics_import():
    """_path_setup import 후 부모 metrics.py 임포트 가능해야 함."""
    import _path_setup  # noqa: F401 — sys.path 설정이 목적인 부수효과 임포트
    from metrics import compute_zcs, compute_rds  # 부모 모듈
    assert callable(compute_zcs)
    assert callable(compute_rds)


def test_compute_zcs_formula_unchanged():
    """부모 metrics.py 공식이 예상값을 반환하는지 (재사용 안전성)."""
    from metrics import compute_zcs
    # ZCS = max(0, 1.1·OBJ + 8·CK + 4.1·(K−CK) − 5·D)
    # OBJ=100, CK=2, K=20, D=10 → 110 + 16 + 4.1*18 - 50 = 149.8
    assert compute_zcs(obj_time=100, capture_kill=2, kills=20, deaths=10) == 149.8
