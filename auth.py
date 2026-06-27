# 관리자 인증 헬퍼 — /admin/* 라우트 보호용 (세션 쿠키 방식)
#
# 흐름:
#   1. /admin/login 에서 비번 입력 → 맞으면 서명된 쿠키(admin_session) 발급
#   2. /admin/* 모든 라우트에서 쿠키 검증 → 없거나 잘못되면 /admin/login 리다이렉트
#   3. 비번은 환경변수 ADMIN_PASSWORD (Railway). 코드에 하드코딩하지 않는다.
#
# 외부 의존성: itsdangerous (FastAPI/Starlette에 내장, 별도 설치 불필요).

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import config

_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="admin-session")
COOKIE_NAME = "admin_session"


def verify_password(password: str) -> bool:
    """입력받은 비번이 ADMIN_PASSWORD 와 일치하는지."""
    return password == config.ADMIN_PASSWORD


def make_cookie() -> tuple:
    """인증 성공 시 (cookie_name, signed_value) 반환."""
    return COOKIE_NAME, _serializer.dumps({"authed": True})


def check_cookie(signed_value: str) -> bool:
    """서명된 쿠키 검증. 만료(=쿠키 수명) 시 False."""
    try:
        data = _serializer.loads(signed_value, max_age=config.ADMIN_COOKIE_MAX_AGE)
        return bool(data.get("authed"))
    except (BadSignature, SignatureExpired):
        return False
