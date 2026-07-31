"""GPT 비전 프롬프트 — 토너먼트용 (양쪽 10명 전부 파싱, 이름 기반 매칭).

부모 prompt.py와의 차이:
- 부모: our_team_side로 우리 팀 한쪽만 추출 (적 팀 무시)
- 토너먼트: team_left/team_right 양쪽 10명 전부 추출
- 제거: 우리 팀 식별 단계, "적 팀 스탯 넣지 마세요"
- 추가: team_left_score/team_right_score (양쪽 점수)
- 유지: 모드 판별, 맵 추출, HP/SND 필드, 2장(기본/디테일 탭) 처리
- ★ 핵심: 두 사진의 팀 좌/우는 서로 다를 수 있음 — 이름으로 매칭.
"""

PROMPT = (
    "이제부터 차례대로 제공될 2장의 사진은 동일한 CODM 모바일 이스포츠 매치의 "
    "전체 결과 화면입니다. 각 사진에는 두 팀(각 5명, 총 10명)의 선수 데이터가 "
    "좌/우로 나뉘어 표시되어 있습니다.\n\n"

    "★ 매우 중요 — 두 사진의 좌/우 팀 배치는 서로 다를 수 있습니다 ★\n"
    "예: 1번 사진(기본 탭)에서 좌측이 A팀이더라도, 2번 사진(디테일 탭)에서는\n"
    "우측이 A팀일 수 있습니다. 따라서 '좌측=team_left'라고 위치를 고정하지 말고,\n"
    "이름을 기준으로 같은 선수를 두 사진에서 찾아 스탯을 합쳐야 합니다.\n\n"

    "[1단계 — 게임 모드 판별]\n"
    "사진 상단의 큰 텍스트를 보고 모드를 판별하세요.\n"
    "- 'HARDPOINT'가 보이면 → 모드는 \"HP\"\n"
    "- 'SEARCH AND DESTROY' 또는 'SEARCH & DESTROY'가 보이면 → 모드는 \"SND\"\n"
    "열 제목으로도 보조 판단: ADR, FIRST KILL(S), LONE WOLF WIN 열이 있으면 SND, "
    "Total Damage, Capture Kill 열이 있거나 TIME 열이 있으면 HP.\n\n"

    "[2단계 — 점수 / 맵 추출]\n"
    "사진 상단의 결과 텍스트에서 추출하세요:\n"
    "- team_left_score: 1번 사진(기본 탭) 좌측 팀 점수 (정수)\n"
    "- team_right_score: 1번 사진(기본 탭) 우측 팀 점수 (정수)\n"
    "- map: 모드 텍스트 옆의 맵 이름 (예: 'HARDPOINT COMBINE' → 'Combine'). "
    "Title Case로 정규화. 안 보이면 null.\n\n"

    "[3단계 — 두 팀 식별 (1번 사진 기준)]\n"
    "1번 사진(기본 탭)에서 두 팀을 식별합니다.\n"
    "- team_left: 1번 사진의 좌측에 나열된 5명의 선수 (기본 스탯 포함)\n"
    "- team_right: 1번 사진의 우측에 나열된 5명의 선수 (기본 스탯 포함)\n"
    "- 1번 사진의 열: SCORE, K/D/A (또는 K/D), TIME, IMPACT (HP) 또는 SCORE, K/D/A, ADR (SND)\n\n"

    "[4단계 — 디테일 스탯 병합 (2번 사진, 이름으로 매칭) ★가장 중요]\n"
    "2번 사진(디테일 탭)에서 각 선수의 디테일 스탯을 읽어, 1번 사진에서 식별한\n"
    "같은 이름의 선수에게 병합합니다.\n"
    "- 2번 사진의 열: Total Damage, Capture Kill (HP) 또는 ADR, FIRST KILL, LONE WOLF WIN (SND)\n"
    "- ★ 2번 사진에서 선수가 어느 쪽(좌/우)에 있든, '이름'으로 같은 선수를 찾아 스탯을 합칩니다.\n"
    "  예: 1번 사진 좌측의 'Fz.Karpe'가 2번 사진에서는 우측에 있을 수 있습니다.\n"
    "  이때 위치가 아니라 'Fz.Karpe'라는 이름으로 같은 선수임을 식별하세요.\n"
    "- 두 사진의 이름이 약간 다르게 표기될 수 있습니다 (예: 'Fz.Karpe' vs 'Karpe').\n"
    "  비슷한 이름이면 같은 선수로 간주하고 합치세요.\n\n"

    "[5단계 — 양쪽 팀 선수 전원 스탯 완성]\n"
    "team_left와 team_right 각각 정확히 5명, 총 10명을 완성하세요.\n"
    "- 각 선수는 기본 스탯(1번 사진) + 디테일 스탯(2번 사진)이 모두 합쳐진 상태여야 합니다.\n"
    "- 5명이 보이지 않으면 사진을 더 꼼꼼히 살펴보세요. CODM 결과 화면은 항상 한 팀 5명입니다.\n"
    "- 이름은 화면에 보이는 대로 정확히 읽으세요 (클랜태그, 특수문자, 숫자 포함 그대로). "
    "예: 'Fz.Karpe', '-MaDara-', 'Hashirama6974', 'Guri狸', 'HiruzEn'.\n"
    "- 확신이 없어도 추측값을 넣고, 완전히 안 보이는 경우에만 \"Unknown1\" 형식으로 채우세요.\n\n"

    "■ HP 모드 선수 필드: name, k, d, a, kd_ratio, time, score, impact, total_damage, capture_kill\n"
    "  - kd_ratio = k/d (소수점 둘째 자리), d=0이면 k값 그대로\n"
    "  - time = '분:초'를 순수 초(Seconds)로 변환 (예: '2:30' → 150)\n"
    "  - k, d, a, time, score, impact, total_damage, capture_kill은 모두 정수/숫자\n"
    "  - total_damage와 capture_kill은 반드시 2번 사진(디테일 탭)에서 읽어 채우세요.\n"
    "■ SND 모드 선수 필드: name, k, d, a, kd_ratio, score, impact, adr, first_kill, lone_wolf_win\n"
    "  - K/D/A가 '17/12/1'이면 k=17, d=12, a=1\n"
    "\n"
    "■ 각 선수의 모든 필드를 빠뜨리지 말고 채우세요. 어느 한 사진에서만 보이는 "
    "필드도 포함해야 합니다.\n\n"

    "[최종 검증 — 출력하기 전에 반드시 확인]\n"
    "1. team_left 배열에 정확히 5명이 있는가?\n"
    "2. team_right 배열에 정확히 5명이 있는가?\n"
    "3. 각 선수의 total_damage/capture_kill(HP) 또는 adr/first_kill/lone_wolf_win(SND)이\n"
    "   채워져 있는가? (2번 사진에서 읽었는가?)\n"
    "4. 1번 사진 좌측 5명이 team_left, 우측 5명이 team_right에 들어갔는가?\n"
    "위 검증을 통과한 경우에만 출력하세요.\n\n"

    "[출력 형식 — 순수 JSON Object만, 마크다운 없이]\n"
    "HP 예시:\n"
    "{\n"
    "\"mode\": \"HP\",\n"
    "\"map\": \"Combine\",\n"
    "\"team_left_score\": 250,\n"
    "\"team_right_score\": 198,\n"
    "\"team_left\": [{\"name\": \"이름\", \"k\": 0, \"d\": 0, \"a\": 0, \"kd_ratio\": 0.0, \"time\": 0, \"score\": 0, \"impact\": 0, \"total_damage\": 0, \"capture_kill\": 0}],\n"
    "\"team_right\": [{\"name\": \"이름\", \"k\": 0, \"d\": 0, \"a\": 0, \"kd_ratio\": 0.0, \"time\": 0, \"score\": 0, \"impact\": 0, \"total_damage\": 0, \"capture_kill\": 0}]\n"
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
