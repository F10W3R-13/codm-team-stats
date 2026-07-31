"""GPT 비전 프롬프트 — 토너넌트용 (양쪽 10명 전부 파싱).

부모 prompt.py와의 차이:
- 부모: our_team_side로 우리 팀 한쪽만 추출 (적 팀 무시)
- 토너넌트: team_left/team_right 양쪽 10명 전부 추출
- 제거: 우리 팀 식별 단계, "적 팀 스탯 넣지 마세요"
- 추가: team_left_score/team_right_score (양쪽 점수)
- 유지: 모드 판별, 맵 추출, HP/SND 필드, 2장(기본/디테일 탭) 처리
"""

PROMPT = (
    "이제부터 차례대로 제공될 2장의 사진은 동일한 CODM 모바일 이스포츠 매치의 "
    "전체 결과 화면입니다. 각 사진에는 좌측 팀(5명)과 우측 팀(5명) 양쪽의 선수 "
    "데이터가 함께 표시되어 있습니다. 양쪽 합쳐 총 10명의 선수가 있습니다.\n\n"

    "★ 핵심 규칙: team_left 배열에 정확히 5명, team_right 배열에 정확히 5명을 "
    "모두 빠짐없이 추출해야 합니다. 한 명도 누락되면 안 됩니다. "
    "어느 한쪽 팀이 통째로 빠지거나 4명만 나오면 잘못된 것입니다. ★\n\n"

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

    "[3단계 — 두 사진의 선수 매칭 ★매우 중요]\n"
    "두 사진은 같은 10명을 다른 열(기본 탭 / 디테일 탭)로 보여줍니다.\n"
    "같은 선수는 두 사진에서 같은 위치(같은 줄)에 나타납니다. 이름을 기준으로 "
    "두 사진의 데이터를 합쳐 한 선수당 하나의 객체로 만드세요.\n"
    "- 1번 사진(기본 탭): SCORE, K/D/A 또는 K/D, TIME, IMPACT 열\n"
    "- 2번 사진(디테일 탭): Total Damage, Capture Kill(HP) 또는 ADR, FIRST KILL, LONE WOLF WIN(SND) 열\n"
    "- 사진 순서가 반대일 수도 있습니다. 열 제목을 보고 어느 탭인지 판단하세요.\n\n"

    "[4단계 — 양쪽 팀 선수 전원 스탯 추출]\n"
    "좌측 팀 선수 5명을 team_left 배열에, 우측 팀 선수 5명을 team_right 배열에 "
    "각각 추출하세요.\n"
    "- 반드시 양쪽 모두 정확히 5명씩, 총 10명을 출력해야 합니다.\n"
    "- 5명이 보이지 않으면 사진을 더 꼼꼼히 살펴보세요. CODM 결과 화면은 항상 "
    "양쪽 각각 5명입니다.\n"
    "- 이름은 화면에 보이는 대로 정확히 읽으세요 (클랜태그, 특수문자, 숫자 포함 그대로). "
    "예: 'Fz.Karpe', '-MaDara-', 'Hashirama6974', 'Guri狸'.\n"
    "- 글자가 약간 잘리거나 변형되어도 최선을 다해 읽으세요. 확신이 없어도 추측값을 넣고, "
    "완전히 안 보이는 경우에만 \"Unknown1\", \"Unknown2\" 형식으로 채우세요.\n\n"

    "■ HP 모드 선수 필드: name, k, d, kd_ratio, time, score, impact, total_damage, capture_kill\n"
    "  - kd_ratio = k/d (소수점 둘째 자리), d=0이면 k값 그대로\n"
    "  - time = '분:초'를 순수 초(Seconds)로 변환 (예: '2:30' → 150)\n"
    "  - score, impact, total_damage, capture_kill, k, d, time은 모두 정수/숫자\n"
    "■ SND 모드 선수 필드: name, k, d, a, kd_ratio, score, impact, adr, first_kill, lone_wolf_win\n"
    "  - K/D/A가 '17/12/1'이면 k=17, d=12, a=1\n"
    "  - adr(average damage per round), first_kill, lone_wolf_win은 정수\n"
    "\n"
    "■ 각 선수의 모든 필드를 빠뜨리지 말고 채우세요. 어느 한 사진에서만 보이는 "
    "필드도 포함해야 합니다. 기본 탭 필드는 1번 사진에서, 디테일 탭 필드는 "
    "2번 사진에서 가져오세요.\n\n"

    "[최종 검증 — 출력하기 전에 반드시 확인]\n"
    "1. team_left 배열에 정확히 5명이 있는가?\n"
    "2. team_right 배열에 정확히 5명이 있는가?\n"
    "3. 각 선수의 모든 필드가 채워져 있는가? (null이나 누락된 필드가 없는가?)\n"
    "4. 두 사진의 같은 선수가 중복되지 않았는가?\n"
    "위 검증을 통과한 경우에만 출력하세요.\n\n"

    "[출력 형식 — 순수 JSON Object만, 마크다운 없이]\n"
    "HP 예시 (5명만 표시하지만 실제로는 양쪽 각각 5명 전부):\n"
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
