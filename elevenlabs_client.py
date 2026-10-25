"""ElevenLabs 클라이언트. 키는 .env의 ELEVENLABS_API_KEY에서 읽는다 (코드에 쓰지 않음)."""

import os

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

client = ElevenLabs()
