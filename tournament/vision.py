"""GPT-4.1 비전 호출 래퍼 (토너먼트 양쪽 10명 파싱).

부모 bot.py의 analyze_images와 동일 패턴:
- model=gpt-4.1, temperature=0, max_tokens=2048, response_format=json_object
- 차이: 부모는 Discord URL을 받지만 토너먼트는 업로드된 파일 bytes를 base64 인코딩.
- 차이: 프롬프트는 prompt_tournament.PROMPT (양쪽 파싱).
"""
import base64
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

import _path_setup  # noqa: F401  (부모 디렉토리를 sys.path에 추가)
import prompt_tournament

# 부모 디렉토리의 .env 에서 OPENAI_API_KEY 자동 로드.
# (부모 bot.py:18-21 패턴과 동일 — 별도 export 없이 .env 만 있으면 동작.)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# 클라이언트는 실제 호출 시점에 생성 (import 시점엔 API 키가 없을 수 있음 —
# 테스트에서 analyze_two_screens 을 mock 할 때 모듈 import 단계가 실패하지 않도록).
_client = None


def _get_client():
    """OPENAI_API_KEY 가 설정된 실제 호출 시점에 클라이언트 생성 (lazy)."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _to_data_url(image_bytes: bytes) -> str:
    """이미지 bytes → data URL (GPT image_url 입력용)."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def analyze_two_screens(image_bytes_1: bytes, image_bytes_2: bytes) -> dict:
    """GPT 비전으로 2장 스크린샷 분석 → 양쪽 10명 스탯 dict.

    반환 구조: {mode, map, team_left_score, team_right_score,
               team_left: [선수×5], team_right: [선수×5]}
    예외: GPT 호출 실패 / JSON 파싱 실패 시 raise.
    """
    completion = _get_client().chat.completions.create(
        model="gpt-4.1",
        temperature=0.0,
        max_tokens=4096,
        response_format={"type": "json_object"},
        timeout=120,
        n=1,
        messages=[
            {"role": "user", "content": prompt_tournament.PROMPT},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": _to_data_url(image_bytes_1), "detail": "auto"}}]},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": _to_data_url(image_bytes_2), "detail": "auto"}}]},
        ],
    )
    raw = completion.choices[0].message.content
    return json.loads(raw)
