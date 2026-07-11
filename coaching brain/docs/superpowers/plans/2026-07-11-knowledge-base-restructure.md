# 지식베이스 모듈화 재구성 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 670줄 단일 파일 `게임철학_역학지식.md`를 16개 모듈화된 파일로 분할하고, 세팅 문서를 `reference/`로 이동시킨다.

**Architecture:** 원본의 섹션 구조를 디렉토리 구조로 매핑. 철학 원칙은 응집(1파일), 맵 지식은 원자화(맵별 파일). 모든 파일은 INDEX.md에서 네비게이션. 순수 마크다운 링크로 상호연결.

**Tech Stack:** 마크다운 파일. Git 미사용 (git repo 아님). 검증은 원본과의 내용 대조로 수행.

**원본 위치:** `C:/Users/0616y/Downloads/Superpowers Workspace/게임철학_역학지식.md` (670줄)
**세팅 문서 위치:** `C:/Users/0616y/Downloads/Superpowers Workspace/CODM_2026_Esports_Settings.md` (486줄)

---

## Global Constraints

- 원본 파일(`게임철학_역학지식.md`)은 **삭제하지 않음** — 루트에 보존
- 세팅 문서는 **이동(move)** 하여 `reference/`로 옮김 (복사 후 원본 삭제 = 이동)
- 모든 링크는 **상대경로 마크다운 링크** `[이름](경로.md)` — 위키링크([[]]) 사용 금지
- 모든 파일의 맨 위에는 `← [INDEX](../INDEX.md)` (또는 최상위 파일의 경우 `← [INDEX](INDEX.md)`) 백링크를 둠
- 파일명은 **한글** 사용 (원본 톤 유지)
- 새 내용을 **추가하지 않음** — 재배치만. "보완 필요"는 체크리스트로 보존
- 줄번호는 구현 시점의 원본 기준 — 작업 전 원본을 다시 읽어 줄번호를 확인할 것

---

## File Structure

```
Superpowers Workspace/
├── 게임철학_역학지식.md              # 원본 — 보존 (삭제 안 함)
├── knowledge/                        # 새로 생성
│   ├── INDEX.md                      # Task 8
│   ├── principles/
│   │   └── 코칭철학원칙.md            # Task 2
│   ├── mechanics/
│   │   ├── CODM기본역학.md           # Task 3
│   │   ├── 무기옵스킬메타.md          # Task 3
│   │   └── 공용어사전.md             # Task 3
│   ├── modes/
│   │   ├── Hardpoint.md             # Task 4
│   │   ├── SearchDestroy.md         # Task 4
│   │   └── Control.md               # Task 4
│   ├── maps/
│   │   ├── Combine.md               # Task 5
│   │   ├── Hacienda.md              # Task 5
│   │   ├── Takeoff.md               # Task 5
│   │   ├── Standoff.md              # Task 5
│   │   ├── Summit.md                # Task 5
│   │   ├── Arsenal.md               # Task 5
│   │   └── CrossroadsStrike.md      # Task 5
│   ├── team/
│   │   └── 팀운영.md                 # Task 6
│   └── log/
│       └── 흡수로그.md               # Task 7
├── reference/                        # 새로 생성
│   └── CODM_2026_Esports_Settings.md # Task 1 (이동)
└── docs/superpowers/
    ├── specs/ (이미 존재)
    └── plans/ (이미 존재)
```

---

## Task 1: 디렉토리 구조 생성 + 세팅 문서 이동

**Files:**
- Create: `knowledge/` 및 하위 디렉토리 6개 (`principles/`, `mechanics/`, `modes/`, `maps/`, `team/`, `log/`)
- Create: `reference/`
- Move: `CODM_2026_Esports_Settings.md` → `reference/CODM_2026_Esports_Settings.md`

- [ ] **Step 1: 디렉토리 생성**

Run:
```bash
cd "C:/Users/0616y/Downloads/Superpowers Workspace"
mkdir -p knowledge/principles knowledge/mechanics knowledge/modes knowledge/maps knowledge/team knowledge/log reference
```

- [ ] **Step 2: 디렉토리 확인**

Run: `ls -d knowledge/*/ reference/`
Expected: `knowledge/log/  knowledge/maps/  knowledge/mechanics/  knowledge/modes/  knowledge/principles/  knowledge/team/  reference/`

- [ ] **Step 3: 세팅 문서 이동 (move)**

Run:
```bash
mv "CODM_2026_Esports_Settings.md" "reference/CODM_2026_Esports_Settings.md"
```

- [ ] **Step 4: 이동 확인**

Run: `ls reference/` → Expected: `CODM_2026_Esports_Settings.md`
Run: `ls *.md` → Expected: `게임철학_역학지식.md` (세팅 문서 없음)

---

## Task 2: principles/코칭철학원칙.md — 9개 원칙

**Files:**
- Create: `knowledge/principles/코칭철학원칙.md`

**Source:** 원본 L25-235 (Section 1 전체: 원칙 1-9)

**Transformations:**
1. 맨 위에 백링크 헤더 추가
2. 원본의 `# 🧭 Section 1: 코칭 철학 원칙` 헤더를 파일 타이틀로 변경
3. 원칙 간 상호참조 텍스트(예: "원칙 7과 연결")를 마크다운 링크로 변환 — 단, 같은 파일 내 앵커이므로 `[원칙 7](#원칙-7--이기러-플레이해라-지지-않으러가-아니다-전사문-56-신규)` 형태. 앵커가 복잡하면 `(#원칙-7)` 형태로 간단히 작성 (GitHub 호환성보다 가독성 우선)
4. 원칙 3(slay out), 원칙 9(잠재 가치) 등에서 맵/모드 관련 내용은 그대로 유지 — 해당 맵 파일로 링크 걸지 않음 (같은 파일 내에서 읽는 게 자연스러움)

- [ ] **Step 1: 파일 생성**

원본 L25-235를 읽어 아래 템플릿에 맞춰 파일 작성:

```markdown
← [INDEX](../INDEX.md)

# 🧭 코칭 철학 원칙

> 코치가 전사문에서 **반복적으로 강조한 핵심 신념**. CODM에 국한되지 않지만 CODM 역학에 기반한다.
>
> v0.2 기준 **9개 원칙**. 원칙 7-9는 전사문 5-6에서 처음 등장한 심화 원칙.

---

(원본 L31-235의 원칙 1-9 내용을 그대로 복사. 단, 원칙 번호 헤더는 ## 유지)

원칙 7, 8, 9 사이의 `---` 구분선 유지 (원본 L159, L186, L211).
```

- [ ] **Step 2: 내용 검증**

Run: `wc -l "knowledge/principles/코칭철학원칙.md"`
Expected: 약 210줄 (원본 205줄 + 헤더/백링크 5줄)

원본 L25-235와 비교하여 9개 원칙이 모두 포함되어 있는지 확인.

- [ ] **Step 3: 원칙 개수 확인**

Run: `grep -c "^## 원칙" "knowledge/principles/코칭철학원칙.md"`
Expected: `9`

---

## Task 3: mechanics/ — 3개 파일

**Files:**
- Create: `knowledge/mechanics/CODM기본역학.md` — Source: 원본 L237-262 (Section 2.1)
- Create: `knowledge/mechanics/무기옵스킬메타.md` — Source: 원본 L264-318 (Section 2.2)
- Create: `knowledge/mechanics/공용어사전.md` — Source: 원본 L320-346 (Section 2.3)

- [ ] **Step 1: CODM기본역학.md 생성**

```markdown
← [INDEX](../INDEX.md)

# 🎮 CODM 기본 역학

> CODM이라는 게임이 **왜** 그렇게 작동하는가. 원리 이해가 전술의 기반.

---

(원본 L241-262의 내용: TTK, 리스폰, 시야 공유, 맵 구조 — 그대로 복사)
```

- [ ] **Step 2: 무기옵스킬메타.md 생성**

```markdown
← [INDEX](../INDEX.md)

# 무기 · 옵스킬 메타와 플레이 스타일

> **코치의 핵심 통찰**: "OBJ가 낮다"고만 안 하고, **왜 낮은지를 무기/옵스킬 메타로 분석**. 이게 코칭의 깊이.

---

(원본 L268-318의 내용:
- 통찰 표 (선수별 메타 변화)
- 옵스킬 타이밍 역학 (See then pop, War Machine, Equalizer)
- 왜 이 통찰이 강력한가
- 2026 메타 요약 — 그대로 복사)
```

주의: 선수별 표(L270-277)에서 맵이나 모드로의 링크는 걸지 않음 — 이 파일은 선수-무기 관계가 중심.

- [ ] **Step 3: 공용어사전.md 생성**

```markdown
← [INDEX](../INDEX.md)

# 🗣️ CODM 팀 공용어 사전

> 코치가 사용하거나 가르치려는 개념들. **표준화하면 VOD·실시간 코칭의 공용어**가 된다.

---

(원본 L323-346의 공용어 표를 그대로 복사. 단, 출처 열의 "전사문 N"은 그대로 유지)
```

- [ ] **Step 4: 3개 파일 검증**

Run:
```bash
grep -c "TTK" "knowledge/mechanics/CODM기본역학.md"           # Expected: 2+
grep -c "See, then pop" "knowledge/mechanics/무기옵스킬메타.md"  # Expected: 1
grep -c "Money hill" "knowledge/mechanics/공용어사전.md"       # Expected: 1
```

---

## Task 4: modes/ — 3개 파일

**Files:**
- Create: `knowledge/modes/Hardpoint.md` — Source: 원본 L356-378
- Create: `knowledge/modes/SearchDestroy.md` — Source: 원본 L379-394 + L474-476 (Raid SnD 메모)
- Create: `knowledge/modes/Control.md` — Source: 원본 L395-426 + L490-491 (Raid Control 메모)

- [ ] **Step 1: Hardpoint.md 생성**

```markdown
← [INDEX](../INDEX.md)

# Hardpoint

> 고정된 힐 포인트를 점령하여 시간을 쌓는 모드. 250점 선착.

---

(원본 L356-378의 내용: 목표, 코치가 강조한 핵심, 흔한 실수 — 그대로 복사)

## 맵별 상세

> 각 맵의 구체적인 힐별 전술은 맵 파일 참조:
> - [Combine](../maps/Combine.md)
> - [Hacienda](../maps/Hacienda.md)
> - [Takeoff](../maps/Takeoff.md)
> - [Summit](../maps/Summit.md)
> - [Arsenal](../maps/Arsenal.md)
> - [Standoff](../maps/Standoff.md)
```

- [ ] **Step 2: SearchDestroy.md 생성**

```markdown
← [INDEX](../INDEX.md)

# Search & Destroy

> bomb plant/defend. 라운드제, 리스폰 없음. CODM 모드 중 가장 언어 의존적.

---

(원본 L379-394의 내용: 목표, 코치가 강조한 핵심, 흔한 실수 — 그대로 복사)

## 맵별 메모

### Raid
- 소통 on point였음 (긍정 사례) — 전사문 3
- Sparrow 사용 가능(팀원 의견) — 코치는 "Raid SnD sparrow는 상상 안 됨" — [Standoff B](../maps/Standoff.md) 한정으로 제안 유지

> ⚠️ Tunisia, Firing Range, Coastal, Slums, Meltdown: 보완 필요 (전사문에 상세 없음)
```

- [ ] **Step 3: Control.md 생성**

```markdown
← [INDEX](../INDEX.md)

# Control

> 사이트 캡처/방어. 티켓(생명수)제. 2026 풀: [Raid](#raid), [Standoff](../maps/Standoff.md), [Crossroads Strike](../maps/CrossroadsStrike.md).

---

(원본 L395-426의 내용: 목표, 코치가 강조한 핵심, War Machine in Control, Standoff B push 상세, Crossroads Strike, 흔한 실수 — 그대로 복사)

주의: 원본 L409-417의 Standoff B push 상세와 L418-420의 Crossroads Strike 내용은 Control 모드 일반 역학의 일부이므로 이 파일에 유지. 별도 맵 파일(Standoff.md)에는 링크로 참조만 걸고 중복 기재하지 않음.

## 맵별 메모

### Raid
- 2026 풀. 상세 전술: 전사문에서 거의 다뤄지지 않음. ⚠️ 보완 필요.
```

- [ ] **Step 4: 3개 파일 검증**

Run:
```bash
grep -c "250점" "knowledge/modes/Hardpoint.md"               # Expected: 1
grep -c "IGL" "knowledge/modes/SearchDestroy.md"             # Expected: 2+
grep -c "War Machine" "knowledge/modes/Control.md"           # Expected: 3+
```

---

## Task 5: maps/ — 7개 파일

**Files:**
- Create: `knowledge/maps/Combine.md` — Source: 원본 L429-437 (HP) + L432 cinema/E-box 등
- Create: `knowledge/maps/Hacienda.md` — Source: 원본 L439-443 (HP)
- Create: `knowledge/maps/Takeoff.md` — Source: 원본 L445-449 (HP)
- Create: `knowledge/maps/Standoff.md` — Source: 원본 L457-461 (HP) + Control B push 참조
- Create: `knowledge/maps/Summit.md` — Source: 원본 L451-455 (HP)
- Create: `knowledge/maps/Arsenal.md` — Source: 원본 L463-467 (HP)
- Create: `knowledge/maps/CrossroadsStrike.md` — Source: 원본 L487-488 (Control)

**공통 템플릿** (모든 맵 파일에 적용):

```markdown
← [INDEX](../INDEX.md)

# {맵이름}

> 맵 풀: {해당 모드 링크}
> 관련 원칙: [코칭 철학 원칙](../principles/코칭철학원칙.md)

---

## Hardpoint

### P1
(내용)

### P2
(내용)

...
```

- [ ] **Step 1: Combine.md 생성**

원본 L429-437의 Combine 표를 파일로 변환. 표 형태를 그대로 유지하되, 각 P별 내용은 표 셀에서 줄바꿈 헤딩으로 풀어서 가독성 향상시켜도 됨 (선택사항 — 표 유지도 ok).

```markdown
← [INDEX](../INDEX.md)

# Combine

> 맵 풀: [Hardpoint](../modes/Hardpoint.md)
> 관련 원칙: [코칭 철학 원칙](../principles/코칭철학원칙.md)

---

## Hardpoint

(원본 L432-437의 Combine 표 내용을 그대로 복사. P1, P2, P3, P3(first vs second), P3(2nd half), P4 행 포함)
```

- [ ] **Step 2: Hacienda.md 생성**

```markdown
← [INDEX](../INDEX.md)

# Hacienda

> 맵 풀: [Hardpoint](../modes/Hardpoint.md)
> 관련 원칙: [코칭 철학 원칙](../principles/코칭철학원칙.md)

---

## Hardpoint

(원본 L442-443의 Hacienda 표 내용: P3, P4 행 — 그대로 복사)
```

- [ ] **Step 3: Takeoff.md 생성**

```markdown
← [INDEX](../INDEX.md)

# Takeoff

> 맵 풀: [Hardpoint](../modes/Hardpoint.md)
> 관련 원칙: [코칭 철학 원칙](../principles/코칭철학원칙.md)

---

## Hardpoint

(원본 L448-449의 Takeoff 표 내용: P3, P4 행 — 그대로 복사)
```

- [ ] **Step 4: Standoff.md 생성**

Standoff는 HP와 Control 두 모드에서 언급되므로 두 섹션을 모두 포함.

```markdown
← [INDEX](../INDEX.md)

# Standoff

> 맵 풀: [Control](../modes/Control.md) (B push 핵심 전술)
> 관련 원칙: [코칭 철학 원칙](../principles/코칭철학원칙.md)

---

## Control

Standoff B push 상세 전술은 [Control 모드 파일](../modes/Control.md#standoff-control--b-push-상세)에서 다룬다.

요약:
- B push가 핵심 (A push는 fine)
- statue → broken → top granny 연쇄 통제
- **Sparrow 제안**(B 클리어용, death machine 대신) — 코치 제안, Kingz 반발 예상

## Hardpoint

(원본 L460-461의 Standoff HP 행: P3/P4 언급만, 상세 미제공 — 보완 필요 표시)
> ⚠️ P3/P4 상세 보완 필요 (전사문 3 언급만 존재)
```

- [ ] **Step 5: Summit.md 생성**

```markdown
← [INDEX](../INDEX.md)

# Summit

> 맵 풀: [Hardpoint](../modes/Hardpoint.md)
> 관련 원칙: [코칭 철학 원칙](../principles/코칭철학원칙.md)

---

## Hardpoint

(원본 L453-455의 Summit 표 내용: P3, P4 행 — 그대로 복사)
```

- [ ] **Step 6: Arsenal.md 생성**

```markdown
← [INDEX](../INDEX.md)

# Arsenal

> 맵 풀: [Hardpoint](../modes/Hardpoint.md)
> 관련 원칙: [코칭 철학 원칙](../principles/코칭철학원칙.md)

---

## Hardpoint

(원본 L466-467의 Arsenal 표 내용: 전반, P2 행 — 그대로 복사)
```

- [ ] **Step 7: CrossroadsStrike.md 생성**

```markdown
← [INDEX](../INDEX.md)

# Crossroads Strike

> 맵 풀: [Control](../modes/Control.md)
> 관련 원칙: [코칭 철학 원칙](../principles/코칭철학원칙.md) — 특히 [원칙 9 잠재 가치](../principles/코칭철학원칙.md)

---

## Control

(원본 L487-488의 Crossroads Strike 내용 — 그대로 복사)

우리가 스폰에서 고전 + 1-2명이 적 진역 roaming → 그 선수의 잡은 **사이트를 캡처**해야 → 캡처하면 스폰 공격 중인 적이 뒤를 봐야 함 → 우리가 스폰에서 탈출 → 거기서 시작
```

- [ ] **Step 8: 7개 파일 검증**

Run:
```bash
ls knowledge/maps/
```
Expected: `Arsenal.md  Combine.md  CrossroadsStrike.md  Hacienda.md  Standoff.md  Summit.md  Takeoff.md`

각 파일에 `← [INDEX]` 백링크와 `## Hardpoint` 또는 `## Control` 섹션이 있는지 확인:
```bash
for f in knowledge/maps/*.md; do echo "=== $f ==="; head -3 "$f"; grep "^## " "$f"; done
```

---

## Task 6: team/팀운영.md

**Files:**
- Create: `knowledge/team/팀운영.md`

**Source:** 원본 L497-591 (Section 4 전체: 콜 시스템, 역할 분배, 갈등 관리)

- [ ] **Step 1: 파일 생성**

```markdown
← [INDEX](../INDEX.md)

# 🗣️ 팀 운영 원칙

> 인게임 소통·역할 분배 원칙. Donnie 4Pillar의 CODM 인게임 적용.

---

(원본 L497-591의 내용을 그대로 복사:
- 4.1 콜 시스템 원칙 (상태 공유, 진입 콜, Promise 시스템, 앵커링 콜, Call-out 양면성)
- 4.2 역할 분배 원칙 (HP 역할, SnD 역할, 역할 유연성, 역할 셔플)
- 4.3 갈등 관리 원칙 (Kingz↔Shisui, P1 spawn push 갈등, CEO 직소통, 언어/기술 장벽))

맨 아래 `---` 구분선 유지.)
```

- [ ] **Step 2: 검증**

Run:
```bash
grep -c "Promise" "knowledge/team/팀운영.md"     # Expected: 3+
grep -c "Cartels" "knowledge/team/팀운영.md"     # Expected: 5+
```

---

## Task 7: log/흡수로그.md

**Files:**
- Create: `knowledge/log/흡수로그.md`

**Source:** 원본 L595-633 (Section 5 전체: 전사문 1-6 흡수 기록)

- [ ] **Step 1: 파일 생성**

```markdown
← [INDEX](../INDEX.md)

# 🔁 흡수 로그

> 각 전사문에서 **무엇을 학습했는가**. 새 전사문 추가 시 이곳에 한 줄씩 기록.

---

(원본 L599-633의 내용을 그대로 복사:
- 전사문 1 — Hardpoint VOD (Combine, 대 UD)
- 전사문 2 — Shisui 1-on-1 + 팀 회의
- 전사문 3 — Hardpoint 회전/전술 (Combine P3)
- 전사문 4 — Hardpoint (대 UD, Summit)
- 전사문 5 — 스크림 복기
- 전사문 6 — 스크림 복기)
```

- [ ] **Step 2: 검증**

Run:
```bash
grep -c "^## 전사문" "knowledge/log/흡수로그.md"   # Expected: 6
```

---

## Task 8: INDEX.md — 입구 파일

**Files:**
- Create: `knowledge/INDEX.md`

**Source:** 원본 L1-21 (헤더, 목적, 버전, 읽는법) + L637-668 (확장 규칙, 보완 필요)

**주의:** 이 태스크는 모든 다른 파일이 존재한 후에 실행해야 함 (링크 대상이 있어야 하므로).

- [ ] **Step 1: INDEX.md 생성**

```markdown
# 🧠 코치 게임 철학 & CODM 역학 지식 기반

> **목적**: 코치의 머릿속에 있는 CODM 철학·게임 지식을 **체계화하여 외부화**한다.
> 전사문이 추가될 때마다 이 구조에 흡수되어, 코칭 파이프라인 최적화의 기반이 된다.

| 버전 | 마지막 갱신 | 기반 전사문 | 다음 업데이트 조건 |
|---|---|---|---|
| v0.2 | 2026-07-11 | 전사문 1-6 | 새 전사문 추가 시 |

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
- [Control](modes/Control.md)

**맵별 상세:**
- [Combine](maps/Combine.md) (HP) — P1~P4 심층, cinema 진입, E-box smoke
- [Hacienda](maps/Hacienda.md) (HP) — P3, P4 corner 클리어 매핑
- [Takeoff](maps/Takeoff.md) (HP) — P3 top red, P4 slay out 조건
- [Summit](maps/Summit.md) (HP) — P3, P4 spawn
- [Arsenal](maps/Arsenal.md) (HP) — P2 yellow spawn
- [Standoff](maps/Standoff.md) (Control/HP) — B push 연쇄, Sparrow 제안
- [Crossroads Strike](maps/CrossroadsStrike.md) (Control) — 사이트 캡처로 스폰 탈출

### 🗣️ 팀 운영
- [팀 운영 원칙](team/팀운영.md) — 콜 시스템, 역할 분배, 갈등 관리, Promise 시스템

### 🔁 흡수 로그
- [흡수 로그](log/흡수로그.md) — 전사문 1-6에서 무엇을 학습했는가

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

- [ ] Raid Control 상세 전술 (2026 풀)
- [ ] Tunisia, Firing Range, Coastal, Slums, Meltdown 맵별 상세 (SnD 풀)
- [ ] Kingz/Cartels 외 선수들의 무기-플레이스타일 매핑 확장
- [ ] Veto(밴픽) 전략 — [Esports Settings](../reference/CODM_2026_Esports_Settings.md#world-championship-veto-process) 기반
- [ ] Mappings 문서화 산출물 — 코치가 선수 전원 입회 하에 진행 예정
- [ ] 첫째/둘째 P3 교차 전술의 다른 맵 적용 (Combine 외)
- [ ] operator sacrifice/promise 시스템의 맵·힐별 구체 약속 문서화

---

## 📦 원본 아카이브

> 이 구조는 단일 파일 `게임철학_역학지식.md` (v0.2, 670줄)에서 분할되었다.
> 원본은 작업공간 루트에 보존되어 있다: [원본 전체](../게임철학_역학지식.md)

---

*이 지식베이스는 코치의 두뇌를 확장하는 외부 메모리다. 완성본이 아니라 성장하는 생명체다.*
```

- [ ] **Step 2: 링크 무결성 검증**

INDEX.md에 적힌 모든 링크가 실제 파일을 가리키는지 확인:

```bash
cd "C:/Users/0616y/Downloads/Superpowers Workspace/knowledge"
for target in \
  "principles/코칭철학원칙.md" \
  "mechanics/CODM기본역학.md" \
  "mechanics/무기옵스킬메타.md" \
  "mechanics/공용어사전.md" \
  "modes/Hardpoint.md" \
  "modes/SearchDestroy.md" \
  "modes/Control.md" \
  "maps/Combine.md" \
  "maps/Hacienda.md" \
  "maps/Takeoff.md" \
  "maps/Summit.md" \
  "maps/Arsenal.md" \
  "maps/Standoff.md" \
  "maps/CrossroadsStrike.md" \
  "team/팀운영.md" \
  "log/흡수로그.md" \
  "../reference/CODM_2026_Esports_Settings.md"; do
  if [ -f "$target" ]; then echo "✅ $target"; else echo "❌ MISSING: $target"; fi
done
```

Expected: 모두 ✅. ❌가 하나라도 있으면 해당 Task로 돌아가 파일 생성.

- [ ] **Step 3: 줄 수 확인**

Run: `wc -l INDEX.md`
Expected: 100줄 내외 (목표: 원본 670줄 → 입구 100줄 이하)

---

## Task 9: 전체 검증 + 백링크 정합성

**목표:** 분할 완료 후 원본 대비 누락/중복이 없는지 최종 확인.

- [ ] **Step 1: 파일 개수 확인**

```bash
find knowledge/ -name "*.md" | wc -l
```
Expected: `17` (INDEX 1 + principles 1 + mechanics 3 + modes 3 + maps 7 + team 1 + log 1)

- [ ] **Step 2: 백링크 정합성**

모든 파일의 첫 줄에 `← [INDEX](../INDEX.md)` 또는 `← [INDEX](INDEX.md)`가 있는지 확인:

```bash
find knowledge/ -name "*.md" -exec sh -c 'echo "=== {} ===" && head -1 "{}"' \;
```

Expected: 모든 파일 첫 줄이 `← [INDEX](...)` 형태.

- [ ] **Step 3: 원본 섹션 커버리지 수동 체크**

원본의 5개 섹션이 모두 새 구조에 매핑되었는지 확인:

| 원본 섹션 | 줄 범위 | 새 위치 | 확인 |
|---|---|---|---|
| 헤더/메타/확장규칙 | L1-21, L637-668 | INDEX.md | ☐ |
| Section 1 (9 원칙) | L25-235 | principles/코칭철학원칙.md | ☐ |
| Section 2.1 (기본 역학) | L237-262 | mechanics/CODM기본역학.md | ☐ |
| Section 2.2 (무기 메타) | L264-318 | mechanics/무기옵스킬메타.md | ☐ |
| Section 2.3 (공용어) | L320-346 | mechanics/공용어사전.md | ☐ |
| Section 3.1 (모드 역학) | L349-426 | modes/*.md | ☐ |
| Section 3.2-3.4 (맵별) | L427-493 | maps/*.md | ☐ |
| Section 4 (팀 운영) | L497-591 | team/팀운영.md | ☐ |
| Section 5 (흡수 로그) | L595-633 | log/흡수로그.md | ☐ |

- [ ] **Step 4: reference/ 이동 확인**

```bash
ls "reference/CODM_2026_Esports_Settings.md"
```
Expected: 파일 존재.

```bash
ls "CODM_2026_Esports_Settings.md" 2>/dev/null
```
Expected: 에러 (원본 위치에 없음 = 이동 완료).

- [ ] **Step 5: 원본 보존 확인**

```bash
ls "게임철학_역학지식.md"
```
Expected: 파일 존재 (삭제 안 됨).

- [ ] **Step 6: 토큰 효율 샘플 체크**

INDEX.md만 읽었을 때 전체 구조가 파악되는지, 그리고 INDEX(약100줄) + 특정 파일(예: maps/Combine.md)을 읽으면 Combine 전술을 다룰 수 있는지 확인.

```bash
wc -l knowledge/INDEX.md knowledge/maps/Combine.md
```
Expected: 합계 150줄 이내 (원본 670줄 대비 77%+ 절감).
