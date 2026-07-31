"""GPT 비전 프롬프트 — 토너먼트용 (양쪽 10명 전부 파싱).

부모 prompt.py와의 차이:
- 부모: our_team_side로 우리 팀 한쪽만 추출 (적 팀 무시)
- 토너먼트: team_left/team_right 양쪽 10명 전부 추출
- 제거: 우리 팀 식별 단계, "적 팀 스탯 넣지 마세요"
- 추가: team_left_score/team_right_score (양쪽 점수)
- 유지: 모드 판별, 맵 추출, HP/SND 필드, 2장(기본/디테일 탭) 처리
"""

PROMPT = (
    "이제부터 차례대로 제공될 2장의 사진은 동일한 CODM 모바일 이스포츠 매치의 "
    "전체 결과 화면입니다. 각 사진에는 좌측 팀과 우측 팀 양쪽의 선수 데이터가 "
    "함께 표시되어 있습니다. 당신의 임무는 양쪽 팀 전원의 데이터를 추출하는 것입니다.\n\n"

    "[1단계 — 게임 모드 판별]\n"
    "사진 상단의 큰 텍스트를 보고 모드를 판별하세요.\n"
    "- 'HARDPOINT'가 보이면 → 모드는 \"HP\"\n"
    "- 'SEARCH AND DESTROY' 또는 'SEARCH & DESTROY'가 보이면 → 모드는 \"SND\"\n"
    "열 제목으로도 보조 판단: ADR, FIRST KILL(S), LONE WOLF WIN 열이 있으면 SND, "
    "Total Damage, Capture Kill 열이 있거나 TIME 열이 있으면 HP.\n\n"

    "[2단계 — 점수 / 맵 추출]\n"
    "사진 상단의 결과 텍스트에서 추출하세요:\n"
    "- team_left_score: 좌측 팀 점수 (정수)\n"
    "- team_right_score: 우측 팀 점수 (정수)\n"
    "- map: 모드 텍스트 옆의 맵 이름 (예: 'HARDPOINT COMBINE' → 'Combine'). "
    "Title Case로 정규화. 안 보이면 null.\n\n"

    "[3단계 — 양쪽 팀 선수 전원 스탯 추출 ★가장 중요]\n"
    "좌측 팀 선수 5명을 team_left 배열에, 우측 팀 선수 5명을 team_right 배열에 "
    "각각 추출하세요. 양쪽 모두 빠짐없이 전부 추출해야 합니다.\n"
    "- 이름은 화면에 보이는 대로 정확히 읽으세요 (클랜태그, 특수문자 포함 그대로).\n"
    "- 읽을 수 없는 글자도 보이는 그대로 적거나 \"Unknown1\", \"Unknown2\" 형식으로 채우세요.\n"
    "- 용병/게스트 닉네임도 그대로 출력하세요.\n\n"

    "■ HP 모드 선수 필드: name, k, d, kd_ratio, time, score, impact, total_damage, capture_kill\n"
    "  - kd_ratio = k/d (소수점 둘째 자리), d=0이면 k값 그대로\n"
    "  - time = '분:초'를 순수 초(Seconds)로 변환\n"
    "■ SND 모드 선수 필드: name, k, d, a, kd_ratio, score, impact, adr, first_kill, lone_wolf_win\n"
    "  - K/D/A가 '17/12/1'이면 k=17, d=12, a=1\n"
    "\n"
    "(1번/2번 사진의 순서가 반대여도 알아서 적용하세요. 1번 사진이 기본 탭 "
    "[SCORE, K/D/A, TIME, IMPACT], 2번이 디테일 탭 [Total Damage, Capture Kill] 등)\n\n"

    "[출력 형식 — 순수 JSON Object만, 마크다운 없이]\n"
    "HP 예시:\n"
    "{\n"
    "\"mode\": \"HP\",\n"
    "\"map\": \"Combine\",\n"
    "\"team_left_score\": 250,\n"
    "\"team_right_score\": 198,\n"
    "\"team_left\": [{\"name\": \"이름\", \"k\": 0, \"d\": 0, \"kd_ratio\": 0.0, \"time\": 0, \"score\": 0, \"impact\": 0, \"total_damage\": 0, \"capture_kill\": 0}],\n"
    "\"team_right\": [{\"name\": \"이름\", \"k\": 0, \"d\": 0, \"kd_ratio\": 0.0, \"time\": 0, \"score\": 0, \"impact\": 0, \"total_damage\": 0, \"capture_kill\": 0}]\n"
    "}\n\n"
    "SND 예시:\n"
    "{\n"
    "\"mode\": \"SND\",\n"
    "\"map\": \"Coastal\",\n"
    "\"team_left_score\": 4,\n"
    "\"team_right_score\": 6,\n"
    "\"team_left\": [{\"name\": \"이름\", \"k\": 0, \"d\": 0, \"a\": 0, \"kd_ratio\": 0.0, \"score\": 0, \"impact\": 0, \"adr\": 0, \"first_kill\": 0, \"lone_wolf_win\": 0}],\n"
    "\"team_right\": [{\"name\": \"이름\", \"k\": 0, \"d\": 0, \"a\": 0, \"kd_ratio\": 0.0, \"score\": 0, \"impact\": 0, \"adr\": 0, \"first_kill\": 0, \"lone_wolf_win\": 0}]\n"
    "}"
)
