# GPT 비전 분석 프롬프트 — 전체 매치 스크린샷용
#
# 변경 배경 (CLAUDE.md §10 참고):
# - 기존: 우리 팀만 크롭한 사진 2장 → 우리 팀 스탯만 추출. 승패/맵은 수동.
# - 신규: 전체 매치 스크린샷 2장(기본 탭 + 디테일 탭) → 우리 팀 식별 후 스탯 +
#         승패/점수/맵/모드 자동 추출. 적 팀 데이터는 무시(단계적 도입).
#
# 핵심 도전: 좌/우 양쪽 팀 중 어느 쪽이 우리 팀인지 식별해야 함.
# 전략: 로스터 + alias에 매칭되는 선수가 많은 쪽 = 우리 팀.
#
# 로스터는 DB에서 동적 주입(build_system_prompt). DB 장애/빈 경우 DEFAULT_ROSTER 폴백.

# 폴백 로스터 (DB에서 로드 실패하거나 비어있을 때). 기존 하드코딩값 유지.
DEFAULT_ROSTER = ["Shisui", "Cartels", "unravel", "Kingz", "Maozyn", "Exile"]

_PROMPT_TEMPLATE = (
    "이제부터 차례대로 제공될 2장의 사진은 동일한 CODM 모바일 이스포츠 매치의 "
    "전체 결과 화면입니다. 각 사진에는 좌측 팀(파란색)과 우측 팀(빨간색) 양쪽의 "
    "선수 데이터가 함께 표시되어 있습니다. 당신의 임무는 다음 4단계를 수행하는 것입니다.\n\n"    "[1단계 — 게임 모드 판별]\n"
    "사진 상단의 큰 텍스트를 보고 모드를 판별하세요.\n"
    "- 'HARDPOINT'가 보이면 → 모드는 \"HP\"\n"
    "- 'SEARCH AND DESTROY' 또는 'SEARCH & DESTROY'가 보이면 → 모드는 \"SND\"\n"
    "열 제목으로도 보조 판단: ADR, FIRST KILL(S), LONE WOLF WIN 열이 있으면 SND, "
    "Total Damage, Capture Kill 열이 있거나 TIME 열이 있으면 HP.\n\n"
    "[2단계 — 우리 팀 식별 ★가장 중요]\n"
    "우리 팀 로스터(표준 이름): {roster}\n"
    "두 사진의 양쪽(좌측/우측) 팀 선수 이름을 읽고, 어느 쪽이 우리 팀인지 판별하세요.\n"
    "- 대소문자, 클랜태그, 특수문자, 깨진 글자와 무관하게 위 로스터에 가장 유사한 "
    "선수가 많은 쪽이 우리 팀입니다. (예: 'Renegul8808'='Shisui', 'BLACKPINK'='Cartels')\n"
    "- 용병/다른 닉네임 선수가 섞여 있어도, 로스터 매칭이 더 많은 쪽을 우리 팀으로 합니다.\n"
    "- 우리 팀이 좌측인지 우측인지를 먼저 확정한 뒤, 그쪽 데이터만 추출하세요. "
    "절대 적 팀(반대쪽) 선수의 스탯을 결과에 넣지 마세요.\n\n"
    "[3단계 — 승패 / 점수 / 맵 추출]\n"
    "사진 상단의 결과 텍스트에서 추출하세요:\n"
    "- result: 'VICTORY' → \"WIN\", 'DEFEAT' → \"LOSS\" (우리 팀 기준)\n"
    "  * 주의: VICTORY/DEFEAT와 함께 표시되는 점수가 '우리:상대' 순서인지 확인. "
    "    보통 좌측 팀 점수가 먼저 오므로, 우리 팀이 좌측이면 첫 번째 점수가 우리 점수.\n"
    "- team_score: 우리 팀 점수 (정수)\n"
    "- opponent_score: 상대 팀 점수 (정수)\n"
    "- map: 모드 텍스트 옆의 맵 이름 (예: 'HARDPOINT COMBINE' → 'Combine'). "
    "  Title Case로 정규화. 안 보이면 null.\n\n"
    "[4단계 — 우리 팀 선수 스탯 추출]\n"
    "확정한 우리 팀 쪽의 선수들만(보통 4~5명) 추출하세요. 이름은 로스터의 표준 이름으로 변환.\n"
    "완전히 다른 용병 닉네임은 그대로 출력. 읽을 수 없는 글자도 보이는 그대로 적거나 "
    "\"Unknown1\", \"Unknown2\" 형식으로 채우세요.\n\n"
    "■ HP 모드 선수 필드: name, k, d, kd_ratio, time, score, impact, total_damage, capture_kill\n"
    "  - kd_ratio = k/d (소수점 둘째 자리), d=0이면 k값 그대로\n"
    "  - time = '분:초'를 순수 초(Seconds)로 변환\n"
    "■ SND 모드 선수 필드: name, k, d, a, kd_ratio, score, impact, adr, first_kill, lone_wolf_win\n"
    "  - K/D/A가 '17/12/1'이면 k=17, d=12, a=1\n"
    "\n"
    "(1번/2번 사진의 순서가 반대여도 알아서 적용하세요. 1번 사진이 기본 탭 "
    "[SCORE, K/D/A, TIME, IMPACT], 2번이 디테일 탭 [Total Damage, Capture Kill] 등)\n\n"
    "[출력 형식 — 순수 JSON Object만, 마크다운 없이]\n"
    "주의: 매치 결과는 \"result\" (문자열 WIN/LOSS), 선수 목록은 \"players\" (배열)로 "
    "서로 다른 키를 사용합니다.\n"
    "HP 예시:\n"
    "{\n"
    "\"mode\": \"HP\",\n"
    "\"result\": \"WIN\",\n"
    "\"team_score\": 250,\n"
    "\"opponent_score\": 198,\n"
    "\"map\": \"Combine\",\n"
    "\"our_team_side\": \"left\",\n"
    "\"players\": [{\"name\": \"이름\", \"k\": 0, \"d\": 0, \"kd_ratio\": 0.0, \"time\": 0, \"score\": 0, \"impact\": 0, \"total_damage\": 0, \"capture_kill\": 0}]\n"
    "}\n\n"
    "SND 예시:\n"
    "{\n"
    "\"mode\": \"SND\",\n"
    "\"result\": \"LOSS\",\n"
    "\"team_score\": 4,\n"
    "\"opponent_score\": 6,\n"
    "\"map\": \"Coastal\",\n"
    "\"our_team_side\": \"right\",\n"
    "\"players\": [{\"name\": \"이름\", \"k\": 0, \"d\": 0, \"a\": 0, \"kd_ratio\": 0.0, \"score\": 0, \"impact\": 0, \"adr\": 0, \"first_kill\": 0, \"lone_wolf_win\": 0}]\n"
    "}"
)


def build_system_prompt(roster: list = None) -> str:
    """GPT 비전 프롬프트 생성. 로스터를 DB에서 동적 주입.

    roster: 표준 선수명 리스트. None/빈 리스트 → DEFAULT_ROSTER 폴백.
    """
    roster_list = roster if roster else DEFAULT_ROSTER
    roster_json = "[" + ", ".join(f'"{n}"' for n in roster_list) + "]"
    return _PROMPT_TEMPLATE.replace("{roster}", roster_json)


# 하위 호환: 기존 import(prompt.SYSTEM_PROMPT) 대응용 상수.
# 동적 로스터가 필요 없는 곳(예: 봇 부팅 직전)은 이것을, 봇 본체는 build_system_prompt 사용.
SYSTEM_PROMPT = build_system_prompt()
