# CODM 스탯 봇
# make.com 시나리오 "CODM stats interpreter (HP + SND)"를 디스코드 봇 하나로 재현.
#
# 동작 흐름:
#   1. scrim-result 채널에 이미지 2장 첨부 메시지가 오면
#   2. GPT 비전으로 2장의 스크린샷을 분석 (HP/SND 모드 판별 + 선수 5명 통계 JSON)
#   3. 모드에 따라 구글 시트(Database_HP / Database_SND)에 선수별 행 추가
#
# make.com과의 차이: 메시지 작성 시간(한국시)을 Date 열에 자동 기록.

import asyncio
import json
import logging
from datetime import timezone, timedelta

import discord
from discord.ext import commands
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
# RAM 다이어트: openai 패키지(pydantic/httpx 포함, ~20MB RSS)를 부팅 즉시 로드하지 않고
# 첫 스크린샷 분석 시점에 지연 로드한다. 봇 기동/명령 처리엔 불필요한 의존성.
openai_client = None


def get_openai_client():
    global openai_client
    if openai_client is None:
        from openai import OpenAI
        openai_client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
    return openai_client

# 데이터베이스 초기화 (없으면 생성)
db.init_db()

intents = discord.Intents.default()
intents.message_content = True   # Message Content Intent (개발자 포털에서 활성화 필수)

bot = commands.Bot(command_prefix="!", intents=intents, max_messages=200)  # 메시지 캐시 축소 (기본 1000) — 히스토리/참조 읽기 미사용


# ── 헬퍼 ──────────────────────────────────────────────────────────────────
def load_roster() -> list:
    """DB players 테이블 로드. 상대팀에 동명(norm 일치)이 존재하는 이름은 제외 —
    오염 이름이 GPT 로스터 힌트로 주입되면 상대쪽을 우리팀으로 식별하는
    자기강화 오염이 생긴다(2026-09-23 uD 선수 유입 실증)."""
    try:
        with db.get_conn() as conn:
            rows = conn.execute("SELECT name FROM players ORDER BY id").fetchall()
            names = [r["name"] for r in rows if r["name"]]
            if names:
                import opponent_matching
                opp_norms = db.opponent_name_norms(conn)
                roster = [n for n in names
                          if opponent_matching.norm_name(n) not in opp_norms]
                return roster or names
            return list(DEFAULT_ROSTER)
    except Exception:
        log.exception("로스터 로드 실패 — DEFAULT_ROSTER 폴백")
        return list(DEFAULT_ROSTER)


def analyze_images(url1: str, url2: str, roster: list = None) -> dict:
    """GPT 비전으로 두 스크린샷을 분석해 통계 JSON(dict)을 반환.

    roster: 동적 주입할 표준 선수명 리스트. None이면 load_roster()로 DB에서 로드.
      GPT가 우리 팀 식별 정규화 기준으로 쓴다 (OCR correction hint 역할).

    make.com의 OpenAI 모듈 설정을 계승:
      - messages: [user(프롬프트), user(image1), user(image2)]
      - response_format: json_object
      - temperature/max_tokens 는 config.chat_params()가 모델 세대에 맞게 보정
    """
    if roster is None:
        roster = load_roster()
    system_prompt = build_system_prompt(roster)
    completion = get_openai_client().chat.completions.create(
        model=config.OPENAI_MODEL,
        response_format={"type": "json_object"},
        timeout=60,
        n=1,
        **config.chat_params(config.OPENAI_TEMPERATURE, config.OPENAI_MAX_TOKENS),
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
                team_score: int = None, opponent_score: int = None,
                enemy_players: list = None) -> dict:
    """GPT 분석 결과 한 매치를 SQLite DB에 저장.

    반환: save_match 결과 dict (match_id, saved, mode, result, scores, map 포함)
    """
    return stats_repo.save_match(
        mode=mode, players=players, match_date=date_str,
        map_name=map_name, result=result,
        team_score=team_score, opponent_score=opponent_score,
        enemy_players=enemy_players,
    )


# ── 우리팀 방향 확인 플로우 ────────────────────────────────────────────────
# GPT 비전이 좌/우 어느 쪽이 우리팀인지 추측하지만, 용병·닉네임 변경으로 오판이
# 잦아 상대 선수 스탯이 우리팀으로 흡수되는 사고가 반복됐다(2026-09-23 uD 사례).
# 저장 전에 코치가 버튼으로 어느 쪽이 우리팀인지 확정한다 — 사람이 결정하므로
# 타팀 선수가 용병으로 와도 자유롭게 우리팀에 들어올 수 있다.
TEAM_CONFIRM_TIMEOUT = 600  # 초 — 이 시간 내 미응답 시 저장 없이 만료


def _side_display(players: list) -> str:
    """한쪽 팀 선수명 표시 — 정규화명과 화면 원본(ign_raw)이 다르면 병기."""
    parts = []
    for p in players:
        nm = (p.get("name") or "").strip() or "?"
        raw = (p.get("ign_raw") or "").strip()
        if raw and raw != nm:
            parts.append(f"{nm} ({raw})")
        else:
            parts.append(nm)
    return ", ".join(parts) if parts else "-"


async def _save_and_reply(confirm_msg: discord.Message, upload_message: discord.Message,
                          mode: str, players: list, enemy_players: list,
                          match_result: str, team_score, opponent_score,
                          map_name, date_str: str) -> None:
    """확정된 방향으로 저장하고, 확인 메시지를 완료 요약로 교체 + 리포트 임베드."""
    result_info = write_to_db(
        mode, players, date_str,
        map_name=map_name, result=match_result,
        team_score=team_score, opponent_score=opponent_score,
        enemy_players=enemy_players,
    )

    names = ", ".join(p.get("name", "?") for p in players) or "-"
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
    await confirm_msg.edit(content=summary)

    # Auto match report (right after analysis completes)
    try:
        import report_embeds
        # 내부에서 동기 GPT 인사이트 호출(최대 15s) — executor로 위임
        embed = await asyncio.get_running_loop().run_in_executor(
            None, report_embeds.build_match_report_embed, result_info["match_id"])
        if embed:
            await upload_message.channel.send(embed=embed)
    except Exception:
        log.exception("Auto match report generation failed (record was saved)")


class TeamConfirmView(discord.ui.View):
    """Team A(GPT 추정 우리팀)/Team B 중 어느 쪽이 우리팀인지 업로더가 확정."""

    def __init__(self, upload_message: discord.Message, analysis: dict):
        super().__init__(timeout=TEAM_CONFIRM_TIMEOUT)
        self.upload_message = upload_message
        self.analysis = analysis
        self.message = None  # 확인 요청 메시지 (타임아웃 시 비활성화용)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.upload_message.author.id:
            await interaction.response.send_message(
                "Only the uploader can confirm this match.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Team A is ours", style=discord.ButtonStyle.primary)
    async def pick_a(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        await self._save(interaction, swap=False)

    @discord.ui.button(label="Team B is ours", style=discord.ButtonStyle.secondary)
    async def pick_b(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        await self._save(interaction, swap=True)

    async def _save(self, interaction: discord.Interaction, swap: bool):
        self.stop()
        a = self.analysis
        players, enemy = a["players"], a["enemy_players"]
        result, ts, osc = a["result"], a["team_score"], a["opponent_score"]
        if swap:
            flipped = stats_repo.swap_sides(players, enemy, result, ts, osc)
            players, enemy = flipped["players"], flipped["enemy_players"]
            result, ts, osc = (flipped["result"], flipped["team_score"],
                               flipped["opponent_score"])
        await interaction.response.edit_message(view=None)
        try:
            await _save_and_reply(
                interaction.message, self.upload_message, a["mode"], players, enemy,
                result, ts, osc, a["map"], a["date"])
        except Exception as e:
            log.exception("DB write failed")
            await interaction.followup.send(f"❌ Error saving to database: `{e}`")

    async def on_timeout(self):
        if self.message is None:
            return
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(
                content=self.message.content +
                        "\n⏱️ Confirmation timed out — nothing saved. "
                        "Re-upload the screenshots to try again.",
                view=self)
        except Exception:
            log.exception("타임아웃 처리 실패")


async def _ask_team_confirmation(message: discord.Message, mode: str,
                                 players: list, enemy_players: list,
                                 match_result: str, team_score, opponent_score,
                                 map_name, date_str: str, gpt_side=None):
    """저장 전 확인 단계 — Team A/B 목록을 보여주고 업로더의 버튼 클릭을 기다린다."""
    gpt_mark = f" (GPT guess: {gpt_side})" if gpt_side else " (GPT guess)"
    map_part = f" · {map_name}" if map_name else ""
    text = (
        f"🎮 **{mode}**{map_part} — which team is ours?\n"
        f"**Team A**{gpt_mark}: {_side_display(players)}\n"
        f"**Team B**: {_side_display(enemy_players)}\n"
        f"_Nothing is saved until you confirm "
        f"(timeout {TEAM_CONFIRM_TIMEOUT // 60} min)._"
    )
    view = TeamConfirmView(message, {
        "mode": mode, "players": players, "enemy_players": enemy_players,
        "result": match_result, "team_score": team_score,
        "opponent_score": opponent_score, "map": map_name, "date": date_str,
    })
    view.message = await message.reply(text, view=view)


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
        enemy_players = result.get("enemy_players") or []

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
        # 저장 전 확인 단계 — 코치가 Team A/B 중 우리팀을 버튼으로 확정하면 저장된다.
        await _ask_team_confirmation(
            message, mode, players, enemy_players, match_result,
            team_score, opponent_score, map_name, date_str,
            gpt_side=result.get("our_team_side"))


def main():
    log.info("봇 시작 중...")
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
