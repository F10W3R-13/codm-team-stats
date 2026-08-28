# CODM 스탯 봇 설정값
# make.com 시나리오에서 사용하던 값들을 그대로 가져왔다.
import os

# ── 디스코드 ────────────────────────────────────────────────────────────
# 스탯 스크린샷을 감시할 채널 ID (make.com: scrim-result 채널)
WATCH_CHANNEL_ID = 1481522059086532629

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

# ── OpenAI 호환 (OpenAI / Z.ai GLM) ───────────────────────────────────────
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = "glm-5.3-flash"     # 2026-08 전환: gpt-5.6-luna($0.20/$1.20) → Z.ai flash($0.075/$0.25), 네이티브 비전
OPENAI_TEMPERATURE = 0.0          # 구세대 전용 (reasoning 계열에선 미전송)
OPENAI_MAX_TOKENS = 8192          # glm-5.3-flash: thinking 토큰 포함 총한도 — OCR JSON본문까지 여유 확보
OPENAI_REASONING_EFFORT = "low"   # reasoning 계열: OCR·짧은 인사이트엔 low로 충분 (지연·비용 절약)

# glm-* 모델은 Z.ai OpenAI 호환 엔드포인트로. env OPENAI_BASE_URL 로 오버라이드 가능.
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or (
    "https://api.z.ai/api/paas/v4/" if OPENAI_MODEL.startswith("glm-") else None)

# gpt-5+/o계열 reasoning 모델은 temperature 변경·max_tokens 미지원 → 파라미터 자동 보정.
OPENAI_IS_REASONING = OPENAI_MODEL.startswith(("gpt-5", "o1", "o3", "o4"))


def chat_params(temperature: float = None, max_tokens: int = None) -> dict:
    """모델 세대에 맞는 chat.completions.create 추가 파라미터 조립.

    reasoning 계열: temperature 미전송(고정 1), max_tokens→max_completion_tokens.
    구세대(gpt-4.1 등): 기존대로 temperature/max_tokens.
    """
    params: dict = {}
    if OPENAI_IS_REASONING:
        if max_tokens:
            params["max_completion_tokens"] = max_tokens
        params["reasoning_effort"] = OPENAI_REASONING_EFFORT
    else:
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens:
            params["max_tokens"] = max_tokens
    return params

# ── 구글 시트 ─────────────────────────────────────────────────────────────
SPREADSHEET_ID = "1nnyzo7_mH1JgTF5yln2AR1HuUiVGc9c7ZctVyA8PlgE"
# 로컬: GOOGLE_SERVICE_ACCOUNT_FILE(파일 경로) 사용.
# 배포(Railway): 파일을 못 올리므로 GOOGLE_SERVICE_ACCOUNT_JSON(JSON 내용 통째로) 사용.
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
SHEET_HP = "Database_HP"          # make.com: sheetId Database_HP
SHEET_SND = "Database_SND"        # make.com: sheetId Database_SND

# ── 로스터 (이름 정규화용) ───────────────────────────────────────────────
ROSTER = ["Shisui", "Cartels", "unravel", "Kingz", "Maozyn", "Exile"]  # AyeoRaph 퇴단 (2026-06)

# ── 관리자 인증 (웹 /admin/* 보호용) ──────────────────────────────────────
# Railway 환경변수 ADMIN_PASSWORD 로 설정. 없으면 기본값 사용.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "3717")
# 쿠키 서명용 시크릿. 환경변수 우선, 없으면 ADMIN_PASSWORD 파생값.
SECRET_KEY = os.environ.get("SECRET_KEY") or f"codm-admin-{ADMIN_PASSWORD}"
# 인증 쿠키 수명(초). 7일.
ADMIN_COOKIE_MAX_AGE = 7 * 24 * 3600

# ── 칼럼 매핑 ─────────────────────────────────────────────────────────────
# make.com의 google-sheets addRow 모듈 mapper.values 매핑을
# 파이썬 리스트(append_row용)로 변환한 것이다.
# 각 함수는 (player_dict, date_str) → list[str] 를 반환.
#
# HP 시트 헤더(make.com 기준):
#   A IGN | B actual name | C Kills | D Deaths | E K/D
#   F OBJ(time) | G Score | H Impact | I Total Damage | J Capture Kill | K Date(신규)
#
# SND 시트 헤더(make.com 기준):
#   A IGN | B actual name | C Kills | D Deaths | E Assists | F K/D
#   G Score | H Impact | I ADR | J First Kill | K Lone Wolf Win | L Date(신규)
#
# SND의 actual name(B열)은 make.com처럼 Alias 시트를 참조하는 VLOOKUP 수식을
# 그대로 USER_ENTERED 모드로 넣는다.

# SND actual name 열에 들어갈 VLOOKUP 수식 (행 번호는 gspread append_row 기준으로
# 실제 행이 정해진 뒤 치환한다. sentinel {row} 사용).
SND_ACTUAL_NAME_FORMULA = (
    '=IFERROR(VLOOKUP(TRIM(INDIRECT("A"{row})), Alias!A:B, 2, FALSE), '
    'INDIRECT("A"{row}))'
)


def hp_row(p: dict, date_str: str) -> list:
    """HP 모드 선수 1명 → Database_HP 행 (K열 Date 자동 기록 포함)."""
    return [
        p.get("name", ""),
        "",  # B: actual name (HP는 make.com에서도 빈칸)
        p.get("k", ""),
        p.get("d", ""),
        p.get("kd_ratio", ""),
        p.get("time", ""),       # F: OBJ
        p.get("score", ""),
        p.get("impact", ""),
        p.get("total_damage", ""),
        p.get("capture_kill", ""),
        date_str,                # K: Date (메시지 작성일, 신규 추가)
    ]


def snd_row(p: dict, date_str: str, row_number: int) -> list:
    """SND 모드 선수 1명 → Database_SND 행 (L열 Date 자동 기록 포함).

    row_number: 이 행이 기록될 실제 시트 행 번호(1-based). VLOOKUP 수식의
    INDIRECT("A"&ROW())를 명시적 행 번호로 치환한다.
    """
    formula = SND_ACTUAL_NAME_FORMULA.replace("{row}", str(row_number))
    return [
        p.get("name", ""),
        formula,                  # B: actual name (VLOOKUP 수식)
        p.get("k", ""),
        p.get("d", ""),
        p.get("a", ""),           # E: Assists
        p.get("kd_ratio", ""),    # F: K/D
        p.get("score", ""),
        p.get("impact", ""),
        p.get("adr", ""),
        p.get("first_kill", ""),
        p.get("lone_wolf_win", ""),
        date_str,                 # L: Date (메시지 작성일, 신규 추가)
    ]
