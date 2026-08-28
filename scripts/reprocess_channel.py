# 1회용 재처리: #scrim-result 채널의 과거 스크린샷을 재분석해 상대팀 스탯을 채운다.
#
# 동작:
#   - 배포 Postgres(DATABASE_PUBLIC_URL)에 직접 저장 — 재업로드 병합 덕에
#     이미 저장된 매치면 상대 스탯만 추가되고 중복 생성되지 않는다.
#   - bot.py의 analyze_images / write_to_db / date_str_from_message 를 그대로
#     재사용 (실제 봇과 동일한 경로 — 프롬프트 회귀 검증도 겸함).
#   - 재개 가능: processed 메시지 ID를 reprocess_state.json에 기록, 재시작 시 스킵.
#
# 사용: python -u scripts/reprocess_channel.py [처리할 최대 매치 수]
# 중단: Ctrl+C (다음 실행 시 이어서)
import asyncio
import base64
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

# ── 배포 DB 직접 연결 (db.py import 전에 환경변수 세팅) ────────────────────
if not os.environ.get("DATABASE_URL"):
    import subprocess

    try:
        out = subprocess.run(
            ["railway.exe", "variables", "--service", "Postgres", "--json"],
            capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        out = subprocess.run(
            "railway variables --service Postgres --json",
            capture_output=True, text=True, shell=True, check=True).stdout
    os.environ["DATABASE_URL"] = json.loads(out)["DATABASE_PUBLIC_URL"]
    print("배포 Postgres 공개 URL로 연결", flush=True)

import config  # noqa: E402
import db  # noqa: E402
import stats_repo  # noqa: E402  (_save_opponent_stats 재사용)
import discord  # noqa: E402
import bot  # noqa: E402  (analyze_images/date_str_from_message — import 시 init_db 포함)

STATE_PATH = os.path.join(ROOT, "reprocess_state.json")
LOG_PATH = os.path.join(ROOT, "reprocess_log.txt")


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"done": [], "failed": {}}


def save_state(state: dict):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)


def find_existing_match(conn, date_str: str, mode: str, map_name):
    """재처리용 기존 매치 탐색: 날짜·모드·맵 일치 우선, 없으면 날짜·모드 후보가
    정확히 1개일 때만 채택. 우리 스탯은 건드리지 않고 enemy만 채우기 위한 탐색."""
    rows = conn.execute(db._adapt_sql(
        """SELECT id FROM matches
           WHERE match_date=? AND mode=?
             AND (map_name=? OR map_name IS NULL OR ? IS NULL)
           ORDER BY id"""), (date_str, mode, map_name, map_name)).fetchall()
    exact = [r["id"] for r in rows]
    if not exact and not map_name:
        # 맵을 못 읽은 경우: 날짜·모드 후보가 유일할 때만
        rows2 = conn.execute(db._adapt_sql(
            "SELECT id FROM matches WHERE match_date=? AND mode=? ORDER BY id"),
            (date_str, mode)).fetchall()
        if len(rows2) == 1:
            return rows2[0]["id"]
        return None
    return exact[0] if len(exact) == 1 else None


def roster_guard(conn, players: list) -> bool:
    """players 중 기존 우리 선수(players/aliases)와 하나라도 겹치면 True.
    전혀 안 겹치면 비-스크림 이미지로 판단해 스킵."""
    names = {((p.get("name") or "").strip()) for p in players}
    for n in names:
        if not n:
            continue
        row = conn.execute(db._adapt_sql(
            "SELECT 1 FROM players WHERE LOWER(name)=LOWER(?)"), (n,)).fetchone()
        if row:
            return True
        row = conn.execute(db._adapt_sql(
            "SELECT 1 FROM aliases WHERE LOWER(ign)=LOWER(?)"), (n,)).fetchone()
        if row:
            return True
def log_line(msg: str):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


async def main():
    max_matches = int(sys.argv[1]) if len(sys.argv) > 1 else None
    state = load_state()
    done_ids = set(state["done"])

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            ch = await client.fetch_channel(config.WATCH_CHANNEL_ID)
            print(f"로그인: {client.user} / 채널 #{ch.name}", flush=True)

            # 오래된 것부터 순회 (재업로드 병합이 시간순으로 자연스럽게 작동)
            # 2026-07 이전 스크린샷은 포맷이 달라 GLM이 map/적팀을 못 읽는다 (실측) —
            # 기본 7/1부터, 인자 2개째로 시작 날짜 오버라이드.
            since = sys.argv[2] if len(sys.argv) > 2 else "2026-07-01"
            targets = []
            async for m in ch.history(limit=None, oldest_first=True):
                if bot.date_str_from_message(m) < since:
                    continue
                imgs = [a for a in m.attachments
                        if a.content_type and a.content_type.startswith("image/")]
                if len(imgs) >= 2 and m.id not in done_ids:
                    targets.append((m, imgs))
            total = len(targets)
            print(f"대상: {total}매치 (이미 처리: {len(done_ids)})", flush=True)
            if max_matches:
                targets = targets[:max_matches]
                print(f"이번 실행 제한: {max_matches}매치", flush=True)

            ok_n = fail_n = skip_n = 0
            for i, (m, imgs) in enumerate(targets, 1):
                date_str = bot.date_str_from_message(m)
                try:
                    # Discord 첨부 URL은 만료 시그니처가 달려 Z.ai가 못 받아온다 —
                    # bytes로 직접 내려받아 base64 data URL로 전송 (tournament/vision 패턴).
                    datas = []
                    for a in imgs[:2]:
                        raw = await a.read()
                        mime = (a.content_type or "image/jpeg").split(";")[0]
                        datas.append(f"data:{mime};base64,{base64.b64encode(raw).decode()}")
                    result = await asyncio.to_thread(
                        bot.analyze_images, datas[0], datas[1])
                    players = result.get("players") or []
                    enemy = result.get("enemy_players") or []
                    if not players:
                        raise ValueError("players 없음 (GPT 응답 이상)")

                    with db.get_conn() as conn:
                        if not roster_guard(conn, players):
                            line = (f"[{i}/{len(targets)}] msg={m.id} {date_str} "
                                    f"스킵: 우리 로스터와 일치 없음 (비-스크림 이미지)")
                            print(line, flush=True)
                            log_line(line)
                            state["done"].append(m.id)
                            skip_n += 1
                            continue

                        match_id = find_existing_match(
                            conn, date_str, result.get("mode", "HP"), result.get("map"))
                        if not match_id:
                            # 기존 매치를 확정 못 찾으면 저장하지 않는다 — 재처리는
                            # '기존 매치에 enemy 채우기'가 목적이지 신규/변형 저장이 아님.
                            line = (f"[{i}/{len(targets)}] msg={m.id} {date_str} "
                                    f"{result.get('mode')} map={result.get('map')} "
                                    f"스킵: 대응 기존 매치 미확정 (map=None·후보 다중)")
                        else:
                            # 기존 매치 발견 → 우리 스탯은 그대로, enemy만 주입
                            opp = stats_repo._save_opponent_stats(
                                conn, match_id, result.get("mode", "HP"), enemy)
                            line = (f"[{i}/{len(targets)}] msg={m.id} {date_str} "
                                    f"{result.get('mode')} map={result.get('map')} "
                                    f"기존매치={match_id} enemy_saved={opp.get('saved')} "
                                    f"team={opp.get('team_id')}")
                    print(line, flush=True)
                    log_line(line)
                    state["done"].append(m.id)
                    done_ids.add(m.id)
                    ok_n += 1
                except Exception as e:
                    line = f"[{i}/{len(targets)}] msg={m.id} {date_str} 실패: {type(e).__name__}: {e}"
                    print(line, flush=True)
                    log_line(line)
                    state["failed"][str(m.id)] = f"{type(e).__name__}: {e}"
                    fail_n += 1
                save_state(state)
                await asyncio.sleep(2)  # 게이트웨이/API 여유

            print(f"완료: 성공 {ok_n} / 스킵 {skip_n} / 실패 {fail_n} (로그: {LOG_PATH})", flush=True)
        except Exception as e:
            print(f"[오류] {type(e).__name__}: {e}", flush=True)
        finally:
            await client.close()

    await client.start(config.DISCORD_TOKEN)


asyncio.run(main())
