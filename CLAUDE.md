# 작업 지침 (AGENTS.md)

이 파일은 AI 에이전트가 이 프로젝트에서 작업할 때 따르는 규칙이다.
핵심 목표: **시키지 않은 일로 폭주하지 말 것. 단, 명확한 일은 빠르게 처리할 것.**

---

## 1. 스코프 — 질문과 작업을 구분한다

- "확인", "어떨지", "되나?", "맞나?", "왜?" 류 **질문에는 설명으로만** 답한다. 코드를 건드리지 않는다.
- 질문에 답하다가 개선점이 보이면, **하지 말고 한두 줄로 제안만** 하고 멈춘다. ("원하면 ~해줄까요?")
- 한 가지 요청에서 **연쇄 추론으로 범위를 늘리지 않는다.**
  (나쁜 예: "갱신되나?" → 캐싱 구현 → 배포 → DB 전환. 질문 하나에 이렇게 가지 치지 말 것.)

## 2. 작업 규모 — 균형 (속도 ↔ 안전)

빠르게 그냥 진행해도 되는 것 (멈추지 말 것):
- 명확하게 지정된 1~3개 파일의 작은 수정, 오타·버그·스타일 수정
- 방금 만든/읽은 파일에 이어지는 자연스러운 후속 편집
- 사용자가 이미 "해줘"라고 명시한 작업

진행 전에 **먼저 계획을 1~3줄로 말하고 승인**받을 것:
- 4개 이상 파일에 걸친 변경, 또는 100줄 이상 규모
- 새 의존성 추가, 설정/빌드/배포 파일 생성·변경
- DB 스키마·마이그레이션
- git 커밋·푸시는 **§7 규칙** 참고 (사용자 허가 후 진행)

원칙: **작고 명확하면 진행, 크거나 되돌리기 어려우면 멈추고 묻는다.** 애매하면 묻는다.

## 3. 검증할 수 없는 변경

- 로컬에서 실행·검증할 수 없는 변경(예: 환경 없는 DB, 배포 후에만 확인 가능한 것)은
  **임의로 진행하지 말 것.** 위험을 먼저 알리고 동의를 받는다.
- "아마 될 것이다" 상태로 큰 변경을 쌓지 않는다.

---

## 4. 토큰·시간 절약 (작업은 빠르게, 출력은 짧게)

- **이미 읽은 파일을 다시 읽지 않는다.** 편집 도구가 실패하지 않았다면 변경은 반영된 것이므로 재확인용 재읽기 금지.
- **파일 전체를 통째로 읽지 말 것.** 필요한 부분만(관련 함수/범위) 읽는다. 큰 파일은 검색으로 위치를 먼저 찾는다.
- **여러 파일을 무작정 읽기보다 검색(grep)으로 좁힌다.**
- **독립적인 조회·검색은 한 번에 묶어** 실행한다.
- **작업 로그를 장황하게 나열하지 않는다.** 매 단계 중계방송 금지. 결론과 바뀐 점 위주로.
- **명령 출력이 길면 핵심만 요약**한다. 전체를 그대로 붙여넣지 않는다.
- **다 됐으면 멈춘다.** 요청 범위를 넘는 "이왕 하는 김에"식 추가 작업·과잉 리팩터 금지.

## 5. 응답 스타일

- **결론부터.** 서론·장황한 배경 설명 없이 바로 답한다.
- 길게 늘어놓지 말고 필요한 만큼만. 표·목록으로 압축한다.
- 한국어로 답한다.

---

## 6. 이 프로젝트 메모

- 스택: **FastAPI + Jinja2(HTML 템플릿) + SQLite/Postgres(양쪽 지원)**, Discord 봇(`bot.py`).
- DB는 환경변수 `DATABASE_URL`이 있으면 Postgres, 없으면 로컬 SQLite(`codm.db`).
- 웹 실행: `uvicorn web_api:app --port 8000` (CWD = 이 폴더여야 DB·템플릿 경로가 맞음).
- 봇 실행: `python bot.py`. 통합 실행(봇+웹): `python start.py` (배포용, subprocess로 둘 다 띄움).
- 템플릿 스타일은 `templates/base.html`의 `<style>` 한 곳에 모여 있고, 다른 페이지가 그 클래스를 공유한다. (디자인은 토스 TDS 톤 적용)
- 비밀정보(`.env`, `service-account.json`)·DB(`codm.db`)·CSV·백업(`*.bak`, `codm.db.backup*`)은 절대 커밋하지 않는다. `.gitignore`에 이미 포함.
- GPT 프롬프트(`prompt.py`)와 커스텀 지표 공식(`metrics.py`)은 출처가 정해져 있어 함부로 수정 금지.

### 핵심 지표: ZCS (Zone Control Score)
- **ZCS는 이 프로젝트에서 가장 중요한 코칭 지표다.** K/D와 함께 병기하되, HP 컨텍스트에서는 ZCS를 제1 강조 지표로 다룬다.
- 공식: `ZCS = max(0, 1.1·OBJ + 8·캡처킬 + 4.1·K − 5·D)` (HP 전용 — SND엔 OBJ/캡처킬이 없어 계산 불가).
- 새 선수 평가/표시 로직을 짤 때, HP라면 **K/D와 ZCS를 함께 노출**하는 것을 기본으로 한다. SND에는 ZCS를 억지로 넣지 않는다.
- 진실 공식은 `metrics.py`의 `compute_zcs()`. SQL에서도 동일 공식(`MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)`)을 쓰며, `_adapt_sql`이 Postgres용으로 `GREATEST(0, ...)`로 변환한다.

---

## 7. Git 워크플로우 ⭐ (중요)

**저장소**: `https://github.com/F10W3R-13/codm-team-stats.git` (Private)
**브랜치**: `main` (기본)

### 커밋·푸시 규칙
- **주요 작업이 끝날 때마다 커밋 + 푸시**한다. "주요 작업" = 하나의 기능/수정 단위가 완결된 상태.
- **사용자에게 허가를 받은 뒤에 커밋·푸시**한다 ("이제 커밋·푸시할게요?" 식으로 1줄로 물어보고 진행).
- 사용자가 명시적으로 "커밋해/푸시해/올려"라고 했으면 별도 재확인 없이 진행.
- 사소한 수정(오타, 1-2줄)은 모을 수 있고, 기능 단위로 커밋.

### 커밋 메시지 규칙
- 한국어 또는 영어 (간결하게)
- 형식: `제목(한 줄)` + 빈 줄 + `본문(선택, 변경 요약)`
- 예: `Add player consistency (stddev) metric` / `Postgres 호환: INSERT OR REPLACE → UPSERT 헬퍼`

### 절대 커밋 금지 (`.gitignore` 처리됨)
- `.env` (토큰, API 키)
- `service-account.json` (구글 키)
- `codm.db`, `codm.db.backup*` (DB 파일)
- `*.csv` (마이그레이션 원본)
- `*.blueprint*.json` (make.com 원본)
- `*.bak*`, `__pycache__/`

### 표준 절차
```bash
git add -A
git status   # 비밀정보 빠졌는지 확인
git commit -m "제목"
git push origin main
```

---

## 8. 아키텍처 개요

```
디스코드 채널 ──스크린샷──▶ bot.py (on_message)
                              │ GPT-4.1 비전 (prompt.py)
                              ▼ JSON {mode, result, team_score, map, players[]}
                         stats_repo.save_match()
                              │
                              ▼
                         DB (SQLite/Postgres)
                              ▲
                              │ queries.py / analytics.py / metrics.py
            ┌─────────────────┴──────────────────┐
            ▼                                    ▼
    web_api.py (FastAPI)              commands_cog.py
    + templates/ (웹, 3개국어)          (디스코드 슬래시 명령, 영어)
```

**3개 실행 단위가 같은 DB 공유**: `bot.py`(봇), `web_api.py`(웹), `import_sheets.py`(일회성 마이그레이션).
봇이 쓰면 웹에 즉시 반영. 통합 실행은 `start.py`.

## 9. 데이터 모델 특이점 (핵심)

- **매치 분할 규칙**: 구글 시트에 match_id가 없어서 "이전 매치에 이미 등장한 선수가 다시 나오면 새 매치 시작"으로 분할 (`import_sheets.py`의 `group_matches()`). 단순 행수(4/5)로 자르면 안 됨.
- **ZCS 시트 오류 정정**: 구글 시트 Dashboard의 "ZCS" 열에 Total Damage 값이 잘못 배치되어 있었음. ZCS는 `metrics.py` 공식 `max(0, 1.1·OBJ+8·CK+4.1·K−5·D)`으로 재계산한 값이 정답.
- **이름 정규화**: 대소문자 섞임 (`Unravel`/`unravel`) → `import_sheets.py`의 `normalize_name()`으로 통일.
- **DB 수정 시**: 봇/웹을 먼저 중지하고 백업 후 수정 (SQLite 동시 쓰기 취약).

## 10. 언어/i18n 정책

- **코치용 = 한국어**, **선수용 = 영어/스페인어**.
- **디스코드 봇**: 영어 고정 (선수들이 보는 채널).
- **웹**: `?lang=ko|en|es` 전환. 3개국어 사전은 `i18n.py`.
- **AI 인사이트**: `lang` 파라미터 따라 GPT 응답 언어 변경 (캐싱: `insight_cache.py`, TTL 1시간 + 매치 기록 시 무효화).
- **로그(콘솔)**: 한국어.

## 11. 배포 (Railway)

- PaaS: Railway.app, GitHub 연동 (`F10W3R-13/codm-team-stats`).
- DB: Railway Postgres (`DATABASE_URL` 자동 주입).
- 실행: Procfile → `python start.py` (봇+웹 subprocess).
- 환경변수: `DISCORD_BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL`, `PORT`.
- 배포 후 DB는 비어있음 → `import_sheets.py`로 구글 시트 → Postgres 마이그레이션 필요.
