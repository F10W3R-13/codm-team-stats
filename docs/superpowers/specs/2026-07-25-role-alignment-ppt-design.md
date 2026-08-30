# Role Alignment & Tactical Model — PPT Design

**Date**: 2026-07-25
**Output**: `coaching brain/역할정합서_PPT.pptx`
**Script**: `coaching brain/make_pptx_roles.py` (새 파일, 기존 `make_pptx.py` 복사 후 확장)
**Audience**: 팀 전체 미팅, 당신이 화면 공유하며 발표 (발표용)
**Language**: English (기존 Post-Loss Speech PPT 톤 일관)
**Slide count**: ~30 slides, 9 sections

---

## 1. 목적 (Purpose)

제공된 텍스트(베테랑 3인의 콜 책임 분배, SMG/AR 라인업 진단과 협업 모델)를 팀 전체에게 발표하기 위한 **역할 정합서 + 전술 다이어그램** 덱. 발표자(코치)가 한국어로 말로 채우는 것을 전제로, 슬라이드 자체는 키워드/다이어그램 중심으로 간결하게.

**3가지 핵심 메시지**:
1. **콜 책임 구조**: Cartels(공격/거점압박), Kings(거시/여유시간 dictate), Shisui(주도적 콜 기대 X, 플레이메이커/클러치 수단)
2. **SMG 듀오 협업**: unravel + Shisui는 시너지도 있지만 템포 gap으로 자주 벌어짐 → Cartels가 중간지점이 아니라 **필요한 쪽을 돕는다** (리스크 ↓, 리턴 ↑)
3. **AR 듀오 협업**: Maozyn(selfless AR / 워머신 함정 주의) + Kings(베테랑 허리 / 콜아웃 갭 공개 코칭) — OBJ 씬에서 단독행동 금지, 여유시간에만 Kings dictate

---

## 2. 디자인 시스템 (기존 Astryx neutral 재사용)

### 색 팔레트 (기존 make_pptx.py 그대로)
- `BG` `#FAFAFA`, `SURFACE` `#FFFFFF`, `TEXT` `#262626`, `TEXT_2` `#535353`, `MUTED` `#8A8A8A`
- `BORDER` `#E5E5E5`, `BORDER_STRONG` `#C8C8C8`
- `ACCENT` `#262626` (검정, UI 액센트)
- `HP` `#F97316` (주황, SMG 라인업 배지)
- `SND` `#8B5CF6` (보라, AR 라인업 배지)
- `DANGER` `#DC2626` (추가 — 벌어짐/gap 표현용, `--danger` 토큰 대응)
- `SUCCESS` `#16A34A` (추가 — 좋은 사인/positive 표현용, `--success` 토큰 대응)

### 타이포그래피
- Pretendard 폰트 유지 (Calibri fallback)
- 기존 계층: title 80pt / statement 54pt / section title 44pt / quote 38pt / bullets 22pt / sub 15pt / kicker 12pt

### 다이어그램 관계 화살표 (새로 추가하는 시각 언어)
- **Cartels 콜 (공격/압박/지원)**: `ACCENT` 검정 **실선 화살표**, 두께 2.5pt
- **Kings 콜 (거시/dictate)**: `MUTED` 회색 **점선 화살표**, 두께 2pt
- **벌어짐/갭 (문제)**: `DANGER` 빨강 **점선**, 두께 1.5pt
- **라인업 배지색 (노드 테두리)**: SMG = `HP` 주황, AR = `SND` 보라

---

## 3. 새로운 헬퍼 함수 (기존 헬퍼 위에 추가)

### `_node(slide, cx, cy, w, h, name, role, lineup)`
선수 노드 박스. 중앙(cx, cy) 기준, 너비/높이 지정.
- 테두리: 라인업 배지색 (HP/SND), 두께 2pt
- 채우기: SURFACE
- 내부 텍스트: 이름(굵게 18pt) + 역할 한 줄(13pt TEXT_2)
- 좌측에 얇은 라인업 색 띠(4pt 너비)로 시각적 구분 강화

### `_arrow(slide, x1, y1, x2, y2, color, weight, dash=False, label="")`
관계 화살표. PPTX connector 사용.
- `dash=False` → 실선 (Cartels용)
- `dash=True` → 점선 (Kings/gap용)
- 끝에 화살촉
- 중간에 라벨 텍스트 박스 (선택)

### `_gap_arrow(slide, x1, y1, x2, y2, label="")`
벌어짐 표현专用. `DANGER` 점선 + 라벨.

### `slide_roster_diagram(lineup, nodes, arrows, title, kicker, note="")`
노드+화살표로 구성된 다이어그램 슬라이드.
- `lineup`: "SMG" 또는 "AR" (배지색 결정)
- `nodes`: list of (cx_emu, cy_emu, name, role)
- `arrows`: list of (x1, y1, x2, y2, type, label) — type: "cartels" / "kings" / "gap"
- 상단 title/kicker, 하단 note(설명 한 줄)

### `slide_rolecard(name, lineup, role_one_liner, responsibilities, identity="")`
선수별 1장 요약 카드.
- 좌측: 큰 이름(60pt) + 라인업 배지
- 우측: 역할 한 줄(28pt 굵게) + 책임 목록(3-4개, 18pt)
- 하단: identity(성향 한 줄, 이탤릭) — 있으면

---

## 4. 덱 구조 (총 30장)

### 타이틀 (1장)
- `slide_title`: "ROLE ALIGNMENT & TACTICAL MODEL"
- 서브: "How the veteran core runs the team — and what changes today."
- "Team Briefing · English"

### Section 01 — The call structure (3장)
**Divider**: `01 · The call structure` / "Three veterans, three different jobs."
- **slide_bullets**: 콜 3역할
  - Cartels — "What the frontline wants" (SMG press lead, 거점 압박 주도)
  - Kings — "What our movement wants" (여유시간 활용, 거시적 dictate)
  - Shisui — "Playmaker & clutch tool, not a caller" (주도적 콜 기대 X, 명확한 이유로)
- **slide_quote**: "Not every veteran has to call. The wrong veteran calling is worse than no call." attribution: "How we use experience"

### Section 02 — SMG lineup: diagnosis (4장)
**Divider**: `02 · SMG lineup` / "Two elite gunfighters — and where they drift apart."
- **slide_rolecard** unravel: 
  - 라인업: SMG
  - 역할 한 줄: "Momentum builder, one-vs-many gunskill"
  - 책임: Strong 1vX · Reactive aim · Tempo-stealer
  - identity: "Wants to be one step ahead — that's why capture kills are high"
- **slide_bullets** unravel 진단:
  - Strength: 강한 일대다 건스킬, 반응속도, 좋은 모멘텀 빌더
  - Risk: OVERPUSH. 셋업 쉽게 포기하고 추가 밸류 찾음
  - Aggression: 상대 템포 빼려고 one step ahead → 높은 거점 킬
- **slide_rolecard** Shisui:
  - 라인업: SMG
  - 역할 한 줄: "Main SMG, clutch & 1v1"
  - 책임: Clutch · Face-to-face gunfight · High-pressure reliance
  - identity: "Gets lost when there's free space — pulls himself into the hill"
- **slide_bullets** Shisui 진단:
  - Strength: 우수한 클러치, 면대면 건파이트, 빡빡한 상황에서 의지할 메인 SMG
  - Risk: 여유공간 있을 때 길 잃음 → 본인을 거점 안으로 불러들임 → 높은 obj 타임
- **slide_bullets** 듀오 dynamics:
  - "Good SMG duo — but they drift apart"
  - 살아있을 때든, 리스폰 미스매치 때든 거리가 벌어짐

### Section 03 — SMG duo diagram (1장)
**`slide_roster_diagram`** SMG:
- 노드: 
  - unravel (좌상, "Tempo stealer / 1vX")
  - Shisui (우상, "Clutch / Main SMG")
  - Cartels (하단 중앙, "Veteran SMG / Calibrator")
- 화살표:
  - unravel ↔ Shisui: **gap** 빨강 점선 "Tempo gap — drift apart"
  - Cartels → unravel: **cartels** 검정 실선 "Support this side"
  - Cartels → Shisui: **cartels** 검정 실선 "Support this side"
  - (선택) unravel → Shisui: 회색 점선 "Synergy (when aligned)"
- note 하단: "Cartels doesn't pull them to a midpoint. He picks the side that needs him."

### Section 04 — Cartels' role on SMG (3장)
**Divider**: `04 · Cartels' job` / "Don't average them out. Reinforce the side that needs it."
- **slide_quote**: "Their gunskill is real. The job isn't to slow them down — it's to cut the risk out of their high-risk, high-return plays."
- **slide_bullets** what to do:
  - Don't: 중간지점으로 끌어당기기 (둘 다 희생)
  - Do: 네 도움이 필요한 쪽을 돕는다
  - Result: 프런트라인 단단해짐 → 두 SMG의 risk를 줄이고 return 극대화 → 그들의 플레이메이킹 잠재력을 열어둔다
- **slide_statement**: "Maximize their return. Cut their risk." (kicker: "That's the veteran SMG job")

### Section 05 — AR lineup: diagnosis (4장)
**Divider**: `05 · AR lineup` / "Selfless by default — with one trap to avoid."
- **slide_rolecard** Maozyn:
  - 라인업: AR
  - 역할 한 줄: "Selfless AR (except P1)"
  - 책임: Hill-close · Sacrifices body · Flex AR gunfights
  - identity: "Intuitive player — overthinking is the enemy"
- **slide_bullets** Maozyn 진단 + 워머신 함정:
  - 기본: P1 제외 hill에서 selfless, 거점과 가깝고 과감히 몸을 던짐
  - **함정**: 워머신만 쓰면 보이지 않는 위치에서 스나이프 시도 → 포지션 붕괴 → 팀은 그대로인데 본인만 오퍼레이터 버튼 → 플랭크에 죽고 뒤에서 맞음
  - **사인 (positive)**: 퓨리파이어처럼 쓰라는 주문 → 현재 잘 지키고 있음 → 계속하길 바람
  - Why mention again: reasoning을 알아야 게임 내에서도 응용 가능
- **slide_rolecard** Kings:
  - 라인업: AR
  - 역할 한 줄: "Veteran spine — when the calls are on"
  - 책임: Mid-game anchor · Damage positions · Dictate in downtime
  - identity: "Call consistency is the gap — not skill"
- **slide_bullets** Kings 진단 (공개 코칭):
  - Good: 베테랑, 컨디션 좋을 때 확실한 허리
  - **The problem**: 콜아웃의 갭이 크다 (이유 불문)
  - = Point Major 중간 서브아웃의 이유
  - Note: exile도 루키 + 팔로워 성향이라 근본 해결은 아니었음

### Section 06 — AR duo diagram (1장)
**`slide_roster_diagram`** AR:
- 노드:
  - Maozyn (좌, "Hill-close / Selfless AR")
  - Kings (우, "Spine / Dictate in downtime")
- 화살표:
  - Kings → Maozyn: **kings** 회색 점선 "Help him fight clean — lift the overthinking"
  - Maozyn → Kings: (시각적 균형용) "Hill pressure anchor"
  - (강조) 두 노드를 감싸는 큰 빨강 점선 박스 + 라벨 "Stay together in OBJ fights"
- note 하단: "You can split in rotation. Never split when the OBJ fight starts."

### Section 07 — AR in OBJ fights (2장)
**Divider**: `07 · AR cooperation in OBJ fights` / "Hacienda P4, Takeoff P3 — solo AR play doesn't help."
- **slide_bullets** rules:
  - Don't: OBJ 싸움 중 AR 단독행동 (Hacienda P4, Takeoff P3 등)
  - Do: Cartels 또는 Jason 등 shoutout call 좋은 SMG의 콜에 거시적 움직임 맞추기
  - Do (미시): Maozyn 돕기 — 그가 직감적으로 움직일 수 있게 overthinking 부담을 줄이고, flex AR로서 필요한 건파이트에 집중하게
  - Why: 중요 순간에마저 떨어져 있으면 "내가 죽으면 SMG 도와줄 AR이 없잖아?" 생각 → Maozyn 헷갈림

### Section 08 — Downtime dictate (3장)
**Divider**: `08 · Use your downtime` / "Rotation phase, team wipe — that's your window."
- **slide_statement**: "You're not the IGL. You're the IGL for 15 seconds at a time." (kicker: "Kings — when to take the wheel")
- **slide_bullets** when & what:
  - When: 로테이션 phase, team wipe (우리가 다 잡았든 다 따였든) — 순간적 시간 여유
  - What: AR Marks로서 intense 건파이트가 없는 그 순간, 아군 움직임 dictate
  - Not: 매번 IGL이 되라는 게 아님 — 이 순간에만 잡으면 됨
- **slide_statement**: "What's the read? → We map it out together." (kicker: "The dictate criteria come from mapping — not improv")

### Section 09 — Roster summary + closing (4장)
**Divider**: `09 · One line each` / "If you remember nothing else."
- **slide_bullets** 5인 요약 (한 줄씩):
  - **Cartels (SMG, veteran)** — "Support the side that needs you. Don't average them."
  - **Kings (AR, veteran)** — "Use downtime to dictate. Close the call-consistency gap."
  - **unravel (SMG)** — "Your job is the return. The team cuts the risk for you."
  - **Shisui (SMG)** — "Be the clutch tool. We won't ask you to call."
  - **Maozyn (AR)** — "Stay intuitive. Furypiercer, not Operator. Don't think alone in OBJ."
- **slide_closing**: "Run the system." / "The veterans carry the calls. The gunfighters carry the rounds."
- (선택) 아젠다 안내 슬라이드 1장: "Next session: mapping workshop — downtime dictate scenarios"

---

## 5. 다이어그램 디테일 명세

### SMG 다이어그램 (Section 03)
```
       unravel ──────gap────── Shisui
       (Tempo)   ↑ drift       (Clutch)
            \                  /
             \   cartels ──→  /
              \  (support)   /
               \             /
                \           /
                 Cartels
              (Calibrator)
```
- unravel 노드: 좌측 상단 (cx=4.0", cy=2.3"), 너비 2.6" × 높이 1.3"
- Shisui 노드: 우측 상단 (cx=9.3", cy=2.3")
- Cartels 노드: 하단 중앙 (cx=6.66", cy=4.8")
- gap 화살표: unravel 우측 ↔ Shisui 좌측, 빨강 점선, 라벨 "Tempo gap"
- cartels 화살표 2개: Cartels → unravel, Cartels → Shisui (각각 검정 실선, 라벨 "Support")

### AR 다이어그램 (Section 06)
```
   ┌───────────── stay together (OBJ) ─────────────┐
   │                                                │
   Maozyn ←──── kings (help) ─────← Kings
   (Hill-close)                    (Spine/Dictate)
   └────────────────────────────────────────────────┘
```
- Maozyn 노드: 좌측 (cx=4.0", cy=3.5")
- Kings 노드: 우측 (cx=9.3", cy=3.5")
- kings 화살표: Kings → Maozyn, 회색 점선, 라벨 "Help him fight clean"
- 빨강 점선 박스: 두 노드 감싸는 큰 사각형 (MSO_SHAPE.RECTANGLE, 채우기 없음, 빨강 점선 테두리) + 상단 라벨 "Stay together in OBJ fights"

---

## 6. 파일 구조

```
coaching brain/
├── make_pptx.py              (기존, Post-Loss Speech — 훼손 X)
├── make_pptx_roles.py        (신규 — 본 작업)
└── 역할정합서_PPT.pptx       (산출물)
```

`make_pptx_roles.py`는 `make_pptx.py`의 헬퍼(`_set_font`, `_add_text`, `_rect`, `_line`, `_bg`, `_footer`, `slide_title`, `slide_divider`, `slide_statement`, `slide_quote`, `slide_bullets`, `slide_closing`)를 복사해서 시작하고, 새 헬퍼(`_node`, `_arrow`, `_gap_arrow`, `slide_roster_diagram`, `slide_rolecard`)를 추가.

---

## 7. 실행 및 검증

1. `cd "C:/Users/0616y/Downloads/Team management app/coaching brain"`
2. `python make_pptx_roles.py`
3. 출력: `역할정합서_PPT.pptx`
4. 검증:
   - 슬라이드 수 30 ± 2
   - 다이어그램 2개 노드+화살표 정상 렌더
   - 색/폰트 기존 시스템 일관
   - pptx 파일이 열리는지 (python-pptx 검증 완료 = OK)
5. 실제 PPT 앱에서 열어 시각적 검증은 사용자가 수행

---

## 8. 명시적 비고 (scope 박스)

- **매핑 내용은 이번 PPT에 안 넣는다** — "다음 미팅에서 사전 논의" 안내 슬라이드만.
- **Kings 코칭은 공개** — 팀 전원 자리에서 발표 전제.
- **Shisui, exile, Jason**은 텍스트에서 언급되지만 깊이 다루지 않음 (텍스트 비중에 맞춤).
- 데이터 파일(선수 실제 스탯)은 사용하지 않음 — 이건 전술/역할 문서이며 통계 대시보드가 아님.
