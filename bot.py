# CODM 스탯 봇
# make.com 시나리오 "CODM stats interpreter (HP + SND)"를 디스코드 봇 하나로 재현.
#
# 동작 흐름:
#   1. scrim-result 채널에 이미지 2장 첨부 메시지가 오면
#   2. GPT-4.1 비전으로 2장의 스크린샷을 분석 (HP/SND 모드 판별 + 선수 5명 통계 JSON)
#   3. 모드에 따라 구글 시트(Database_HP / Database_SND)에 선수별 행 추가
#
# make.com과의 차이: 메시지 작성 시간(한국시)을 Date 열에 자동 기록.

import asyncio
import json
import logging
from datetime import timezone, timedelta

import discord
from discord.ext import commands
from openai import OpenAI
from dotenv import load_dotenv

# .env 파일이 있으면 환경변수로 로드 (config.py보다 먼저 실행되어야 함)
load_dotenv()

import config
import db
import stats_repo
from prompt import build_system_prompt, DEFAULT_ROSTER

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("codm-bot")

KST = timezone(timedelta(hours=9))

# ── 외부 클라이언트 초기화 ────────────────────────────────────────────────
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

# 데이터베이스 초기화 (없으면 생성)
db.init_db()

intents = discord.Intents.default()
intents.message_content = True   # Message Content Intent (개발자 포털에서 활성화 필수)

bot = commands.Bot(command_prefix="!", intents=intents)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────
def load_roster() -> list:
    """DB에서 현재 로스터(players.name)를 로드. 실패/비어있으면 DEFAULT_ROSTER 폴백."""
    try:
        with db.get_conn() as conn:
            rows = conn.execute("SELECT name FROM players ORDER BY id").fetchall()
            roster = [r["name"] for r in rows if r["name"]]
            return roster or list(DEFAULT_ROSTER)
    except Exception:
        log.exception("로스터 로드 실패 — DEFAULT_ROSTER 폴백")
        return list(DEFAULT_ROSTER)


def analyze_images(url1: str, url2: str, roster: list = None) -> dict:
    """GPT-4.1 비전으로 두 스크린샷을 분석해 통계 JSON(dict)을 반환.

    roster: 동적 주입할 표준 선수명 리스트. None이면 load_roster()로 DB에서 로드.
      GPT가 우리 팀 식별 정규화 기준으로 쓴다 (OCR correction hint 역할).

    make.com의 OpenAI 모듈 설정과 동일:
      - messages: [user(프롬프트), user(image1), user(image2)]
      - response_format: json_object
      - temperature: 0, top_p: 0, max_tokens: 2048
    """
    if roster is None:
        roster = load_roster()
    system_prompt = build_system_prompt(roster)
    completion = openai_client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=config.OPENAI_TEMPERATURE,
        max_tokens=config.OPENAI_MAX_TOKENS,
        response_format={"type": "json_object"},
        timeout=60,
        n=1,
        messages=[
            {
                "role": "user",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": url1, "detail": "auto"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": url2, "detail": "auto"},
                    }
                ],
            },
        ],
    )
    raw = completion.choices[0].message.content
    return json.loads(raw)


def date_str_from_message(message: discord.Message) -> str:
    """디스코드 메시지 작성 시간(UTC)을 한국시(KST) YYYY-MM-DD로 변환."""
    created_kst = message.created_at.astimezone(KST)
    return created_kst.strftime("%Y-%m-%d")


def write_to_db(mode: str, players: list, date_str: str,
                map_name: str = None, result: str = None,
                team_score: int = None, opponent_score: int = None) -> dict:
    """GPT 분석 결과 한 매치를 SQLite DB에 저장.

    반환: save_match 결과 dict (match_id, saved, mode, result, scores, map 포함)
    """
    return stats_repo.save_match(
        mode=mode, players=players, match_date=date_str,
        map_name=map_name, result=result,
        team_score=team_score, opponent_score=opponent_score,
    )


# ── 봇 이벤트 ─────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    # 슬래시 명령 Cog 로드 (이미 로드되어 있으면 스킵)
    try:
        await bot.load_extension("commands_cog")
    except discord.ext.commands.ExtensionAlreadyLoaded:
        pass

    # 슬래시 명령을 디스코드에 동기화 (글로벌 — 최대 1시간 전파, 개발 중엔 길드 즉시)
    try:
        synced = await bot.tree.sync()
        log.info("슬래시 명령 동기화: %d개", len(synced))
    except Exception:
        log.exception("슬래시 명령 동기화 실패")

    log.info("로그인 완료: %s (id=%s)", bot.user, bot.user.id)
    log.info("감시 채널: %s", config.WATCH_CHANNEL_ID)

    # ===== 진단: 봇이 실제로 보고 있는 서버/채널 덤프 =====
    log.info("[DIAG] message_content intent = %s", intents.message_content)
    log.info("[DIAG] 봇이 가입한 서버 수 = %d", len(bot.guilds))
    for g in bot.guilds:
        log.info("[DIAG] guild: id=%s name=%s", g.id, g.name)
        try:
            ch = bot.get_channel(config.WATCH_CHANNEL_ID)
            log.info("[DIAG] get_channel(%s) → %s (type=%s name=%s guild_id=%s)",
                     config.WATCH_CHANNEL_ID,
                     ch, type(ch).__name__ if ch else None,
                     getattr(ch, "name", None), getattr(ch, "guild.id", None) if ch else None)
        except Exception:
            log.exception("[DIAG] get_channel failed")
    # =====================================================


@bot.event
async def on_message(message: discord.Message):
    # ===== 진단 로그 (원인 파악 후 제거 예정) =====
    log.info("[DIAG] on_message fired: channel_id=%s author=%s attachments=%d content_types=%s",
             message.channel.id, message.author, len(message.attachments),
             [a.content_type for a in message.attachments])

    # 봇 자신의 메시지는 무시
    if message.author.bot:
        return

    # 감시 채널이 아니면 무시 (다른 명령어 처리도 하지 않음)
    if message.channel.id != config.WATCH_CHANNEL_ID:
        log.info("[DIAG] ignored: channel mismatch (msg_from=%s watch=%s)",
                 message.channel.id, config.WATCH_CHANNEL_ID)
        return

    # 첨부 이미지 2장인지 확인
    attachments = message.attachments
    image_attachments = [
        a for a in attachments
        if a.content_type and a.content_type.startswith("image/")
    ]
    if len(image_attachments) < 2:
        log.info("[DIAG] in watch channel but images<2: total=%d images=%d types=%s",
                 len(attachments), len(image_attachments),
                 [a.content_type for a in attachments])
        # 스크린샷 2장이 아니면 반응하지 않음 (make.com도 limit만 있고 별도 안내는 없었으나
        # 사용자 경험을 위해 안내만 남긴다)
        if image_attachments:
            await message.reply(
                "Please upload both screenshots (stats + detail). "
                f"Images detected: {len(image_attachments)}"
            )
        return

    url1, url2 = image_attachments[0].url, image_attachments[1].url
    log.info("2 screenshots detected — analysis started (msg id=%s)", message.id)

    async with message.channel.typing():
        try:
            # 동기 GPT 비전 호출(timeout 60s) — 이벤트 루프 블로킹 방지
            result = await asyncio.get_running_loop().run_in_executor(
                None, analyze_images, url1, url2)
        except json.JSONDecodeError as e:
            log.exception("GPT response JSON parse failed")
            await message.reply(f"❌ Failed to parse the analysis result as JSON: `{e}`")
            return
        except Exception as e:
            log.exception("GPT vision call failed")
            await message.reply(f"❌ An error occurred during image analysis: `{e}`")
            return

        mode = result.get("mode", "").upper()
        # 신규 프롬프트는 "players" 키 사용. 구버전 호환용 "result" fallback.
        # 단, 신규 프롬프트의 "result"는 승패 문자열("WIN"/"LOSS")이므로 리스트인 경우만 폴백.
        _result_raw = result.get("result", [])
        players = result.get("players") or (_result_raw if isinstance(_result_raw, list) else [])
        match_result = result.get("result") if isinstance(result.get("result"), str) else None
        team_score = result.get("team_score")
        opponent_score = result.get("opponent_score")
        map_name = result.get("map")

        if not players:
            await message.reply("⚠️ Analysis complete, but no player data was found.")
            return

        # AI 누락(4명만 읽음 등) 조기 감지 — 재업로드하면 자동 병합되므로 안내.
        if len(players) < 5:
            log.warning("선수 %d명만 인식됨 (5명 기대). 재업로드 시 자동 병합 또는 /admin에서 추가.", len(players))

        if mode not in ("HP", "SND"):
            await message.reply(
                f"⚠️ Could not determine the game mode (mode={mode!r}). "
                "Please check the screenshots."
            )
            return

        date_str = date_str_from_message(message)
        try:
            result_info = write_to_db(
                mode, players, date_str,
                map_name=map_name, result=match_result,
                team_score=team_score, opponent_score=opponent_score,
            )
        except Exception as e:
            log.exception("DB write failed")
            await message.reply(f"❌ Error saving to database: `{e}`")
            return

        # Completion summary (승패/점수/맵 표시)
        names = ", ".join(p.get("name", "?") for p in players)
        if result_info.get("duplicate"):
            if result_info["saved"] > 0:
                head = (
                    f"♻️ **{mode}** re-upload merged into match #{result_info['match_id']} "
                    f"(+{result_info['saved']} players)"
                )
            else:
                head = (
                    f"♻️ **{mode}** duplicate — already recorded as "
                    f"match #{result_info['match_id']}, nothing saved"
                )
        else:
            head = (
                f"✅ **{mode}** analysis complete — {result_info['saved']} players saved "
                f"(match #{result_info['match_id']})"
            )
        summary = (
            f"{head}\n"
            f"Players: {names}\n"
            f"Date: {date_str}"
        )
        if len(players) < 5:
            summary += (
                f"\n⚠️ Only {len(players)} players detected. "
                "Re-upload the same screenshots to auto-merge missing players, "
                "or fix it in /admin."
            )
        # 승패/점수/맵이 추출됐으면 추가
        extras = []
        if match_result:
            score_str = ""
            if team_score is not None and opponent_score is not None:
                score_str = f" ({team_score}:{opponent_score})"
            extras.append(f"Result: **{match_result}**{score_str}")
        if map_name:
            extras.append(f"Map: {map_name}")
        if extras:
            summary += "\n" + " · ".join(extras)
        await message.reply(summary)

        # Auto match report (right after analysis completes)
        try:
            import report_embeds
            # 내부에서 동기 GPT 인사이트 호출(최대 15s) — executor로 위임
            embed = await asyncio.get_running_loop().run_in_executor(
                None, report_embeds.build_match_report_embed, result_info["match_id"])
            if embed:
                await message.channel.send(embed=embed)
        except Exception:
            log.exception("Auto match report generation failed (record was saved)")


def main():
    log.info("봇 시작 중...")
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
