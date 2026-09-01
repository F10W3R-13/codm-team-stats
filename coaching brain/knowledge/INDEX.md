# 🧠 코치 게임 철학 & CODM 역학 지식 기반

> **목적**: 코치의 머릿속에 있는 CODM 철학·게임 지식을 **체계화하여 외부화**한다.
> 전사문이 추가될 때마다 이 구조에 흡수되어, 코칭 파이프라인 최적화의 기반이 된다.

| 버전 | 마지막 갱신 | 기반 전사문 | 다음 업데이트 조건 |
|---|---|---|---|
| v0.6 | 2026-09-01 | 전사문 1-10 | 새 전사문 추가 시 |

---

## 📖 구조 안내

이 지식베이스는 **필요한 부분만 로드**할 수 있도록 모듈화되어 있다. 이 INDEX만 보면 전체 구조가 파악된다.

### 🧭 철학 원칙
- [코칭 철학 원칙](principles/코칭철학원칙.md) — 왜 그렇게 코칭하는가. 9개 원칙.

### 🎮 CODM 역학
- [CODM 기본 역학](mechanics/CODM기본역학.md) — TTK, 리스폰, 시야, 맵 구조
- [무기 · 옵스킬 메타](mechanics/무기옵스킬메타.md) — 선수별 무기-스타일, 옵스킬 타이밍 역학
- [공용어 사전](mechanics/공용어사전.md) — 팀 공용어 표 (Money hill, Shadow, Slay out...)

### 🗺️ 맵 / 모드 지식
**모드 일반 역학:**
- [Hardpoint](modes/Hardpoint.md) — 모드 역학 + 흔한 실수
- [Search & Destroy](modes/SearchDestroy.md)
- [Control](modes/Control.md) — 모드 역학 + Raid 공격 티켓 운영(전사문 10)

**맵별 상세:**
- [Combine](maps/Combine.md) (HP) — P1~P4 심층, cinema 진입, E-box smoke
- [Hacienda](maps/Hacienda.md) (HP) — P1 삥 vs 연막, P3 폭을 거점 안에, P4 corner 클리어 매핑
- [Takeoff](maps/Takeoff.md) (HP) — P3 top red, P4 거점 연관성·내정지, slay out 조건, AR 포지셔닝(전사문 10)
- [Summit](maps/Summit.md) (HP) — P3, P4 spawn
- [Arsenal](maps/Arsenal.md) (HP) — P2 yellow spawn
- [Standoff](maps/Standoff.md) (Control/HP) — B push 연쇄, Sparrow 제안
- [Crossroads Strike](maps/CrossroadsStrike.md) (Control) — 사이트 캡처로 스폰 탈출

### 🗣️ 팀 운영
- [팀 운영 원칙](team/팀운영.md) — 콜 시스템, 역할 분배, 갈등 관리, Promise 시스템

### 🔁 흡수 로그
- [흡수 로그](log/흡수로그.md) — 전사문 1-10에서 무엇을 학습했는가

---

## 📋 참조 문서 (공식 규칙)

> 지식이 아닌 **토너먼트 공식 세팅/규칙**은 별도 영역에 있다.

- [CODM 2026 Esports Settings](../reference/CODM_2026_Esports_Settings.md) — 맵 풀, 밴픽, 무기 제한, 옵스킬 중복 금지, 웨폰 클래스 롤, 로비 생성 가이드

**교차 참조 포인트:**
- 맵 풀 → Esports Settings의 [Esports Map Pool](../reference/CODM_2026_Esports_Settings.md#esports-map-pool) 섹션
- 밴픽 전략 (보완 필요) → [Veto Process](../reference/CODM_2026_Esports_Settings.md#world-championship-veto-process) 섹션
- 역할 분배 상위 제약 → [Weapon Class Roles](../reference/CODM_2026_Esports_Settings.md#weapon-class-roles) 섹션
- 옵스킬 중복 금지 → [Unique Operator Skills](../reference/CODM_2026_Esports_Settings.md#unique-operator-skills) 섹션

---

## 📈 확장 규칙 — 이 지식베이스를 살아있게 유지하는 법

### 언제 갱신하나
1. **새 전사문 추가 시** (자동 흡수)
   - [흡수 로그](log/흡수로그.md)에 한 줄 추가
   - 해당 내용이 철학/역학/맵 지식이면 해당 파일에 통합
2. **코치가 새 통찰 발언 시** (비전사문)
   - 해당 파일에 추가 + 출처 명시
3. **메타 변화 시** (게임 패치, 새 무기/옵스킬)
   - [무기 · 옵스킬 메타](mechanics/무기옵스킬메타.md) 업데이트
4. **새 팀 합류 시** (종목 변경 포함)
   - CODM 특화 파일(mechanics, modes, maps)을 새 종목으로 교체 또는 보관
   - [코칭 철학 원칙](principles/코칭철학원칙.md)은 유지 (종목 독립적)

### 갱신 절차
1. 전사문 읽기 → 핵심 통찰 추출
2. 해당 파일에 통합 (출처: 전사문 N)
3. [흡수 로그](log/흡수로그.md)에 한 줄 추가
4. (필요 시) `02_CODM_2026_Playbook.md`로 구체화

---

## ✅ 보완 필요 영역 (v0.2 기준)

- [x] Raid Control 상세 전술 (2026 풀) — 전사문 10으로 공격 플랜 부분 충족. 방어 상세는 보완 필요
- [x] Tunisia, Firing Range 맵별 상세 — 전사문 9로 부분 충족 (A러시 카운터·A 리테이크). Coastal, Slums, Meltdown는 여전히 보완 필요
- [ ] Kingz/Cartels 외 선수들의 무기-플레이스타일 매핑 확장
- [ ] Veto(밴픽) 전략 — [Esports Settings](../reference/CODM_2026_Esports_Settings.md#world-championship-veto-process) 기반
- [ ] Mappings 문서화 산출물 — 코치가 선수 전원 입회 하에 진행 예정
- [ ] 첫째/둘째 P3 교차 전술의 다른 맵 적용 (Combine 외)
- [ ] operator sacrifice/promise 시스템의 맵·힐별 구체 약속 문서화
- [ ] Control에서 스나이퍼=4v5 인식 문제 해결 (전사문 9에서 코치가 보류한 과제)

---

## 📦 원본 아카이브

> 이 구조는 단일 파일 `게임철학_역학지식.md` (v0.2, 670줄)에서 분할되었다.
> 원본은 작업공간 루트에 보존되어 있다: [원본 전체](../게임철학_역학지식.md)

---

*이 지식베이스는 코치의 두뇌를 확장하는 외부 메모리다. 완성본이 아니라 성장하는 생명체다.*
