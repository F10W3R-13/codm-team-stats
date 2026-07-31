# 토너먼트 모드 설계 — 1회용 대회 데이터 수집/분석 로컬 웹앱

**날짜**: 2026-08-01
**목적**: 주최한 CODM 대회(5팀 풀리그 + 결승) 참가자 지표 수집/분석을 위한 **1회용 독립 로컬 웹앱**. 기존 우리 팀 시스템은 0줄 수정, 완전 분리.

---

## 1. 배경 & 요구사항

### 왜 새로 짜는가
기존 시스템은 "단일 팀 내부 스탯 도구"다. `matches` 테이블에 team/tournament/opponent 분류 컬럼이 없고, 모든 집계(leaderboard, ZCS/RDS, 평균)가 "DB 전체 선수 풀" 기준이다. `ROSTER`도 6명 하드코딩. 대회 참가자 데이터를 같은 DB에 넣으면 리더보드/평균이 즉시 오염된다.

### 확정 요구사항 (브레인스토밍 결과)
- **형식**: 5팀 풀리그(라운드로빈, 10경기) + 결승 1경기 = **총 11경기**. 각 매치는 5v5, 한 스크린샷에 양 팀 10명 표시.
- **수집 시점**: 사후 일괄 임포트 (대회 종료 후 스크린샷 모아 한 번에 처리).
- **입력 소스**: 스크린샷 2장(기본 탭 + 디테일 탭) + GPT 비전. 우리 시스템과 동일한 2장 업로드 구조.
- **격리**: 우리 팀 시스템과 **완전 분리** (코드 0줄 수정, DB 별도 파일).
- **배포**: 1회용이므로 **로컬 웹앱만** (Railway 배포 불필요).
- **자동화 목표**: 스크린샷 2장 업로드 → 매치 1개가 메타·10명 스탯·승패·팀 식별 전부 자동 등록 ("손도 안 대고 다 되는").
- **시드**: 팀명·팀 명단은 사용자가 사전 확보해 제공 (DB 시드용).
- **출력물**: 선수 순위표, 팀 순위표, 최종 리포트, 개인상(MVP 등).
- **MVP 산출**: ZCS(HP) 평균 + RDS(SND) 평균 합산 1위 (모드 불균형 보정).

---

## 2. 아키텍처 — 독립 폴더 분리

### 폴더 구조
```
Team management app/
├── (기존 우리 팀 시스템 — 0줄 수정)
│   ├── web_api.py, bot.py, db.py, queries.py, ...
│   ├── prompt.py, metrics.py          ← 경로로 참조만 (import)
│   └── metrics.py(compute_zcs/compute_rds) ← 공식 출처 고정, import 재사용
│
└── tournament/                         ← 새 폴더 (1회용)
    ├── app.py                          ← FastAPI 앱 (uvicorn app:app --port 8001)
    ├── db.py                           ← 토너먼트 전용 스키마 + SQLite
    ├── vision.py                       ← GPT 비전 호출 래퍼 (양쪽 10명 파싱)
    ├── prompt_tournament.py            ← prompt.py 기반 양쪽 파싱 사본 (b안)
    ├── matching.py                     ← IGN → DB 선수 역추적 (퍼지 매칭)
    ├── standings.py                    ← 풀리그/결승 팀 순위 계산
    ├── awards.py                       ← MVP/개인상 산출
    ├── seed.py                         ← 팀·명단 시드 CLI
    ├── import_screenshots.py           ← (선택) 일괄 임포트 CLI
    ├── tournament.db                   ← 별도 SQLite (.gitignore)
    └── templates/
        ├── base.html
        ├── import.html                 ← 스크린샷 업로드 + 파싱 미리보기
        ├── standings.html              ← 팀 순위표
        ├── players.html                ← 선수 순위표
        ├── match.html                  ← 매치 상세 (양 팀 10명)
        └── report.html                 ← 최종 리포트 (시상용)
```

### 재사용 전략
- **`metrics.py`**: `from metrics import compute_zcs, compute_rds`로 **직접 import**. 공식은 출처 고정(AGENTS.md §핵심지표)이므로 복붙보다 import가 안전. 부모 디렉토리를 sys.path에 추가해 접근.
- **`prompt.py`**: 양쪽 10명 파싱으로 수정 필요 → `prompt_tournament.py` 사본 생성 (b안). 기존 `prompt.py`는 "우리 팀 한쪽만" 추출(`our_team_side`)이라 토너먼트용(양쪽 전부)과 호환 안 됨.
- **OCR alias 매칭**: `.agents/skills/ocr-alias-matching/SKILL.md` 규칙을 `matching.py`에서 동일 로직으로 구현 (별명·대소문자·퍼지 매칭).

### 실행
```bash
cd tournament
uvicorn app:app --port 8001 --reload
```
포트 8001 (기존 웹 8000과 충돌 회피), 별도 프로세스, 별도 DB 파일.

---

## 3. 데이터 모델 — 자동화 중심

`tournament/tournament.db` (SQLite 전용, Postgres 불필요).

```sql
-- 팀 (5개, 사용자 시드)
CREATE TABLE teams (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    seed INTEGER              -- 시드/표시 순서 (선택)
);

-- 선수 (한 선수는 한 팀 소속)
CREATE TABLE players (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,       -- 표준명 (시드)
    team_id INTEGER NOT NULL REFERENCES teams(id),
    UNIQUE(name, team_id)
);

-- 별명 (OCR 인식명 → 표준명 매핑, 자동 학습)
CREATE TABLE aliases (
    id INTEGER PRIMARY KEY,
    ign TEXT UNIQUE NOT NULL, -- 스크린샷에서 읽은 이름
    player_id INTEGER NOT NULL REFERENCES players(id)
);

-- 매치 (11경기)
CREATE TABLE matches (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,            -- 'HP' | 'SND'
    map_name TEXT,
    match_date TEXT,
    stage TEXT NOT NULL DEFAULT 'round_robin',  -- 'round_robin' | 'final' ★
    team_a_id INTEGER NOT NULL REFERENCES teams(id),
    team_b_id INTEGER NOT NULL REFERENCES teams(id),
    team_a_score INTEGER,          -- 파싱된 점수 (승패 산출용)
    team_b_score INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 선수별 HP 스탯 (매치당 10행, 양 팀 전부)
CREATE TABLE player_stats_hp (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),   -- 어느 팀 소속
    kills INTEGER, deaths INTEGER, assists INTEGER,
    damage INTEGER, obj_time REAL, capture_kill INTEGER,
    UNIQUE(match_id, player_id)
);

-- 선수별 SND 스탯 (매치당 10행)
CREATE TABLE player_stats_snd (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    kills INTEGER, deaths INTEGER, assists INTEGER,
    damage INTEGER, adr REAL,
    first_kill INTEGER, lone_wolf_win INTEGER,
    UNIQUE(match_id, player_id)
);
```

### 기존 시스템과의 핵심 차이
| | 우리 팀 시스템 | 토너먼트 |
|---|---|---|
| 팀 개념 | 없음 (단일 팀 가정) | **teams 테이블, 5팀** |
| 선수 소속 | 없음 | **players.team_id (FK)** |
| 매치 분류 | 없음 | **matches.stage** (라운드로빈/결승) |
| 스탯 행수/매치 | 5 (한 팀만) | **10 (양 팀 전부)** |
| 스탯 team_id | 없음 | **player_stats.team_id** (집계 시 팀 필터) |
| 승패 | matches.result (WIN/LOSS) | **team_a/b_score** (양 팀 점수, 승패는 산출) |

---

## 4. 자동화 파이프라인 — 스크린샷 2장 → 매치 자동 등록

**핵심 원칙: 스크린샷 2장 업로드 → 매치 1개 완전 자동 등록.**

### 5단계 흐름
```
스크린샷 2장 업로드 (stats 탭 + detail 탭)
        │
        ▼
① GPT 비전 파싱 (prompt_tournament.py + vision.py)
   → JSON: {mode, map, team_left_score, team_right_score, winner_side,
            team_left:  [{ign, K, D, A, dmg, ...}, ×5],
            team_right: [{ign, K, D, A, dmg, ...}, ×5]}
   (양쪽 10명 전부 추출 — 우리 팀 식별 단계 제거)
        │
        ▼
② 선수 IGN → DB 역추적 (matching.py, 퍼지 매칭)
   각 ign을 aliases/players에서 매칭 → player_id + team_id 획득
   team_left 5명이 같은 team_id → A팀 / team_right 5명 → B팀
   매칭 실패 시 미리보기에서 1클릭 매핑 → alias 자동 학습(다음부턴 자동)
        │
        ▼
③ 매치 자동 등록 (db.py)
   matches 1행 (mode/map/scores/team_a/team_b) + player_stats 10행 INSERT
   승패는 team_a_score vs team_b_score로 산출
        │
        ▼
④ stage 자동 판별 ★ (round_robin vs final)
   풀리그 = 각 팀쌍이 정확히 1번 만남 (C(5,2)=10경기)
   같은 팀쌍이 2번째로 만나는 매치 = 자동으로 'final'
   → 11번째 매치(1위 vs 2위)가 이 조건에 해당
        │
        ▼
⑤ 순위/개인상 자동 산출 (standings.py, awards.py)
   팀 순위(승점) · 선수 순위(ZCS/RDS) · MVP — 전부 DB에서 자동 계산
```

### prompt_tournament.py의 기존 대비 변경점
기존 `prompt.py` 4단계 중 **[2단계 우리 팀 식별]**을 제거하고 양쪽 전부 수집:
- **제거**: `our_team_side`, 로스터 매칭으로 한쪽 식별, "적 팀 스탯 넣지 마세요"
- **변경**: `team_left`/`team_right` 배열로 양쪽 10명 전부 추출
- **추가**: `team_left_score`/`team_right_score` (양쪽 점수, 우리 팀 기준 아님)
- **유지**: 모드 판별, 맵 추출, HP/SND 필드 구조, 2장 처리(기본/디테일 탭)

### stage 자동 판별의 정당성
풀리그(라운드로빈)에서는 모든 팀쌍이 정확히 1번 만난다. 결승은 1위 vs 2위 재대결이므로 **같은 팀쌍이 2번째로 만나는 매치 = 결승**. 5팀 풀리그(10경기) 다음 11번째 매치가 항상 이 조건. 안전망: 매치 상세에서 stage 수동 토글(드문 경우용).

---

## 5. 지표 & 순위 계산

### 개인 지표 (metrics.py 재사용)
- **HP**: `compute_zcs(kills, deaths, obj_time, capture_kill)` — ZCS 제1 지표
- **SND**: `compute_rds(kills, deaths, assists, first_kill, lone_wolf_win, adr)` — RDS 제1 지표
- 부모 `metrics.py`에서 직접 import. 공식 출처 고정(AGENTS.md).

### 팀 순위 (standings.py)
- **승점**: 승=2, 무=1(동점 가능), 패=0. 풀리그 매치(`stage='round_robin'`)만 집계.
- **동점 시 타이브레이크**: ① 승점 → ② 득실라운드차(team_score - opponent_score) → ③ 직접 대결 결과.
- 결승(`stage='final'`) 결과는 별도 표시: "풀리그 1위 vs 2위 → 결승 결과". 최종 우승 = 결승 승자.

### MVP & 개인상 (awards.py)
- **MVP** = (자기 HP 매치들의 ZCS 평균) + (자기 SND 매치들의 RDS 평균) 합산 1위. 평균이라 HP 매치 많다고 유리하지 않음(모드 불균형 보정).
- **최다 킬**, **최고 K/D**, **광탈왕(최다 데스)**, **딜러(최다 딜)** — 단순 합/평균 1위.

---

## 6. 화면 구성 (로컬 웹앱, 포트 8001)

| 라우트 | 용도 |
|---|---|
| `/` (import) | **스크린샷 2장 업로드** → 파싱 미리보기(10명, 팀 배정 확인) → 저장. 매치 등록 메인 |
| `/standings` | **팀 순위표**: 5팀 승점 순(풀리그) + 결승 결과 별도 표시 |
| `/players` | **선수 순위표**: 전체 선수 K/D, ZCS(HP), RDS(SND) 정렬 |
| `/matches/{id}` | 매치 상세: 양 팀 10명 스탯 + 승패 + stage 배지 |
| `/report` | **최종 리포트**: 우승팀, 결승 요약, 팀 순위, MVP/개인상 (시상용 1페이지) |

---

## 7. 시드 절차 (대회 시작 전 1회)

사용자가 제공한 5팀명 + 각 팀 명단을 `seed.py`로 주입:
- 입력 형식: 팀명별 선수 IGN 리스트 (JSON/파이썬 dict, 또는 대화형 CLI).
- `teams` 5행 + `players` 각 팀 5~6행 + `aliases`(표준명 자동 등록) 생성.
- 이후 임포트 시 IGN 역추적의 기준이 됨.

---

## 8. 비범위 (Out of Scope)

- 실시간 입력/봇 연동 (사후 일괄이므로 불필요)
- Railway 배포 (1회용 로컬 앱)
- 우리 팀 시스템과의 데이터 비교/통합 (완전 분리)
- 코칭 브레인/AI 인사이트 연동 (대회 분석은 지표 중심)
- i18n 다국어 (코치 단일 사용자, 한국어 고정)

---

## 9. 대회 종료 후 정리

대회 끝나면 `tournament/` 폴더째 삭제 또는 보관. 기존 우리 팀 시스템은 영향 0%.
