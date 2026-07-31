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
import sys
import threading
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

# ── 4단계: 브라우저 자동 오픈 (서버 뜨기 직전 예약) ────────────────
PORT = 8001
URL = f"http://localhost:{PORT}"


def _open_browser():
    """1.5초 후 브라우저 오픈 (서버가 뜰 시간 확보)."""
    threading.Timer(1.5, lambda: webbrowser.open(URL)).start()


_open_browser()
print(f"🌐 브라우저를 엽니다: {URL}")
print("   (안 열리면 직접 주소창에 입력)")
print()
print("━━━ 서버 시작 (종료하려면 Ctrl+C) ━━━")
print()

# ── 5단계: uvicorn 기동 (블로킹) ────────────────────────────────────
import uvicorn
uvicorn.run("app:app", host="127.0.0.1", port=PORT, reload=False)
