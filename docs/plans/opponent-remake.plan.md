# Plan: 상대팀 관리 시스템 리메이크 — opponent-remake

- 상태: GATE 1 승인 대기 (2026-09-17 작성)
- 진입: `ecc:orch-add-feature` (size: large) · 실행: `ecc:tdd-workflow`
- 감사 근거: 백엔드·UX 이중 전수 감사(code-explorer 2건, 2026-09-17)
- 선행 문서: docs/superpowers/plans/2026-08-28-opponent-h2h.md (8월 최초 구현 — 본 계획은 그 개선·리메이크)

## 문제 인벤토리 (감사 확정)

**상(P0)**: admin 4개 작업의 flash 토스트가 즉시 reload에 묻힘 · 파괴적 병합에 confirm 없음 · 스코어 NULL이 "None : None" 렌더 · 관리 CRUD 부재(팀 삭제·이름변경·로스터 제거·지정 해제·상대 alias 관리 전무).
**중(P1)**: D1 잘못 학습된 alias를 재매칭으로 못 고침(resolve 우선순위) · D3 팀 중복 검사 정확 일치만(norm 불일치) · OCR 쓰레기 이름이 로스터에 무조건 축적 · pending 50건 LIMIT · 처리 시 스크롤 리셋 · 서버 메시지 한국어 하드코딩 · source enum 미번역 · versus 카드 season 미승계 · 빈 상태 안내 부재.
**저**: 데드 i18n 키(versus_record·versus_opp_player) · avg_margin 라벨 없음 · 목록 복귀 링크 없음.

## 제외 스코프
봇 슬래시 명령 추가 · classify_opponents.py 웹 이관 · FK/PRAGMA 구조 변경 · H2H 모드 분리(P3).

## 슬라이스 (순서 = 구현 순서)

### R1. 관리 CRUD 완결 — admin_write.py, db.py, web_api.py, i18n
- 신규: `rename_opponent_team`(norm 중복 검사 포함) / `delete_opponent_team`(정책: matches.opponent_team_id→NULL, rosters 삭제, players·스탯 유지) / `remove_opponent_roster_row` / `unassign_match_opponent`(태그만 NULL) / 상대 alias 헬퍼 `db.add_opponent_alias`·`remove_opponent_alias`.
- `add_opponent_team` 중복 검사 norm_name 기반 강화(D3).
- 라우트(POST+JSON, 기존 패턴): `/admin/opponent/team/rename`, `team/delete`, `roster/remove`, `match-unassign`, `alias`(POST/DELETE).
- 응답 `{ok, message}` 유지 + `code` 필드 추가(R3 프런트 매핑용).
- opponent_admin_data에 `aliases` 목록 추가.

### R2. 매칭 품질 — db.py, admin_write.py, stats_repo.py, opponent_matching.py
- `resolve_opponent_player_id(..., ignore_alias=False)` 파라미터(D1) — 1단계 alias 스캔 우회.
- **핵심 함정 대응**: alias INSERT OR IGNORE는 오답 행을 못 덮어씀 → `purge_opponent_alias_variants(conn, name)`(norm 일치 alias 사전 삭제) 후 재학습으로 rebound.
- `assign_match_opponent(..., ignore_alias)` — true면 purge+ignore_alias 재매칭. `/admin/opponent/match-team`에 전달.
- `opponent_matching.is_ocr_suspect()`로 술어 이동(모듈 재사용) + `_save_opponent_stats`에서 suspect 이름은 **스탯 저장·로스터 스킵**.

### R3. admin UX 수복 — admin_opponents.html, admin_write.py, i18n
- fetch 공통 패턴: 401 처리 + try/catch + `flash(r.message || t[r.code])` + `setTimeout(reload, 800)`(admin_players 선례). **pending assign은 예외 — 행 DOM 제거로 스크롤 유지.**
- 병합 confirm() (영향 문구 포함).
- pending 51건+ "외 N건" 카운트(`pending_total`).
- R1 CRUD UI: 팀 카드 연필(인라인 rename 폼)·삭제(confirm, 매치 수 경고)·로스터 행 ×·팀별 최근 매치 select로 지정 해제·alias 테이블+추가 폼.
- R2 연동: assign 행에 "alias 무시 재매칭" 체크박스.
- source enum 현지화(`opp_source_*`). 전부 클래스 기반(인라인 금지).

### R4. versus 화면 강화 — queries.py, versus.html, versus_team.html, i18n
- 카드 링크 season 승계 · avg_margin 라벨.
- 상세: 스코어 NULL→"—", result NULL→미입력 배지, 목록 복귀 링크, 요약 헤더(W-L-승률·모드별), 상대 로스터 섹션(이름·source·경기수·K-D — H2H 루프에서 accumulate+rosters 1회 조회), 빈 상태 안내(/admin/opponents 링크).
- 데드 키 `versus_record`·`versus_opp_player` 사용 처리.

### R5. 테스트 보강 + 문서 — tests, AGENTS.md
- 매트릭스: CRUD 왕복, D1 end-to-end(오학습→ignore_alias→rebound), D3 norm 거부, OCR suspect 로스터 스킵, versus NULL 렌더·summary/roster 집계, 기존 스위트 회귀.
- AGENTS.md §6(/versus 라우트 추가·/admin/opponents 기능)·매칭 규칙(purge 재학습) 갱신.

## 의존성·배포
R1→R2→R3→R4(병렬 가능)→R5. 스키마 변경·마이그레이션·배포 데이터 작업 **전혀 없음** — push만으로 완결. 전 슬라이스 완료 후 한 번에 push.

## 리스크
- alias 오답 잔존(INSERT OR IGNORE) → purge 없이는 재오염: D1 테스트는 rebound까지 검증.
- 파괴적 작업 → confirm에 영향 수치 + 삭제 정책 테스트 고정(FK 없어 수동 무결성).
- SQLite/Postgres: 전부 ? 바인딩, norm 비교는 Python(LOWER() 콜레이션 차이 회피).
- i18n 키 3개 언어 동시 — test_i18n 자동 강제.
- 캐시: unassign/delete도 invalidate_all.
