"""토너먼트 웹앱 원클릭 런처.

실행:
    python run.py

하는 일 (한 번에 전부):
  1. 부모 .env 에서 OPENAI_API_KEY 자동 로드 (없으면 안내 후 종료)
  2. DB 초기화 (tournament.db 생성)
  3. 시드 상태 체크 (팀/명단 등록 여부 → 안내)
  4. 브라우저 자동 오픈 (http://localhost:8001)
  5. uvicorn 서버 기동 (Ctrl+C 로 종료)

시드가 안 되어 있으면 터미널에 안내만 띄우고 서버는 그냥 시작 —
(시드는 웹앱이 떠 있는 동안 다른 터미널에서 python seed.py 로 언제든 가능.)
"""
import os
import socket
import sys
import threading
import time
import webbrowser

from dotenv import load_dotenv

# 부모 디렉토리의 .env 로드 (OPENAI_API_KEY)
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PARENT, ".env"))

# ── 1단계: API 키 확인 ─────────────────────────────────────────────
if not os.environ.get("OPENAI_API_KEY"):
    print("=" * 60)
    print("❌ OPENAI_API_KEY 가 없습니다.")
    print()
    print("   부모 폴더의 .env 파일에 키가 있어야 합니다:")
    print(f"   {_PARENT}\\.env")
    print()
    print("   .env 파일 안에 이 줄이 있어야 합니다:")
    print('   OPENAI_API_KEY=sk-...본인키...')
    print("=" * 60)
    sys.exit(1)
print("✅ OPENAI_API_KEY 확인됨")

# ── 2단계: DB 초기화 ────────────────────────────────────────────────
import db
db.init_db()
print("✅ DB 준비 완료 (tournament.db)")

# ── 3단계: 시드 상태 체크 ───────────────────────────────────────────
teams = db.list_teams()
players = db.list_players()
if not teams:
    print()
    print("=" * 60)
    print("⚠️  팀/명단이 아직 등록되지 않았습니다!")
    print()
    print("   이 창은 그대로 두고, 새 터미널을 열어서:")
    print("   1) cd tournament")
    print("   2) python seed.py        ← 대화형으로 팀·명단 입력")
    print("      (또는 python seed.py teams.json)")
    print()
    print("   시드 후 브라우저에서 스크린샷 업로드하면 됩니다.")
    print("   서버는 계속 켜져 있으니 시드는 언제든 해도 OK.")
    print("=" * 60)
    print()
else:
    print(f"✅ 시드 완료: 팀 {len(teams)}개 · 선수 {len(players)}명")

PORT = 8001
URL = f"http://localhost:{PORT}"


def _open_browser_when_ready():
    """서버가 실제로 요청을 받을 준비가 된 뒤 브라우저 오픈.

    고정 타이머(예: 1.5초) 대신 폴링으로 서버 기동을 확인한다.
    느린 환경에서 서버 기동이 지연되면 고정 타이머는 브라우저가 먼저 열려
    '연결 거부' 페이지를 띄우는 경쟁 조건이 발생한다.
    폴링은 서버가 소켓을 열었는지 직접 확인하므로 이를 제거한다.
    """
    for _ in range(50):  # 최대 ~10초 대기 (0.2초 × 50)
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.3):
                webbrowser.open(URL)
                return
        except OSError:
            time.sleep(0.2)
    # 10초래도 안 뜨면 포기 (사용자가 수동으로 열게 안내만 남김)


threading.Thread(target=_open_browser_when_ready, daemon=True).start()
print(f"🌐 브라우저를 자동으로 엽니다: {URL}")
print("   (서버가 준비되면 열림. 안 열리면 직접 주소창에 입력)")
print()
print("━━━ 서버 시작 (종료하려면 Ctrl+C) ━━━")
print()

# ── 5단계: uvicorn 기동 (블로킹) ────────────────────────────────────
import uvicorn
uvicorn.run("app:app", host="127.0.0.1", port=PORT, reload=False)
