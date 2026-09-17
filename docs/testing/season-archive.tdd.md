# TDD Evidence Report — 시즌 아카이빙 (season-archive)

- 작성: 2026-09-17 · 소스 계획: [docs/plans/season-archive.plan.md](../plans/season-archive.plan.md)
- 진입: `ecc:orch-add-feature` (size: large) → `ecc:tdd-workflow` · 게이트: GATE 1 승인(2026-09-17) → GATE 2 대기
- 커밋 정책: 중간 체크포인트 커밋 없이 단일 커밋(AGENTS.md §7) — 본 리포트가 RED/GREEN 증거 보존 역할 수행

## User journeys

1. 코치로서 s1(9/5 이전) 스탯이 현시즌 지표에 섞이지 않게 하고 싶다 (시즌 초기화).
2. 코치로서 웹에서 S1/S2를 전환해 아카이브 시즌을 열람하고 싶다 (삭제 아님).
3. 시스템으로서 새 매치는 항상 현재 시즌으로 기록되고, 시즌이 다른 매치와 잘못 병합되지 않아야 한다.

## 슬라이스별 RED → GREEN 증거

실행 러너: `python -m pytest` (루트) / `python -m ruff check .` — JS 러너 매트릭스 대신 프로젝트 표준으로 치환(계획 승인됨).

| 슬라이스 | RED (구현 전 실패) | GREEN (구현 후) | 보장되는 것 |
|---|---|---|---|
| S1 스키마+백필 | `pytest tests/test_season.py` 4/4 FAILED (`no such column: season`, 상수 없음) — 2026-09-17 실행 | 4/4 PASSED | 경계일(09-05)=s2·전일/NULL=s1 분류, 백필 멱등(수동 태그 보존), 신규 DB 스키마 포함 |
| S2 쓰기 태깅+dedup 가드 | 2/2 FAILED (`duplicate=True`로 s1 병합 발생, season=None) | `tests/test_season.py + test_stats_repo_dedup.py` 13 PASSED | 신규 저장 s2 태깅, s1 매치로의 재업로드 병합 금지, 동일 시즌 병합 로직 회귀 없음 |
| S3 읽기 필터 | 9/9 FAILED·ERROR (season 파라미터 없음 TypeError + 기본 뷰에 s1 노출) | 15/15 PASSED (fixture 전컬럼 수정 후) | 조인형·서브쿼리형 양 패턴 시즌 분리, NULL 폴백(양쪽 노출), 봇 기본값 상속 |
| S4 웹 ?season= | 3/5 FAILED (s1 무시, 422 없음, 토글 마크업 없음) | 전체 142 PASSED (i18n 동일성 포함) | ?season=s1 뷰 분리, 무효값 422, nav 토글, lang 조합, 스모크 5개 변형 |
| S5 캐시 키 분리 | 1/3 FAILED (`set() got unexpected keyword 'season'`) | 전체 145 PASSED | (kind,target,lang,season) 4튜플, 3-인자 하위 호환, API 시즌별 인사이트 분리 |
| S6 매핑+문서 | 1/1 FAILED (`season_for_date` 부재) | 전체 146 PASSED | 날짜→시즌 순수 매핑(백필 SQL과 동일 규칙), import_sheets 명시 태깅 |

RED 무효 케이스(정직 기록): S3 최초 실행 시 fixture IntegrityError(선수명 충돌)·NULL 컬럼 metrics 오류는 **설정 결함**이라 유효 RED에서 제외 — fixture 수정 후 순수 어설션 실패로 재확인 후 구현 진행.

## 최종 검증 (verification-loop)

- 루트 스위트: **146 passed** (test_season.py 23개 신규 포함)
- 토너먼트 스위트(별도 프로세스, 필수): **35 passed**
- Lint: `ruff check .` → **All checks passed**
- 보안 스캔(코드상): 신규 시크릿 없음 (변경 파일에 토큰/키 부재 — security-reviewer PASS)
- Diff: 16개 수정 + 4개 신규 파일, `.gitignore` 대상(DB·env) 미포함 확인

## 리뷰 (Phase 5) 결과 및 처리

| 리뷰어 | 판정 | 발견 → 처리 |
|---|---|---|
| ecc:code-reviewer | WARNING→수정 완료 | **HIGH** 템플릿 fetch 4곳 season 누락(player_detail×2, map_detail, coaching_hub) → `&season={{ season }}` 추가 수정. MEDIUM save_match 태깅 = 계획 확정사항(하단 비고). MEDIUM 봇 공백 = 무근거(아래 비고). LOW 섀도잉 2건·중복 분기 → 수정. LOW analytics SQL 중복 → 미수정(화장적, 최소 diff 원칙). |
| ecc:security-reviewer | **PASS** | SQL 전량 파라미터 바인딩·f-string 3곳 화이트리스트/int 캐스트 확인. LOW pattern 후행 개행(pydantic v1 한계, 인젝션 불가) → 미수정 기록. |
| ecc:database-reviewer | 커밋 가능 | 마이그레이션 멱등성·advisory lock·인덱스 순서·3값 논리 양 엔진 일치 PASS. MEDIUM save_match 태깅(동일 지적) → 비고 참조. LOW SQLite 동시기동 레이스 = 기존 패턴(result 컬럼 때부터 동일, 1회성) → 미수정 기록. |

### 비고 1 — save_match 태깅을 CURRENT_SEASON 고정으로 유지한 근거 (리뷰 MEDIUM 기각)
계획 확정사항(6번). 봇의 `match_date`는 디스코드 **메시지 작성일**이라 사실상 항상 당일 → `season_for_date(오늘)` ≡ `CURRENT_SEASON`. 반대로 `season_for_date` 채택 시 conftest 시드(2026-08 날짜 4매치)가 전부 s1으로 태그되어 기존 손계산 테스트 전반이 깨진다. "과거 날짜를 당일 기록" 경로는 봇 플로우에 존재하지 않아 실영향 0.

### 비고 2 — 봇 공백 기간 우려 기각
리뷰어는 "배포 데이터 전부 s1이라 봇이 빈 값을 반환"이라 지적했으나, 사전 점검(2026-09-17)에서 **s2 매치 18건(HP 스탯 75행, SND 15행)이 이미 존재**. 봇 명령은 공백 없이 현시즌 데이터를 반환한다.

## 커버리지·갱
- 커버리지 도구 부재(프로젝트 표준 준수 — 계획 승인 시 80% 기준 치환). 갱: bot.py OCR 업로드→save_match 실경로 E2E(모킹 불가 영역), Postgres 실배포 검증은 `--post-deploy`로 수행 예정.

## 병합 증거 (스쿼시 대비)
RED·GREEN 전 단계는 위 표에 명시된 pytest 출력으로 보존됨. 단일 커밋 메시지에 본 리포트 경로를 참조한다.
