# 디자인: 지식베이스 모듈화 재구성

| 항목 | 값 |
|---|---|
| 날짜 | 2026-07-11 |
| 상태 | 승인 대기 |
| 기반 파일 | `게임철학_역학지식.md` (670줄), `CODM_2026_Esports_Settings.md` |

---

## 1. 문제

현재 지식베이스는 670줄짜리 단일 마크다운 파일이다. 네 가지 용도(AI 코칭 대화, 전사문 흡수, 직접 참조, 문서 생성 원료) 모두에서 매번 파일 전체를 로드해야 해서:

- **토큰 소모**: 매 대화마다 670줄 전체를 컨텍스트에 올려야 함
- **다루기 무거움**: 철학·역학·맵지식·팀운영·로그가 한 몸이라 특정 주제만 다루기 어려움
- **확장 불안**: 전사문 추가될수록 파일만 단방향으로 길어짐

## 2. 설계 결정 (3가지)

브레인스토밍을 통해 확정된 결정:

1. **용도**: AI 코칭 대화 + 전사문 흡수 + 직접 참조 + 문서 생성 (전부 지원)
2. **입도**: 계층형 하이브리드 — 철학 원칙은 응집(한 파일), 맵 지식은 원자화(맵별 파일)
3. **링크**: 순수 마크다운 링크 `[이름](경로.md)` — 도구 종속성 없음

## 3. 작업공간 전체 구조

지식(자라는 것)과 참조(규칙/세팅)를 최상위에서 분리한다.

```
Superpowers Workspace/
├── knowledge/              # 코치의 지식 (전사문 흡수로 자라는 생명체)
│   ├── INDEX.md            # 🚪 입구. 항상 로드. ~80줄.
│   ├── principles/
│   ├── mechanics/
│   ├── modes/
│   ├── maps/
│   ├── team/
│   └── log/
│
└── reference/              # 공식 규칙/세팅 (참조용, 구조 안정적)
    └── CODM_2026_Esports_Settings.md
```

**분리 이유**: 세팅 문서는 코치의 통찰이 아니라 토너먼트 공식 규칙이다. 성격이 다른 문서를 한 공간에 섞으면 "이건 지식인가 규칙인가" 혼란이 생긴다. 두 영역은 INDEX.md에서 링크로 연결한다.

## 4. knowledge/ 내부 구조와 파일 매핑

```
knowledge/
├── INDEX.md                      # 입구 + 네비게이션 + 버전 메타 + 확장 규칙
│
├── principles/
│   └── 코칭철학원칙.md            # 9개 원칙 (서로 참조 많아 한 파일 응집)
│
├── mechanics/
│   ├── CODM기본역학.md           # TTK / 리스폰 / 시야 / 맵구조
│   ├── 무기옵스킬메타.md          # 선수별 무기-스타일 + 옵스킬 타이밍 역학
│   └── 공용어사전.md             # 팀 공용어 표 (Money hill, Shadow, Slay out...)
│
├── modes/
│   ├── Hardpoint.md             # 모드 일반 역학 + 흔한 실수
│   ├── SearchDestroy.md
│   └── Control.md
│
├── maps/
│   ├── Combine.md               # 맵별: 해당 맵의 모든 모드 통합
│   ├── Hacienda.md
│   ├── Takeoff.md
│   ├── Standoff.md
│   ├── Summit.md
│   ├── Arsenal.md
│   └── CrossroadsStrike.md
│
├── team/
│   └── 팀운영.md                 # 콜 시스템 + 역할 분배 + 갈등 관리
│
└── log/
    └── 흡수로그.md               # 전사문 1-6 흡수 기록
```

### 현재 섹션 → 새 파일 매핑

| 원본 (게임철학_역학지식.md) | 새 위치 |
|---|---|
| 헤더/목적/버전/읽는법/확장규칙/보완필요 (L1-10, L13-21, L637-668) | `INDEX.md` |
| Section 1: 원칙 1-9 (L25-235) | `principles/코칭철학원칙.md` |
| Section 2.1: 기본 역학 (L241-262) | `mechanics/CODM기본역학.md` |
| Section 2.2: 무기·옵스킬 메타 (L264-318) | `mechanics/무기옵스킬메타.md` |
| Section 2.3: 공용어 (L320-346) | `mechanics/공용어사전.md` |
| Section 3.1 Hardpoint (L356-378) | `modes/Hardpoint.md` |
| Section 3.1 SnD (L379-394) | `modes/SearchDestroy.md` |
| Section 3.1 Control (L395-426) | `modes/Control.md` |
| Section 3.2 맵별 HP — Combine (L429-437) | `maps/Combine.md` (HP 섹션) |
| Section 3.2 맵별 HP — Hacienda (L439-443) | `maps/Hacienda.md` |
| Section 3.2 맵별 HP — Takeoff (L445-449) | `maps/Takeoff.md` |
| Section 3.2 맵별 HP — Summit (L451-455) | `maps/Summit.md` |
| Section 3.2 맵별 HP — Standoff (L457-461) | `maps/Standoff.md` (HP 섹션) |
| Section 3.2 맵별 HP — Arsenal (L463-467) | `maps/Arsenal.md` |
| Section 3.3 맵별 SnD — Raid (L474-476) | `modes/SearchDestroy.md` 하단 "맵별 메모" (한 줄: 긍정 사례) |
| Section 3.4 맵별 Control — Standoff (L483-485) | `maps/Standoff.md` (Control 섹션) |
| Section 3.4 맵별 Control — Crossroads (L487-488) | `maps/CrossroadsStrike.md` |
| Section 3.4 맵별 Control — Raid (L490-491) | `modes/Control.md` 하단 "맵별 메모" (보완 필요 표시) |
| Section 4: 팀 운영 전체 (L497-591) | `team/팀운영.md` |
| Section 5: 흡수 로그 (L595-633) | `log/흡수로그.md` |

### 입도 결정 원리

- **맵은 분리**: Combine에 새 전술이 추가돼도 Hacienda 파일을 안 건드려도 됨. 파일이 커져도 다른 맵에 영향 없음.
- **원칙은 응집**: 원칙 7(play to win)이 원칙 8(keep intention)을, 원칙 9(잠재 가치)가 원칙 3(안에서 가치)을 끌고 다님. 쪼개면 링크만 수십 개. 한 파일이 읽기 편함.
- **modes/와 maps/ 분리**: "하드포인트가 어떻게 작동하나"(modes/) vs "Combine P3는 어떻게 하나"(maps/)는 다른 질문. 모드 일반 질문 때 맵 파일을 안 열어도 됨.

### 맵 파일 구조 (모든 maps/*.md 공통)

한 맵의 모든 모드 지식을 한 파일에 통합한다. 맵이 어떤 모드에서 쓰이는지 헤더에 명시.

```markdown
# Combine

> 맵 풀: [Hardpoint](../modes/Hardpoint.md)
> 관련 원칙: [원칙 3 안에서 가치](../principles/코칭철학원칙.md), [원칙 5 스폰은 경향](../principles/코칭철학원칙.md)

## Hardpoint

### P1
(내용)

### P2
(내용)

### P3
(내용 — 첫째/둘째 P3 교차 전술 포함)

### P4
(내용)
```

내용이 없는 모드 섹션은 생략하고, INDEX.md의 "보완 필요"에 기록한다.

## 5. INDEX.md 설계

입구 파일. **이 파일만 항상 로드하면 전체 구조가 보인다.** 본문은 필요한 것만 펴본다.

INDEX.md에 들어가는 것:
- **목적 한 줄** (이 지식베이스가 무엇인가)
- **버전 메타** (v0.2, 2026-07-11, 기반 전사문 1-6)
- **파일 네비게이션** (모든 파일로 가는 링크 + 한 줄 설명)
- **읽는 법** (원본 L13-21의 섹션 가이드를 파일 단위로 재작성)
- **확장 규칙** (언제/어떻게 갱신하는가 — 원본 L637-668)
- **보완 필요 영역** (원본 L658-668의 체크리스트)
- **참조 링크**: `reference/` 영역으로 가는 링크 (맵 풀, 밴픽, 역할 제약 등)

대략 80줄 내외. 670줄 → 80줄로 입구를 가볍게 만드는 것이 이 재구성의 핵심 가치.

## 6. 링크 규칙

- 모든 파일은 `INDEX.md`로 돌아가는 링크를 맨 위에 둔다: `← [INDEX](../INDEX.md)`
- 파일 간 참조는 상대경로 마크다운 링크: `[Combine P3](../maps/Combine.md#p3)`
- 외부 참조(reference/)는 knowledge/ 기준 `../reference/` 경로 사용
- 링크 텍스트는 의미있는 이름으로 (경로 자체가 아닌)

## 7. 이전 원본 보존

- 원본 `게임철학_역학지식.md`는 작업공간 루트에 그대로 보존 (삭제 안 함)
- 분할 완료 후 INDEX.md에 "원본 아카이브" 링크로 명시
- 원본은 향후 검증 완료 후 사용자 판단으로 삭제/보관 결정

## 8. 세팅 문서(reference/)와의 연결점

INDEX.md에서 reference/로 걸어줄 교차 링크:

| INDEX.md 항목 | 연결 대상 (reference/) |
|---|---|
| 맵 풀 안내 | `Esports_Map_Pool` 섹션 |
| 밴픽 전략 (보완 필요) | `World_Championship_Veto_Process` 섹션 |
| 역할 분배 상위 제약 | `Weapon_Class_Roles` 섹션 |
| 옵스킬 중복 금지 | `Unique_Operator_Skills` 섹션 |

세팅 문서 자체는 분할하지 않는다 — 규칙 문서는 하나로 두는 것이 검색/참조에 낫다.

## 9. 토큰 효율 비교

| 시나리오 | 현재 | 개선 후 |
|---|---|---|
| 코칭 철학 질문 | 670줄 로드 | INDEX(80) + 철학원칙(~230) = ~310줄 |
| 특정 맵 전술 질문 | 670줄 로드 | INDEX(80) + 해당 맵(~30-60) = ~110-140줄 |
| 전사문 흡수 | 670줄 로드 + 편집 | INDEX(80) + 해당 영역 파일만 |
| 전체 구조 파악 | 670줄 스캔 | INDEX(80줄) |

## 10. 하지 않는 것 (범위 밖)

- **원칙을 파일 단위로 쪼개지 않음** — 상호 참조가 많아 응집이 나음
- **세팅 문서를 분할하지 않음** — 규칙 문서는 통합이 검색에 낫다
- **위키링크([[]]) 도입 안 함** — 이식성 최우선
- **새 내용 추가하지 않음** — 재배치만. "보완 필요"는 체크리스트로 남김
- **원본 삭제하지 않음** — 보존 후 사용자 결정
