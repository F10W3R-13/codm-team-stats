# GPT 자연어 인사이트 생성
#
# analytics.py가 만든 숫자 데이터를 GPT에게 넘겨
# 자연어 코칭 인사이트로 요약한다.
# (숫자만 보여주는 것보다 "Shisui가 이번 매치 폼이 좋았다" 식의 통찰이 유용)
#
# 모든 함수는 lang 파라미터("ko"/"en"/"es")를 받아 응답 언어를 제어한다.
# 코치용 페이지는 ko, 선수용은 en/es.

import json

import config
from openai import OpenAI

_openai = None

# 언어별 시스템 프롬프트 지시문
_LANG_INSTRUCT = {
    "ko": "한국어로",
    "en": "in English",
    "es": "en español",
}


def _client():
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=config.OPENAI_API_KEY)
    return _openai


def _lang_instruction(lang: str) -> str:
    return _LANG_INSTRUCT.get(lang, _LANG_INSTRUCT["ko"])


def match_insight(report: dict, lang: str = "ko") -> str:
    """매치 리포트 데이터 → 1-2문장 자연어 인사이트.

    실패 시 빈 문자열 반환 (리포트 표시에 영향 주지 않음).
    """
    if not report:
        return ""
    try:
        data = {
            "mode": report["mode"],
            "mom": report["mom"],
            "best": report["best"],
            "worst": report["worst"],
            "team_totals": report["team_totals"],
            "players": report["players"],
        }
        li = _lang_instruction(lang)
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            temperature=0.5,
            max_tokens=300,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a CODM mobile esports team data analyst. "
                        f"Write 1-2 sentences of key insight from the match stats JSON. "
                        f"Provide insight (who had good form, team strengths/weaknesses, "
                        f"what stands out), not just a list of numbers. Concise, for Discord. "
                        f"Respond {li}."
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return ""


def weekly_insight(report: dict, lang: str = "ko") -> str:
    """주간 트렌드 데이터 → 자연어 요약."""
    if not report or not report.get("players"):
        return ""
    try:
        data = {
            "period": report["period"],
            "matches_recent": report["matches_recent"],
            "players": report["players"],
        }
        li = _lang_instruction(lang)
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            temperature=0.5,
            max_tokens=350,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a CODM esports team analyst. Summarize the weekly trend data "
                        f"in 2-3 sentences {li}. Include rising/falling players, notable changes, "
                        f"and coaching suggestions. Concise and actionable, for Discord."
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return ""


def trend_insight(trend: dict, lang: str = "ko") -> str:
    """선수 트렌드 데이터 → 자연어 폼 진단."""
    if not trend:
        return ""
    try:
        data = {
            "name": trend["name"],
            "mode": trend["mode"],
            "recent_matches": trend["recent_matches"],
            "recent": trend["recent"],
            "overall": trend["overall"],
            "delta": trend["delta"],
            "last_matches": trend["last_matches"],
        }
        li = _lang_instruction(lang)
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            temperature=0.5,
            max_tokens=300,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a CODM esports player form analyst. Diagnose the player's "
                        f"recent form vs overall average in 1-2 sentences {li}. "
                        f"Include whether rising/falling with specific numeric evidence. Concise."
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return ""


def player_profile_insight(stats: dict, team_hp: dict = None, lang: str = "ko") -> str:
    """선수 프로필 페이지용 종합 인사이트 (웹).

    강점/약점(팀 평균 대비), 플레이 스타일 치우침, 안정성 등을
    자연어로 요약. 실패 시 빈 문자열.
    """
    if not stats or not (stats.get("hp") or stats.get("snd")):
        return ""
    try:
        data = {
            "name": stats["name"],
            "hp": stats.get("hp"),
            "snd": stats.get("snd"),
            "team_hp_avg": team_hp,
        }
        li = _lang_instruction(lang)
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            temperature=0.5,
            max_tokens=400,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a CODM esports team data analyst. "
                        f"Write 3-5 sentences of coaching insight from a player's overall stats "
                        f"and team average {li}. "
                        f"Include: 1) clear strengths/weaknesses vs team average (mention ±%), "
                        f"2) play style bias (e.g. slayer/objective/balanced — infer from OBJ, "
                        f"CapKill, ZCS, DPD), 3) form stability (mention std dev if present). "
                        f"Grounded in numbers, no over-interpretation. Concise and actionable, for web display."
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return ""


def team_insight(team_data: dict, lang: str = "ko") -> str:
    """팀 전체 인사이트 — 팀 추세 + 맵별 성적 + 맵별 선수 종합.

    팀 추세(상승/하락), 강/약점 맵, 맵별 에이스/약점 선수 등을
    자연어로 요약. 밴픽 코칭 관점 포함. 실패 시 빈 문자열.
    """
    if not team_data:
        return ""
    try:
        li = _lang_instruction(lang)
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            temperature=0.5,
            max_tokens=500,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a CODM esports team data analyst advising the coach on map strategy. "
                        f"Write 4-6 sentences of team insight {li} from the JSON data which includes: "
                        f"team trend (recent vs season avg), per-map team K/D, and per-map player strengths. "
                        f"Cover: 1) overall team trajectory (rising/falling), "
                        f"2) strongest and weakest maps with K/D evidence, "
                        f"3) which players excel/struggle on key maps (for roster/map-pick decisions), "
                        f"4) a brief map ban/pick suggestion if data supports it. "
                        f"Grounded in numbers. Concise, actionable, for web display."
                    ),
                },
                {"role": "user", "content": json.dumps(team_data, ensure_ascii=False)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return ""
