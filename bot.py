# CODM 스탯 봇
# make.com 시나리오 "CODM stats interpreter (HP + SND)"를 디스코드 봇 하나로 재현.
#
# 동작 흐름:
#   1. scrim-result 채널에 이미지 2장 첨부 메시지가 오면
#   2. GPT-4.1 비전으로 2장의 스크린샷을 분석 (HP/SND 모드 판별 + 선수 5명 통계 JSON)
#   3. 모드에 따라 구글 시트(Database_HP / Database_SND)에 선수별 행 추가
#
# make.com과의 차이: 메시지 작성 시간(한국시)을 Date 열에 자동 기록.

import json
import logging
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands
from openai import OpenAI
from dotenv import load_dotenv

# .env 파일이 있으면 환경변수로 로드 (config.py보다 먼저 실행되어야 함)
load_dotenv()

import config
import db
import stats_repo
from prompt import SYSTEM_PROMPT

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
def analyze_images(url1: str, url2: str) -> dict:
    """GPT-4.1 비전으로 두 스크린샷을 분석해 통계 JSON(dict)을 반환.

    make.com의 OpenAI 모듈 설정과 동일:
      - messages: [user(프롬프트), user(image1), user(image2)]
      - response_format: json_object
      - temperature: 0, top_p: 0, max_tokens: 2048
    """
    completion = openai_client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=config.OPENAI_TEMPERATURE,
        top_p=0,
        max_tokens=config.OPENAI_MAX_TOKENS,
        response_format={"type": "json_object"},
        n=1,
        messages=[
            {
                "role": "user",
                "content": SYSTEM_PROMPT,
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


@bot.event
async def on_message(message: discord.Message):
    # 봇 자신의 메시지는 무시
    if message.author.bot:
        return

    # 감시 채널이 아니면 무시 (다른 명령어 처리도 하지 않음)
    if message.channel.id != config.WATCH_CHANNEL_ID:
        return

    # 첨부 이미지 2장인지 확인
    attachments = message.attachments
    image_attachments = [
        a for a in attachments
        if a.content_type and a.content_type.startswith("image/")
    ]
    if len(image_attachments) < 2:
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
            result = analyze_images(url1, url2)
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
        players = result.get("players") or result.get("result", [])
        match_result = result.get("result") if isinstance(result.get("result"), str) else None
        team_score = result.get("team_score")
        opponent_score = result.get("opponent_score")
        map_name = result.get("map")

        if not players:
            await message.reply("⚠️ Analysis complete, but no player data was found.")
            return

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
        summary = (
            f"✅ **{mode}** analysis complete — {result_info['saved']} players saved "
            f"(match #{result_info['match_id']})\n"
            f"Players: {names}\n"
            f"Date: {date_str}"
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
            embed = report_embeds.build_match_report_embed(result_info["match_id"])
            if embed:
                await message.channel.send(embed=embed)
        except Exception:
            log.exception("Auto match report generation failed (record was saved)")


def main():
    log.info("봇 시작 중...")
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
