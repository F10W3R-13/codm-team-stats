# RDS (Round Domination Score) — SND 제1 커스텀 지표 설계

**날짜**: 2026-07-11
**상태**: 승인됨 (공식 + 표시 위치), 구현 대기
**대칭**: ZCS(HP 제1 지표) ←→ RDS(SND 제1 지표)

---

## 1. 배경

HP 모드에는 ZCS(Zone Control Score)라는 종합 커스텀 지표가 있어 선수 평가의 중심 역할을 한다. 반면 SND(수색섬멸)는 K/D, ADR, Impact 같은 기본 지표만 노출되고, SND만의 특수성(원 라이프 라운드, 퍼스트 킬/클러치의 압도적 가치)을 종합적으로 담은 단일 지표가 없었다.

ZCS와 대칭되는 **RDS(Round Domination Score)** 를 SND 제1 지표로 도입한다.

## 2. 핵심 스토리

> **RDS는 "라운드를 지배하는 종합 능력"을 측정한다.**
> SND는 원 라이프 라운드 게임으로, 라운드를 장악하는 사이클은:
> - **시작**: 퍼스트 킬(FK) — 라운드 첫 킬로 5v4 우위 창출
> - **유지**: 듀얼(K/D) + ADR — 안정적 교전력
> - **마무리**: 론 울프 윈(LWW) — 불리한 상황(1vX)에서 라운드를 직접 따는 클러치
> - **팀 기여**: 어시스트(A) — 트레이드(아군 사후 복수)로 흐름 유지

사용자 합의: **FK·LWW 중심 + 어시스트도 유의미 + K/D는 베이스 레이어.**

## 3. 공식

```
RDS = max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D)
```

`metrics.py` 함수:
```python
def compute_rds(kills, assists, first_kill, lone_wolf_win, adr, deaths) -> float:
    """Round Domination Score = max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D).
    SND 전용 — HP 데이터로 호출 금지."""
    if any(v is None for v in (kills, assists, first_kill, lone_wolf_win, adr, deaths)):
        return None
    val = 4.1*kills + 3.5*assists + 14*first_kill + 20*lone_wolf_win + 0.12*adr - 5*deaths
    return round(max(0, val), 2)
```

SQL 인라인 (queries.py):
```sql
MAX(0, 4.1*kills + 3.5*assists + 14*first_kill + 20*lone_wolf_win + 0.12*adr - 5*deaths) AS rds
```
→ `_adapt_sql`이 Postgres용 `GREATEST(0, ...)` 로 자동 변환 (ZCS와 동일 메커니즘).

### 3.1 항별 가중치 근거

K(4.1)를 1× 기준으로 잡은 상대적 가치:

| 항 | 점수 | K 대비 | 설계 의도 |
|----|------|--------|-----------|
| K | +4.1 | 1× | 기준점 — ZCS와 동일 계수 (비교 일관성) |
| D | −5 | 1.2× | 데스가 킬보다 약간 무겁다 — SND는 원 라이프라 데스 = 그 라운드 기여 종료, 부활 없음 → 기회비용이 HP보다 큼 |
| A | +3.5 | 0.85× | 트레이드/팀 기여 — SND에선 아군 사후 복수가 라운드 흐름을 지키는 핵심이라 킬의 85%로 평가 |
| FK | +14 | 3.4× | 퍼스트 킬 = "킬 1개 + 5v4 인원 이득 + 시간적 우위(정보·위치 장악)". COD 통계상 첫 킬 획득 시 라운드 승률 ~65-70% |
| LWW | +20 | 4.9× | 가장 비싼 행동 — 클러치(1v2+)는 이길 확률이 낮은 라운드를 직접 뒤집는 것. "킬 몇 개"가 아니라 **라운드 승리 자체를 캐리** |
| ADR | +0.12/단위 | (연속) | 전 매치 일관된 딜 효율 베이스 층. ADR 스프레드(80~127)가 좁아 실제 점수 차는 ±5점으로 억제 |

### 3.2 가중치의 성격 (중요)

> **3.4배, 4.9배 등의 수치는 SND 게임이론적으로 합당한 매그니튜드 오더이지, 수학적 정답이 아니다.**

- ZCS 공식 자체도 구글 시트 경험식이지 수학 도출이 아님 — 동일한 성격.
- 엄밀한 가중치는 각 항이 라운드 승리에 미치는 한계 효과를 로지스틱 회귀로 추출해야 하나, **현재 라운드 단위 승패 데이터가 없어 불가능.**

**TODO (가중치 재튜닝)**: 승패 데이터(`result` 컬럼)가 충분히 채워지면, 로지스틱 회귀 `P(승리) = sigmoid(β₁K + β₂D + β₃A + β₄FK + β₅LWW + β₆ADR)` 로 β 계수를 데이터에서 추출하여 RDS 가중치를 재튜닝한다. 현재는 경험적 매그니튜드로 진행.

### 3.3 데이터 대입 검증 (현재 6매치 평균)

| 선수 | K | D | A | FK | LWW | ADR | **RDS** | 해석 |
|------|---|---|---|----|----|-----|---------|------|
| Maozyn | 12.5 | 6.7 | 1.2 | 2.33 | 0.17 | 109 | **71.0** | FK 폭발 → 1등 ✅ |
| unravel | 12.0 | 6.8 | 3.2 | 1.2 | 0.2 | 127 | **62.6** | ADR+듀얼 |
| Kingz | 10.8 | 7.8 | 3.3 | 1.17 | 0.5 | 102 | **55.5** | 만능 밸런스 |
| Shisui | 10.0 | 8.5 | 3.8 | 1.0 | 0.67 | 105 | **51.8** | 클러치+A로 중위 끌어올림 ✅ |
| Cartels | 9.8 | 8.5 | 1.7 | 2.0 | 0 | 82 | **41.5** | FK 높아도 클러치 0+낮은 듀얼 → 꼴찌 ✅ |

검증:
- ✅ Maozyn(FK 특화) 1등 — "오프닝 중심" 반영
- ✅ Shisui(LWW+A 특화)가 클러치+어시스트로 중위 — "LWW·A 무시 금지" 반영
- ✅ Cartels(FK는 높으나 클러치 0, K/D 약함) 꼴찌 — "FK만으로 부족, 마무리 필요" SND 본질 반영
- ✅ 점수 범위 40-71로 직관적 (ZCS와 비슷한 스케일)

## 4. 표시 위치 (ZCS와 완전 대칭)

| 페이지 | 현재 (SND) | 변경 후 |
|--------|-----------|---------|
| `/players` | SND 표엔 K/D만 | SND 표에 **RDS 컬럼** 추가 |
| `/players/{name}` 상세 | SND에 RDS 없음 | SND 섹션에 **RDS 카드+추이** (timeseries API 확장) |
| `/leaderboard` | SND → K/D 기본 | 모드 토글 SND 시 기본 지표 **RDS** |
| `/compare` | 레이더 1행 ZCS(HP) | SND 비교 시 **RDS 첫 행** |
| `/maps` `/maps/{name}` | ZCS 중심 카드 | SND 맵 카드에 **RDS** |
| `/matches/{id}` | ZCS | SND 매치 시 **RDS** |

원칙: HP 컨텍스트에 ZCS가 나오는 모든 곳의 SND 대응점에 RDS를 깐다.

## 5. 구현 스코프

ZCS 처리 패턴을 그대로 복제한다 (grep "zcs" → SND 대응점 식별).

```
1. metrics.py
   ├─ compute_rds(k, a, fk, lww, adr, d) 함수 추가
   └─ all_snd_metrics(k, a, fk, lww, adr, d) 헬퍼 추가 (all_hp_metrics 대칭)

2. queries.py
   ├─ SND 평균 스탯 조회에 RDS 계산 추가 (ZCS 처리 패턴 복제)
   ├─ SND 리더보드 함수에 rds 메트릭 추가 (valid_snd 집합에 "rds" 추가)
   ├─ 맵별 성적 쿼리에 SND RDS 인라인 공식 추가
   └─ SQL: MAX(0, 4.1*kills + 3.5*assists + 14*first_kill + 20*lone_wolf_win + 0.12*adr - 5*deaths) AS rds

3. web_api.py
   └─ SND 쿼리 결과에 rds 필드 전달 (기존 hp zcs 패턴)

4. templates/
   └─ players.html, leaderboard.html, compare.html, matches/detail.html, maps.html
      SND 표/카드에 RDS 컬럼/카드 추가 (ZCS 마크업 패턴 복제)

5. i18n (i18n/_ko.py, _en.py, _es.py)
   └─ rds, rds_explained 키 추가 (3개국어)
   └─ test_i18n.py 로 키 동일성 검증 필수

6. AGENTS.md
   └─ "커스텀 지표 전체" 섹션에 RDS 항목 추가
   └─ "핵심 지표" 섹션에 SND 컨텍스트에서 RDS를 제1 강조 지표로 명시
```

### 구현 원칙
- `_adapt_sql`의 `MAX(0,...)`→`GREATEST` 변환은 이미 검증됐으니 Postgres 호환 OK (추가 작업 불필요).
- 템플릿은 ZCS 마크업 패턴을 복제 — 색 토큰(`--snd`/`--snd-weak`), 카드 변형(`.card--snd`), 인라인 금지 규칙 준수.
- 6매치 30기록이라 통계적 신뢰는 낮지만, 데이터 쌓이면 개선 (ZCS 초기와 동일).

## 6. 한계 & 향후 개선

| 한계 | 대응 |
|------|------|
| 가중치가 경험적 매그니튜드 (수학 도출 아님) | TODO: 승패 데이터 충분 시 로지스틱 회귀로 β 추출 → 재튜닝 |
| 6매치 30기록 (통계적 신뢰 낮음) | 데이터 누적 시 자연 개선. UI에서 매치 수 표시 권장 |
| 매치 길이 편차 (짧은 매치=낮은 점수) | ZCS/K/D도 동일 구조 — 기존 설계와 일관 |
| ADR 계수 0.12가 딜 베이스 의존도 결정 | 회귀 시 β로 검증 가능 |

## 7. 결정 기록

- **접근법**: 단일 선형 공식 (B 라운드 정규화, C 복합 서브스코어 대신) — ZCS와 구조 대칭, 현재 데이터로 즉시 가능, 튜닝 단순.
- **이름**: RDS (Round Domination Score) — ZCS와 대칭되는 3글자 약어.
- **가중치 철학**: FK·LWW 중심 + 어시스트 유의미 + K/D ADR 베이스.
