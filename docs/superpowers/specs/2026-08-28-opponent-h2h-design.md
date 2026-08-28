# 상대팀 전적 & Head-to-Head — 설계

날짜: 2026-08-28
상태: 초안 (사용자 리뷰 대기)

## 1. 목표

- **워크플로우 불변**: 지금처럼 디스코드에 사진 2장만 올리면 끝. 메시지에 뭘 더 적거나 사전 작업 필요 없음.
- 상대팀 식별·상대 선수 스탯 수집을 자동화하고, 이 데이터로 **팀 상대전적**(vs 팀 N승 M패)과 **선수 H2H**(매치업별 스탯 대비)를 조회한다.
- **기존 페이지·지표 0줄 수정**: 우리팀 로그로서의 현재 시스템은 완전히 그대로.

### 비목표 (초기 버전에서 제외)

- 기존 370매치의 상대 선수 스탯 소급 복구 (원본 이미지 없음 — 불가)
- 상대 선수 개인 상세 페이지 (팀 상세 내 표로 충분)
- 토너먼트 모드(tournament/) 확장

## 2. 핵심 원칙

1. **읽기는 GPT, 분류는 DB.** GPT는 적팀 이름을 raw로만 출력(변환 금지). 이름→선수 매칭·팀 식별은 DB 계층의 결정적 로직으로. 프롬프트에 상대 로스터를 주입하지 않는다(토큰 낭비·오판·블랙박스 회피).
2. **우리팀 식별과 동일한 원리로 상대팀 식별.** 지금 GPT가 "로스터와 유사한 선수가 많은 쪽 = 우리팀"으로 판별하듯, 상대팀은 DB가 "등록 로스터와 일치하는 선수가 많은 팀"으로 다수결 판정.
3. **사전(로스터 사전)은 매치 데이터에서 자라난다.** 선등록(공식 로스터) = 초기 사전, 매치 축적 = 갱신되는 사전. 매칭 후보군은 둘의 합집합.
4. **수동 병합이 최종 폴백이며 1회면 영구 학습.** 완전히 다른 이름의 동일인물은 인간만 풀 수 있다. admin에서 병합하면 alias 사전에 등록돼 다시 안 나온다.

## 3. 데이터 모델

기존 테이블과 **완전 분리** (같은 테이블에 넣으면 모든 기존 쿼리가 오염됨 — 분리가 "기존 페이지 0줄 수정"을 가능하게 하는 핵심).

```sql
CREATE TABLE IF NOT EXISTS opponent_teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,          -- 정규화된 표준 팀명 (드롭다운으로만 입력 → 오타 분열 원천 차단)
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opponent_players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,          -- 대표 표기 (첫 등록 or 병합 시 코치 선택)
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opponent_aliases (  -- 우리팀 aliases와 동일 패턴
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ign                 TEXT NOT NULL UNIQUE,  -- OCR raw 표기
    opponent_player_id  INTEGER NOT NULL REFERENCES opponent_players(id),
    source              TEXT NOT NULL DEFAULT 'Auto',  -- Auto(퍼지 자동) | Merge(수동 병합)
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opponent_team_rosters (
    team_id     INTEGER NOT NULL REFERENCES opponent_teams(id),
    player_id   INTEGER NOT NULL REFERENCES opponent_players(id),
    source      TEXT NOT NULL,                 -- 'registered'(선등록) | 'match'(매치 축적)
    UNIQUE(team_id, player_id)
);

-- matches에 컬럼 추가 (기존 ALTER 마이그레이션 패턴 재사용):
--   opponent_team_id INTEGER REFERENCES opponent_teams(id)   NULL 허용(미확정)

-- player_stats_hp/snd 미러 (칼럼 동일, FK만 opponent_players):
CREATE TABLE IF NOT EXISTS opponent_stats_hp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    player_id INTEGER NOT NULL REFERENCES opponent_players(id),
    ign_raw TEXT, kills INTEGER, deaths INTEGER, kd_ratio REAL,
    obj_time INTEGER, score INTEGER, impact REAL, total_damage INTEGER, capture_kill INTEGER,
    UNIQUE(match_id, player_id)
);
-- opponent_stats_snd 동일 구조 (assists, adr, first_kill, lone_wolf_win 포함)
```

- **용병 모델**: 선수 신원은 전역(opponent_players), "어느 팀 소속이었나"는 매치(opponent_team_id)와 로스터 테이블이 담는다. 한 선수가 팀을 옮겨도 H2H 신원 유지.
- ZCS/RDS는 공식이 팀 무관하므로 상대 선수 스탯에도 동일 공식 적용해 조회 시 계산 (지표 저장 컬럼은 우리팀 스키마와 동일하게 유지).

## 4. 추출 — prompt.py (출처 고정 파일, 최소 변경)

- [2단계] our_team_side 판별 로직은 그대로 (이미 양쪽을 다 읽고 있음).
- [4단계]에 추가: "확정한 우리 팀의 **반대쪽** 선수들도 동일한 필드로 `enemy_players` 배열에 **raw 그대로**(이름 변환 금지) 출력".
- JSON 스키마에 `enemy_players` 키 추가. 기존 키·지시문은 건드리지 않는다.
- **회귀 리스크 관리**: 변경 후 기존 샘플 스크린샷으로 우리팀 추출 결과가 동일한지 반드시 비교 검증.

## 5. 저장 파이프라인 (stats_repo → db)

### 5.1 상대 선수 resolve (이름 1개당)

1. **정확 매칭**: 정규화(NFKC + lowercase + 특수문자 제거) 후 opponent_aliases/players 조회.
2. **팀 풀 퍼지**: 매치에 팀이 확정된 **이후**(자동 태그 직후 or admin 수동 지정 후) 미해결 이름을 재매칭할 때 사용 — 그 팀의 로스터 풀 내에서 유사도 ≥ 기본 임계값.
3. **전역 퍼지**: 용병 폴백. 전역 풀에서 더 높은 임계값으로. (소속 없는 신원도 잡힘)
4. **신규 엔트리**: 위 모두 실패 → opponent_players 생성. admin 병합 대기.
- 퍼지 구현: 표준 라이브러리(difflib 등)만 사용, 신규 의존성 없음. 임계값은 상수로 두고 조정.

### 5.2 상대팀 자동 식별 (매치당 1회)

1. enemy 이름들의 resolve 결과(정확+퍼지 신뢰 구간)로 소속투표.
2. **과반 판정**(예: 일치 인원 비율 ≥ 0.6, 5명 중 3명) → 단일 팀이면 `matches.opponent_team_id` 자동 태그.
3. 미달·모호 → NULL 저장 (admin 큐로).
4. 태그 성공 시 그 매치에 등장한 상대 선수들을 opponent_team_rosters에 upsert (source='match') — 사전이 자라나는 지점.

### 5.3 부분 실패 격리

- GPT가 `enemy_players`를 누락/빈 배열로 주면 → **우리팀 저장은 정상, 상대 쪽만 스킵**. 상대 수집 실패가 기존 파이프라인을 깨지 않게 한다.

## 6. Admin UI (기존 병합 UX 패턴 재사용)

1. **상대팀 관리 탭**(신규): 팀 등록/삭제 + 로스터 붙여넣기(줄당 닉네임 1개) → opponent_players 자동 생성 + roster 등록(source='registered').
2. **매치 관리 — 상대팀 미확정 큐**: opponent_team_id가 NULL인 매치 목록 → 드롭다운(등록된 팀만)으로 팀 지정. 저장 시 5.1~5.2 재실행(팀 풀로 후보 좁아져 재매칭 정확도 상승).
3. **상대 선수 미해결 큐**: raw 이름 옆 드롭다운 → 기존 상대 선수에 병합(merge) 또는 새 선수로 확정. 병합 시 raw 이름을 opponent_aliases에 영구 등록. **사용자 요구 UX: 팀 지정 → 선수 지정 순서.**

## 7. 조회 — /versus (신규 라우트)

- **팀 목록**: 팀별 상대전적 카드 (W/L, 매치 수, 평균 스코어差, 최근 폼). 미확정 매치는 제외.
- **팀 상세** (`/versus/{team_id}`): 매치 히스토리(승패·스코어·맵) + **H2H 매트릭스** — 행=우리 선수, 열=상대 선수, 셀=공동 출전 매치 수 / K-D diff / ZCS(HP)·RDS(SND) diff. ZCS/RDS는 상대 스탯에 동일 공식 적용해 조회 시 계산.
- 기존 페이지(nav·리더보드·선수 상세 등)는 건드리지 않음. i18n 3개국어 키 추가 (`test_i18n.py` 동일성 유지).

## 8. 오류·예외 정리

| 케이스 | 동작 |
|---|---|
| 미등록 팀 첫 상대 | 팀 식별 실패 → NULL + admin 큐 → 팀 등록 1회로 해소 |
| 용병 과반 라인업 | 다수결 미달 → NULL + admin 큐 |
| OCR 표기 불일치 (오타·유니코드) | 퍼지 흡수, 놓치면 병합 1회 → 영구 학습 |
| 완전히 다른 이름의 동일인물 | AI 해결 불가(시그널 없음) → 수동 병합 전제 |
| GPT enemy_players 누락 | 우리팀 저장 정상, 상대만 스킵 |
| 공식 로스터와 실제 라인업 괴리 | 후보·용병도 신규 엔트리로 자연 축적, 사전은 stale해도 매치 축적이 보완 |
| 기존 370매치 | 팀 태그만 수동 소급 가능(승패 있는 매치), 상대 선수 스탯은 소급 불가 |

## 9. 테스트

- **프롬프트 회귀**: 기존 샘플 스크린샷으로 우리팀 추출 결과 동일성 비교 (enemy 추가로 인한 품질 저하 검증).
- **매칭 단위 테스트**: 정규화/정확 매칭/퍼지 임계값/팀 다수결/용병 전역 폴백/병합 후 학습.
- **기존 스위트**: 라우트 스모크, SQL 호환(`_adapt_sql` — 새 테이블 쿼리도 SQLite/Postgres 양쪽), i18n 키 동일성.

## 10. 구현 순서 (제안)

1. DB 스키마 + resolve/퍼지/투표 로직 (+단위 테스트) — 코어, 결정적
2. prompt.py `enemy_players` + stats_repo 저장 경로 (+회귀 검증)
3. admin 상대팀 관리 + 미확정 큐 (팀/선수)
4. `/versus` 팀 상대전적 + H2H 매트릭스
5. (후순위) 상대 로스터 사전 고도화 — 매치 축적 로스터의 프롬프트 재주입은 하지 않음(원칙 1)

## 11. 난이도 요약

전체 ★★☆ (2~4일 상당). 프롬프트 수정이 유일한 기존 시스템 리스크 지점이며 회귀 검증으로 통제. 신규 로직(퍼지·투표)은 순수 함수라 테스트 용이.
