# 버그·병목 감사 설계 (2026-07-11)

## 목표
코드베이스 전체에서 **정확성 버그**와 **코드 품질/유지보수** 문제를 찾아 심각도별 보고서로 정리한다. **픽스는 하지 않는다.**

## 범위
8개 핵심 모듈 + 주요 템플릿 (전수 아님):

| 그룹 | 모듈 | 라인 | 감사 렌즈 |
|---|---|---|---|
| 데이터층 | `db.py` | 639 | SQL/Postgres 함정, `_adapt_sql`, 예외 삼킴 |
| 데이터층 | `stats_repo.py` | 106 | 쓰기 정합성, UPSERT, NULL |
| 데이터층 | `queries.py` | 1241 | N+1, NULL 집계, DISTINCT/ORDER BY, 연산자 우선순위 |
| 분석층 | `analytics.py` | 589 | 공식 오류, 분모 0, 방향성 |
| 분석층 | `metrics.py` | 115 | ZCS/Impact/DPK 공식, classify_role |
| 분석층 | `analytics_insights.py` | 414 | 캐시 정합성, 예외 처리, GPT 응답 파싱 |
| API/봇 | `web_api.py` | 608 | 라우트, 예외, 인증, 미사용 변수 |
| API/봇 | `bot.py` + `commands_cog.py` | 741 | 예외, 검증, 데드 코드 |
| (참고) 템플릿 | base/coaching_hub/player_detail/compare | — | Jinja2/JS 충돌, 미정의 변수, 인라인 스타일 |

## 접근 방식
**병렬 서브에이전트 분할** — `dispatching-parallel-agents` 스킬로 그룹별 에이전트 배정, 동시 조사.

## 공통 체크리스트 (각 에이전트에 부여)
AGENTS.md §8 알려진 함정 + 일반 버그 패턴:
1. `SELECT DISTINCT ... ORDER BY <표현식>` Postgres 호환성
2. `AVG(MAX(0,...))` 중첩 괄호 (`_adapt_sql` 변환 실패)
3. `WHERE a=? OR b=? AND c=?` 연산자 우선순위 (괄호 누락)
4. Jinja2 `{{ }}` 안 JS 연산자 (`||`, `&&`) 충돌
5. 분모 0 (K/D, DPK, AP%), NULL 집계, 빈 리스트 인덱싱
6. 예외 삼킴 (`except: pass`, bare except), 디버그 잔류
7. 데드 코드/문서 드리프트, `_adapt_sql` 변환 누락
8. 인라인 스타일, 미정의 CSS 토큰 참조
9. NULL/빈 입력 처리 (승패 미입력 등)
10. "낮을수록 좋음" 지표(DPK, 데스)의 방향 처리 오류

## 산출물
`docs/superpowers/specs/2026-07-11-bug-audit-report.md`
- 심각도: 🔴 크리티컬(고장/데이터 손상) / 🟡 주의(잠재적 오작동) / ⚪ 품질(유지보수)
- 각 항목: `file:line` 위치 / 증상 / 영향 / 제안 (픽스 아님)

## 비목표
- 성능 병목 (N+1 정도만 부수적 언급)
- 보안/인증 심층 감사
- 실제 픽스 구현
- 전 템플릿/전 파일 전수 조사
