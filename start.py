# 통합 시작 스크립트 — 디스코드 봇 + FastAPI 웹을 한 컨테이너에서 실행.
#
# 로컬: python start.py
# 배포(Railway): Procfile 이 이 스크립트 호출.
#
# 전략: 봇과 웹을 각각 subprocess로 실행 (코드 격리, 의존성 충돌 방지).
#       둘 다 같은 DB(Postgres/SQLite) 환경변수 공유.
#
# 환경변수:
#   DISCORD_BOT_TOKEN, OPENAI_API_KEY (필수)
#   DATABASE_URL (배포 시 Postgres, 없으면 로컬 SQLite)
#   PORT (Railway 자동 주입, 기본 8000)

import os
import sys
import subprocess
import signal
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("start")

# DB 초기화 (자식 프로세스 전에 한 번)
import db
db.init_db()
log.info("DB 초기화 완료")

procs = []


def start_bot():
    """디스코드 봇을 subprocess로 실행."""
    p = subprocess.Popen([sys.executable, "bot.py"])
    procs.append(p)
    log.info("디스코드 봇 subprocess 시작 (PID %d)", p.pid)
    return p


def start_web():
    """FastAPI 웹 서버를 subprocess로 실행."""
    port = os.environ.get("PORT", "8000")
    p = subprocess.Popen(
        [sys.executable, "-c",
         f"import uvicorn; uvicorn.run('web_api:app', host='0.0.0.0', port={port})"]
    )
    procs.append(p)
    log.info("FastAPI 웹 subprocess 시작 (PID %d, port %s)", p.pid, port)
    return p


def cleanup(*_):
    log.info("종료 신호 수신 — 자식 프로세스 정리")
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # 봇 먼저 시작
    bot_proc = start_bot()
    # 웹 시작
    web_proc = start_web()

    # 자식 프로세스 중 하나라도 죽으면 전체 종료 (컨테이너 재시작 유도)
    while True:
        if bot_proc.poll() is not None:
            log.error("봇 프로세스 종료됨 (code %s)", bot_proc.returncode)
            break
        if web_proc.poll() is not None:
            log.error("웹 프로세스 종료됨 (code %s)", web_proc.returncode)
            break
        try:
            bot_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    cleanup()


if __name__ == "__main__":
    main()
