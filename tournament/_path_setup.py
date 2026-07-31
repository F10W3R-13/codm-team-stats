"""부모 디렉토리(Team management app/)를 sys.path에 추가해
metrics.py 등 부모 모듈을 import 가능하게 한다.

모든 tournament 모듈은 다른 import 전에 이 모듈을 먼저 import한다:
    import _path_setup  # noqa: F401  (부작용 전용)
    from metrics import compute_zcs, compute_rds
"""
import os
import sys

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
