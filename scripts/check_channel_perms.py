# 1회용 진단: 봇의 채널 접근 권한 확인 (읽기 전용)
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import config  # noqa: E402
import discord  # noqa: E402


async def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            print(f"로그인: {client.user}", flush=True)
            for i in range(4):
                await asyncio.sleep(5)
                print(f"  {5 * (i + 1)}초 경과: 서버 {len(client.guilds)}개", flush=True)
                if client.guilds:
                    break
            for g in client.guilds:
                cached = g.get_channel(config.WATCH_CHANNEL_ID)
                print(f"  서버 '{g.name}' (id={g.id}): 감시 채널 캐시 = {'있음' if cached else '없음'}", flush=True)
            try:
                ch = await client.fetch_channel(config.WATCH_CHANNEL_ID)
                print(f"fetch 성공: #{getattr(ch, 'name', '?')} (type={type(ch).__name__})", flush=True)
                member = ch.guild.get_member(client.user.id)
                if member:
                    perms = ch.permissions_for(member)
                    print(f"봇의 실효 권한: 채널보기={perms.view_channel}, "
                          f"기록읽기={perms.read_message_history}, 메시지읽기={perms.read_messages}", flush=True)
                else:
                    print("길드 멤버 조회 실패(캐시 없음)", flush=True)
            except Exception as e:
                print(f"fetch 실패: {type(e).__name__}: {e}", flush=True)
        except Exception as e:
            print(f"[오류] {type(e).__name__}: {e}", flush=True)
        finally:
            await client.close()

    await client.start(config.DISCORD_TOKEN)


asyncio.run(main())
