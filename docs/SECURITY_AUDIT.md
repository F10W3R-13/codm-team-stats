# 보안 감사 보고서

**감사 일자**: 2026-07-25
**대상**: CODM 팀 매니지먼트 웹앱 (FastAPI + Discord 봇, Railway 배포)
**범위**: 인증/인가 · SQL/DB · XSS/템플릿 · 인프라/시크릿 (코드 기반 읽기 전용 분석)
**현재 상태**: 소규모 신뢰 팀 내부 사용 (SaaS 전환 계획 없음)

---

## 전제와 심각도 기준

이 감사는 **두 가지 렌즈**로 평가한다. 현재 사용 형태와 무관하게 SaaS 확장 시를 대비한 기록 목적이다.

| 렌즈 | 전제 | 의미 |
|---|---|---|
| **현 운영 (NOW)** | 신뢰된 소수만 URL/비밀번호 공유, 외부 공격자 없다고 가정 | "당장 사고날 수 있는가?" |
| **SaaS 전환 시 (SaaS)** | 불특정 다수/다중 테넌트 노출 | "공개 서비스로 확장하면 결격인가?" |

심각도 표기: `NOW: X / SaaS: Y` (예: `NOW: Low / SaaS: Critical`).

---

## 핵심 결론 (TL;DR)

- **현 운영 관점**: 사용자가 비밀번호를 환경변수로 제대로 설정하고 URL이 유출되지 않는다면 **즉각적 사고 위험은 낮다**. 다만 **배포자가 env를 까먹으면 기본 비밀번호 "3717"**이 그대로 노출되는 단일 실패점이 존재.
- **SQL 인젝션 / 저장형 XSS** 방어는 기본기가 잘 되어 있음 (`?` placeholder 일관 사용, Jinja2 autoescape + `|safe` 0건, `tojson` 올바른 사용).
- **SaaS 전환 시**에는 인증 시스템 전반과 심층 방어 계층이 전면 재설계 대상. 개별 패치가 아니라 아키텍처 단위 작업.

---

## 발견 항목

### 🔴 Critical

| ID | 항목 | 위치 | NOW | SaaS | 비고 |
|---|---|---|---|---|---|
| C1 | 기본 비밀번호 "3717" + SECRET_KEY 파생 + 평문 `==` 비교 | `config.py:31,33` / `auth.py:18-20` | Med | Critical | env 미설정 시 4자리 숫자 폴백. `SECRET_KEY`가 `codm-admin-{ADMIN_PASSWORD}`로 파생 → 비밀번호 알면 **인증 쿠키 직접 위조 가능** (비번 입력 우회). 평문 비교라 타이밍 공격까지. |
| C2 | AI 엔드포인트 4개 무인증 (GPT 비용 폭탄 벡터) | `web_api.py:283-368` | Low | Critical | `/api/insight/player`, `/match`, `/map`, `/briefing`이 `/admin` 미들웨어 밖. URL 알면 누구나 OpenAI 비용 무제한 유발 가능. |
| C3 | CORS 미설정 | `web_api.py:74` | Low | Critical | `CORSMiddleware` 0건. `samesite=lax`가 1차 방어지만 인증된 admin 방문 시 크로스오리진 공격 표면. |

### 🟠 High

| ID | 항목 | 위치 | NOW | SaaS |
|---|---|---|---|---|
| H1 | CSRF 토큰 전면 부재 — 모든 admin POST/DELETE 무방비 | 모든 admin 템플릿 | Low | High |
| H2 | 로그인 시도 제한 없음 — 기본 비번과 결합 시 수 초 뚫림 | `web_api.py:409` | Med | High |
| H3 | 보안 헤더 0건 (CSP/X-Frame-Options/HSTS/nosniff) → clickjacking 가능 | `web_api.py` 전체 | Low | High |
| H4 | DOM 기반 XSS — `player_detail.html:405` `innerHTML`에 timeseries `date` 주입 | `player_detail.html:399-407` | Med | High |
| H5 | Open Redirect — `Referer` 헤더 검증 없이 리다이렉트 | `web_api.py:611,623` | Low | High |
| H6 | 감사 로깅 부재 — 매치 삭제/선수 병합(되돌릴 불가) 누가/언제 추적 불가 | `admin_write.py` 전체, `audit_log` 테이블 없음 | Low | High |
| H7 | 의존성 버전 미고정 — `>=` 하한만, lockfile 부재 → 매 빌드마다 다른 버전 | `requirements.txt` | Low | High |
| H8 | Google 서비스 계정 JSON 통째로 env — 유출 시 시트 전체 탈취 | `config.py:22`, `DEPLOYMENT.md` | Low | High |
| H9 | 프롬프트 인젝션 — 선수 닉네임/맵명이 GPT user 메시지로 직접 주입. OCR 자동학습 닉네임이 공격 벡터 | `analytics_insights.py:99,135,175,220,286,349` | Low | High |

### 🟡 Medium

| ID | 항목 | 위치 |
|---|---|---|
| M1 | 쿠키 `secure=False` 하드코딩 (MITM 시 세션 탈취) | `web_api.py:420` |
| M2 | 로그아웃 불가 + stateless 쿠키 → 세션 무효화 불가 (침해 대응 불가) | `auth.py` 전체 |
| M3 | 쿠키에 `{"authed": True}`만 → 사용자 식별/책임 소재 불가 | `auth.py:25` |
| M4 | RBAC 부재 (코치/선수 역할 분리 없음) | `auth.py`, `web_api.py` |
| M5 | CDN SRI 부재 (Pretendard/Chart.js, 서플라이체인 공격 시 전 페이지 변조) | `base.html:15-16` |
| M6 | `vod_url`이 `<a href>`/iframe `src`에 raw → `javascript:`/속성 인젝션 | `matches.html:18`, `match_detail.html:113-119` |
| M7 | 레이트 리밋 전 구간 부재 (login/AI/일반) | `web_api.py` 전체 |
| M8 | FastAPI `/docs` (Swagger) 프로덕션 노출 → 엔드포인트 시그니처 노출 | `web_api.py:74` |
| M9 | 예외 메시지 그대로 응답/봇 reply → DB 오류 시 SQL 단편, OpenAI 예외 시 키 접두사 노출 | `bot.py:210,214,251`, `web_api.py:360-362` |
| M10 | DB 백업 코드 레벨 전무 (Railway 자동백업만 의존, 복구 테스트 없음) | scripts/ 없음 |
| M11 | 봇 진단 로그에 디스코드 사용자 ID/닉네임/채널 매번 기록 (PII 축적) | `bot.py:150-163,167-200` |
| M12 | SQL: `team_trend`/`map_trend` f-string INTERVAL (`int()` 캐스팅에 기대는 깨지기 쉬운 방어) | `queries.py:655,657,1002,1004` |
| M13 | 세션 고정 방지 로직 부재 | `web_api.py:409-423` |

### 🟢 Low

| ID | 항목 | 위치 |
|---|---|---|
| L1 | JS 컨텍스트 raw 삽입 — 현재 autoescape가 우연히 막으나 `|tojson` 표준화 필요 | `compare.html:138,144`, `admin_aliases.html:72`, `admin_players.html:58` |
| L2 | `lang`/`error` Query param 무검증 (autoescape 회피 시 즉시 반사형 XSS로 승격) | `web_api.py` 전체 `Query("ko")` |
| L3 | `/health` 엔드포인트 부재 (Railway 헬스체크 불가) | `web_api.py` |
| L4 | 하드코딩된 팀 로스터 + 선수 실명 "Jason" — 코드-데이터 분리 + GDPR 관점 | `prompt_context.py:21-29` |
| L5 | SQL 동적 식별자 보간 (현재는 화이트리스트로 안전, 제거 시 즉시 인젝션) | `admin_write.py:113,117,140,144,185` |

---

## ✅ 양호한 부분 (잘 되어 있는 것)

- **SQL 파라미터화 일관** — 값은 전 구간 `?`/`%s` placeholder
- **Jinja2 autoescape + `|safe` 0건** — 저장형 XSS 주요 벡터 회피
- **`tojson` 올바른 사용** — `</script>`, U+2028/2029, 따옴표 모두 이스케이프 검증 완료
- **`textContent` 일관 사용** (`flash()`, 인사이트 주입 부분)
- `.gitignore` 정상 동작 — `.env`/`service-account.json`/`codm.db` git 추적 없음 검증
- **path traversal 안전** — 코칭 브레인 로더는 디렉토리 리스팅 기반 매칭, 업로드는 메모리 처리(디스크 미저장)
- PII 최소 저장 (IGN 외 개인정보 컬럼 없음)
- OpenAI 클라이언트 `timeout=15s, max_retries=1` (무한 블록 방어)
- Postgres `pg_advisory_lock`으로 마이그레이션 직렬화

---

## 현 운영 관점에서의 실질 위험 평가

현재 "신뢰된 소수, 비공개 URL" 전제에서 **지금 당장 사고로 이어질 가능성이 있는** 항목만 추리면:

1. **C1 (기본 비밀번호 "3717")** — Railway env에 `ADMIN_PASSWORD`가 설정되어 있다면 현 운영에선 낮음. 하지만 **재배포/신규 환경에서 env 누락하는 순간 즉시 4자리 비번**. 가장 현실적인 단일 실패점.
2. **H2 (로그인 무제한)** + C1 결합 — 비번이 짧으면 brute-force에 수 초 노출. 다만 URL을 모르면 시도 자체가 안 됨.
3. **H4 (DOM XSS via `match_date`)** — 관리자가 (또는 import 시스템이) 이상한 `match_date` 값을 넣으면 선수 상세 페이지에서 스크립트 실행. 다만 공격자가 아닌 **관리자 본인 실수**로만 발생.

나머지 대부분은 외부 공격자가 전제되어야 의미있는 항목. 현 운영에서는 **URL 유출 + 기본 비번 노출** 두 가지만 막으면 사실상 안전.

---

## SaaS 전환 시 — 근본 아키텍처 결격 (메모)

> **이 섹션은 SaaS 확장을 결정했을 때 참조용. 현재는 미사용.**

개별 취약점보다 더 본질적인 3가지. 패치가 아니라 **재설계** 단위.

1. **테넌시 격리 전무** — 모든 데이터가 단일 팀 전제. 모든 테이블에 `tenant_id` 도입 + RLS(Row-Level Security) 또는 앱 레벨 필터링 필요.
2. **사용자 모델 부재** — `users` 테이블 자체가 없음. "공개 익명" vs "단일 공유 비밀번호 admin" 두 상태만. → 멤버십/초대/역할 시스템을 처음부터 설계해야.
3. **비책임성** — 쿠키에 사용자 식별자 없고, 감사 로그 없고, stateless 세션. → 다중 관리자 환경에서 책임 추적 불가 (GDPR/SOC2 컴플라이언스 위반).

SaaS 로드맵이 진짜라면 인증/테넌시 레이어를 별도 스프린트로 잡는 게 현실적.

---

## 권장 진행 순서 (참고용, 미실행)

> 현재는 조치하지 않음. 필요해지면 아래 순서로.

| 단계 | 시점 | 내용 |
|---|---|---|
| **1** | 현 운영에서 사고 방지 최소 조치 | C1 (기본 비번 제거·SECRET_KEY 분리·`hmac.compare_digest`), H2 (로그인 시도 제한). 단 2개 항목만으로 현재 위험의 90% 제거 |
| **2** | SaaS 착수 직전 | H1·H3·H5·H7, Medium 보안 헤더/레이트리밋/에러 마스킹. 외부 공개 전 최소 조건 |
| **3** | SaaS 아키텍처 스프린트 | 테넌시 + 사용자 모델 + RBAC + 감사 로그 (H6, M3, M4) |
| **4** | 운영 지속 개선 | DB 백업, 의존성 고정(H7), 프롬프트 인젝션 방어(H9), 진단 로그 정리(M11) |

---

## 분석 방법

- 4개 독립 도메인으로 분리하여 병렬 심층 분석 (인증/인가·CSRF, SQL/DB, XSS/템플릿, 인프라/시크릿)
- 읽기 전용 — 어떤 파일도 수정하지 않음
- 코드 기반 판정 — 추측 배제, 라인 번호 + 스니펫 기반
- `git check-ignore`로 시크릿 추적 여부 검증

---

*이 문서는 특정 시점(2026-07-25)의 스냅샷이다. 코드 변경 시 재감사 필요.*
