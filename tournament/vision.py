"""GPT-4.1 비전 호출 래퍼 (토너먼트 양쪽 10명 파싱).

부모 bot.py의 analyze_images와 동일 패턴:
- model=gpt-4.1, temperature=0, max_tokens=2048, response_format=json_object
- 차이: 부모는 Discord URL을 받지만 토너먼트는 업로드된 파일 bytes를 base64 인코딩.
- 차이: 프롬프트는 prompt_tournament.PROMPT (양쪽 파싱).
"""
import base64
import json
import os

from openai import OpenAI

import prompt_tournament

_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


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
    completion = _client.chat.completions.create(
        model="gpt-4.1",
        temperature=0.0,
        max_tokens=2048,
        response_format={"type": "json_object"},
        timeout=60,
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
