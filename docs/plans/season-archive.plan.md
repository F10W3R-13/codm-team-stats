# Plan: 시즌 아카이빙 (S1/S2) — season-archive

- 상태: GATE 1 승인 대기
- 경계: `SEASON_CUTOFF = "2026-09-05"` (사전 점검 확정: s1 최대 id=441, s2 최소 id=442, 경기일·기록일 불일치 0건, 날짜 NULL 12건은 전부 6월 마이그레이션分 → s1)
- 진입: `ecc:orch-add-feature` (size: large, phase mask 0→1→2→4→5→6)
- 실행: `ecc:tdd-workflow` (이 파일을 plan 핸드오프로 사용)

## 확정 결정사항 (변경 금지)

1. `matches.season TEXT` — 값 `'s1'`/`'s2'`. 상수는 **db.py**에 둔다 (`CURRENT_SEASON='s2'`, `SEASON_CUTOFF='2026-09-05'`). config.py가 아니라 db.py인 이유: queries.py는 `import db`만 하고 config 임포트가 없으며, config.py는 임포트 시점 env 강제(config.py:11,14)라 db→config 간선이 생김.
2. **백필은 init_db 마이그레이션에서 멱등 수행** (별도 운영 쓰기 스크립트 없음):
   `UPDATE matches SET season = CASE WHEN match_date >= ? THEN 's2' ELSE 's1' END WHERE season IS NULL`
   — NULL 날짜는 `NULL >= ?` → UNKNOWN → ELSE 's1'`. Postgres 분기는 기존 pg_advisory_lock 블록 내(db.py:298-308), SQLite 분기는 PRAGMA+ALTER 루프(db.py:324-330). `idx_matches_season` 인덱스 추가.
3. 읽기 필터 문구 전 함수 통일: `(m.season=? OR m.season IS NULL)` / 서브쿼리형 `(season=? OR season IS NULL)`. NULL=미태그 행은 양쪽 시즌 뷰에 노출(전환기 폴백).
4. 웹: GET 라우트에 `season: str = Query(db.CURRENT_SEASON, pattern="^(s1|s2)$")` — 위반값 422. `render()` 헬퍼(web_api.py:49-53)에 season 주입. nav에 `.lang-switcher`(base.html:701-723) 패턴 복제 시즌 토글(`setSeason(s)` — URLSearchParams.set, lang 보존). i18n 3개 언어 키 추가.
5. 봇(commands_cog/report_embeds): 변경 없음 — queries 기본값(current) 상속.
6. 쓰기: `stats_repo.save_match` INSERT에 `db.CURRENT_SEASON` 고정 태깅(시그니처 변경 없음). `_find_reupload_target` 후보 쿼리에 `(season=? OR season IS NULL)` 가드.
7. **필터 예외(수정 금지)**: `match_report`, `match_raw_stats`, `notes_for_match`(점조회), `admin_match_list`·`matches_by_date`(admin 전체), `_elapsed_matches`(노트 경과 수 — 필터 시 경계 리셋).
8. `insight_cache.get/set`에 `season=None` 파라미터, 키 `(kind, target, lang, season)` 4튜플 — 기존 3-인자 호출 하위 호환. kind `match`는 id 기반 제외.
9. `import_sheets.py`: INSERT 시 날짜 분기로 명시 태깅(db.SEASON_CUTOFF 재사용).
10. 문서: AGENTS.md 시즌 정책 소절 신설 + insight_cache TTL 오류 정정(1시간 → 600초, insight_cache.py:18 실패).
11. 배포 후 검증: `scripts/season_boundary_check.py --post-deploy` 모드(season별 카운트, NULL=0 확인).

## 슬라이스 (순서 = 구현 순서, 각각 RED→GREEN)

### S1. 스키마 + 멱등 백필 + 상수 (db.py)
- 신규 DB SCHEMA에 season 컬럼, init_db 양 분기 ALTER+백필, 인덱스.
- 테스트(tests/test_season.py 신규): 직접 INSERT(경계일/전일/NULL) → init_db 재호출 → 09-05=s2, 09-04=s1, NULL=s1, 재실행 멱등.

### S2. 쓰기 태깅 + dedup 시즌 가드 (stats_repo.py)
- save_match INSERT season 추가. _find_reupload_target 가드.
- 테스트: save_match 후 season='s2'; s1 매치와 동일 스탯 재업로드 → 병합 안 함(신규 생성); test_stats_repo_dedup.py 회귀.

### S3. 읽기 계층 필터 (queries.py + analytics.py) — 최대 슬라이스
- matches 조인형 19함수: last_match_summary(215), match_by_date(280), player_kd_trend(334), match_history(484), match_history_grouped(534), team_trend(642), map_team_stats(690), map_team_stats_recent(729), team_trend_by_matches(780), map_player_stats(824), player_map_breakdown(871), map_win_loss(961), map_trend(990), missing_result_count(1112, 현시즌 결측만), win_loss_summary(1121), recent_results(1182), recent_zcs_trend(1210), versus_overview(1426), versus_team_detail(1450).
- 서브쿼리형 6함수: player_overall_stats(46), leaderboard(166), all_players_overview(354), advanced_leaderboard(412), _player_overall_zcs(933), _player_overall_rds(944) — `match_id IN (SELECT id FROM matches WHERE season=? OR season IS NULL)`.
- 시그니처 `season: str = None` → 첫 줄 `season or db.CURRENT_SEASON`. 경유(team_averages/compare_players/team_role_distribution)는 전달만.
- analytics.py: weekly_report(132), player_trend(202, 전체평균 부분 서브쿼리 주의), last_match_id(315), map_detail(331), banpick_board(377), coaching_hub(486) 파라미터 전달.
- 테스트: 독립 fixture에 s1 전용 선수("Veteran") → 기본 호출에 미포함 / season='s1' 호출에만 포함 / NULL 행 양쪽 노출. test_sql_compat.py에 서브쿼리 케이스(%s 개수=파라미터 수). test_opponent_resolve.py 회귀(NULL 폴백).

### S4. 웹 ?season= + nav 토글 + i18n (web_api.py, base.html, i18n/)
- 대상 라우트: `/`, `/players`, `/players/{name}`, `/compare`, `/leaderboard`, `/matches`, `/maps`, `/maps/{name}`, `/versus`, `/versus/{id}`, `/api/player/{name}/timeseries`, `/api/insight/player|map|briefing`. 제외: `/matches/{id}`, `/admin*`.
- render()에 season 주입. 내부 링크 season 승계(grep 검증). 무효값 422.
- 테스트: `?season=s1` s1만 노출, 422, lang 조합 200. test_smoke_routes.py에 season 변형 5개 추가. test_i18n.py.

### S5. insight_cache 키 분리 (insight_cache.py, web_api.py)
- 4튜플 키. 호출부 7곳 season 전달(web_api.py:174,288,305,330,340,353,368,395 — match 제외).
- 테스트: set(s1)/get(s1) 히트, get(s2) None, 기존 3-인자 호환. `/api/insight/player/X?season=s1|s2` 캐시 분리.

### S6. import_sheets 명시 태깅 + 문서 + 검증 스크립트
- 날짜→season 순수 매핑 함수로 분리해 단위 테스트(경계 s2/전일 s1/NULL s1). AGENTS.md 정책 소절 + TTL 정정. boundary_check --post-deploy.
- 최종 게이트: 루트 pytest → `pytest tournament/tests`(별도 프로세스) → `python -m ruff check .`.

## 의존성
S1 → S2 → S3 → S4 → S5; S6은 S1만 의존하나 검증 의미상 마지막. 전 슬라이스 완료 후 **한 번에 push**(Railway 자동 배포 — S3/S4 사이 배포 공백 리스크 제거).

## 리스크 (요약)
- Postgres ALTER/백필: advisory_lock 내 멱등, 배포 후 --post-deploy로 NULL=0 확인.
- Postgres SQL 함정: DISTINCT+ORDER BY, AVG 중첩 → test_sql_compat로 방어.
- conftest fixture: save_match가 s2 태그 → 기존 손계산 테스트 무영향. test_season.py는 자체 fixture로 session 오염 방지.
- 내부 링크 season 누락: S4에서 href grep 검증.

## 커밋 정책
프로젝트 규칙(AGENTS.md §7): 중간 체크포인트 커밋 없이 로컬에서 전 슬라이스 완료 → GATE 2 승인 후 단일(또는 슬라이스별) 커밋·push.
