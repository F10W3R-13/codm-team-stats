# 1회용 진단: 감시 채널의 스크린샷 재처리 대상 개수 세기 (읽기 전용)
# 사용: python -u scripts/count_screenshots.py
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import config  # noqa: E402
import discord  # noqa: E402


async def main():
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    stats = {"msgs": 0, "images": 0, "match_msgs": 0, "first": None, "last": None}

    @client.event
    async def on_ready():
        try:
            print(f"로그인: {client.user}", flush=True)
            ch = await client.fetch_channel(config.WATCH_CHANNEL_ID)
            print(f"채널 #{getattr(ch, 'name', ch.id)} 히스토리 스캔 중...", flush=True)
            scanned = 0
            async for m in ch.history(limit=None, oldest_first=True):
                scanned += 1
                if scanned % 500 == 0:
                    print(f"  ... {scanned}개 메시지 스캔 (이미지 {stats['images']}장)", flush=True)
                imgs = [a for a in m.attachments
                        if a.content_type and a.content_type.startswith("image/")]
                if not imgs:
                    continue
                stats["msgs"] += 1
                stats["images"] += len(imgs)
                if len(imgs) >= 2:
                    stats["match_msgs"] += 1
                if stats["first"] is None:
                    stats["first"] = m.created_at.date()
                stats["last"] = m.created_at.date()
            print(f"이미지 첨부 메시지: {stats['msgs']}", flush=True)
            print(f"총 이미지 장수: {stats['images']}", flush=True)
            print(f"2장 이상(=매치 업로드 단위, 봇 기준): {stats['match_msgs']}", flush=True)
            print(f"1장만 있는 메시지(봇이 무시한 것): {stats['msgs'] - stats['match_msgs']}", flush=True)
            print(f"기간: {stats['first']} ~ {stats['last']}", flush=True)
        except Exception as e:
            print(f"[오류] {type(e).__name__}: {e}", flush=True)
        finally:
            await client.close()

    await client.start(config.DISCORD_TOKEN)


asyncio.run(main())
