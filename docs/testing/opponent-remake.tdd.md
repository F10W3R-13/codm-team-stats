# TDD Evidence Report — 상대팀 관리 시스템 리메이크 (opponent-remake)

- 작성: 2026-09-17 · 소스 계획: [docs/plans/opponent-remake.plan.md](../plans/opponent-remake.plan.md)
- 진입: `ecc:orch-add-feature` (size: large) → `ecc:tdd-workflow` · GATE 1: 진행 지시로 승인 처리(2026-09-17)
- 커밋 정책: 단일 커밋(AGENTS.md §7) — 본 리포트가 RED/GREEN 증거 보존

## User journeys

1. 코치로서 상대팀 생성·이름변경·삭제, 로스터 제거, 매치 지정/해제, 상대 alias 관리를 웹에서 전부 수행하고 싶다.
2. 코치로서 잘못 학습된 별명 매칭을 바로잡고 싶다 (재매칭 시 alias 무시).
3. 시스템으로서 OCR 쓰레기 이름이 상대팀 로스터를 오염시키지 않아야 한다.
4. 코치로서 모든 관리 작업의 성공/실패 피드백을 보고, 파괴적 작업 전 확인을 받고 싶다.
5. 코치로서 상대전적 상세에서 팀 요약·상대 로스터·NULL 스코어 표기를 보고 싶다.

## 슬라이스별 RED → GREEN

| 슬라이스 | RED | GREEN | 보장 |
|---|---|---|---|
| R1 관리 CRUD | test_opponent_crud 9/9 FAILED (404·함수 부재) | 157 passed | rename 로스터 유지, norm 중복 거부(D3), 삭제 정책(태그 NULL+로스터 삭제+선수·스탯 보존), unassign 스탯 무변동, alias CRUD(중복·미존재 거부), aliases 노출 |
| R2 매칭 품질 | test_opponent_rematch 3/3 FAILED | 160 passed | D1: 기본 assign은 alias 우선(현행 문서화) → ignore_alias 시 purge+재매칭+alias rebound, OCR suspect 스탯 3건 저장·로스터 0건, is_ocr_suspect 술어 |
| R3 admin UX | TestR3AdminUx 3/3 FAILED | 163 passed | pending_total·recent_matches, UI 훅(rename-form/delete/roster-remove/unassign/alias/ignore-alias/confirm), source enum 현지화 |
| R4 versus | test_versus_routes 신규 3/3 FAILED | 166 passed | summary(2전 1승1패·승률 50%·by_mode)·roster(games/K-D/source) 집계, NULL 스코어 "—"+미입력 배지("None : None" 부재), 카드 season 승계+avg_margin 라벨 |
| R5 통합·문서 | — (앞 슬라이스 테스트가 곧 매트릭스) | 루트 166 + 토너먼트 35(별도 프로세스) + ruff 클린 + test_i18n 5 | AGENTS.md §6(/versus 라인·admin 서브탭)·§10(상대팀 관리 정책) 갱신 |

RED 무효 케이스(정직 기록): R4 fixture 초안의 SQL 문법 오류(SyntaxError)·문법 수정 후 유효 RED 재확인. R1 fixture 실행 중 발견한 `row['name']`→`row['player_name']` KeyError는 구현 버그(GREEN 단계 수정, 테스트 아님).

## 리뷰 (Phase 5)

| 리뷰어 | 판정 | 처리 |
|---|---|---|
| ecc:code-reviewer | **APPROVE** (CRITICAL/HIGH/MEDIUM 0) | LOW 2건 반영: rename 캐시 무효화 1줄 추가, es `versus_win_rate` 번역("Tasa de victoria"). remove-roster 무효화 미추가는 기존 컨벤션(add/set_roster도 무효화 없음)과 일치 — 캐시 내용 실질 변경 없음 |
| ecc:security-reviewer | **PASS** | 인증(미들웨어 커버·우회 없음)·인젝션(전량 바인딩)·CSRF(SameSite=lax+POST/DELETE)·XSS(autoescape+encodeURIComponent+textContent) 전부 검증. LOW 2건은 기존 코드(secure 플래그·로그 쿼리)로 diff 밖 — 기록만 |

## 최종 검증 (verification-loop)

- 루트 pytest **166 passed** (신규 18: crud 12 + rematch 3 + versus 3) / 토너먼트(별도 프로세스) **35 passed** / `ruff check .` **All checks passed**
- 보안 스캔: 신규 시크릿 없음 (변경 파일에 토큰·키 부재)
- Diff: 13개 수정·신규 (admin_write, db, web_api, opponent_matching, stats_repo, queries, 템플릿 3, i18n 3, AGENTS.md, 테스트 2 신규+1 수정) — .gitignore 대상 미포함

## 커버리지·갱
- 수동 브라우저 검증 미수행(토스트 타이밍·다크모드 육안 확인) — 배포 후 스팟 체크 권장. Postgres 실측: 신규 SQL이 전부 단순 바인딩이라 로컬 SQLite 결과와 동일 예정(리뷰어 확인).

## 병합 증거 (스쿼시 대비)
RED/GREEN은 위 표의 pytest 출력으로 보존. 커밋 메시지가 본 리포트 경로 참조.
