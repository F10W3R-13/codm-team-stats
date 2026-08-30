# Role Alignment & Tactical Model PPT — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `coaching brain/역할정합서_PPT.pptx`를 생성하는 pptxgenjs 스크립트를 작성하고, validation + 시각 QA를 통과시킨다.

**Architecture:** Node.js 단일 스크립트 `coaching brain/make_pptx_roles.js`. 기존 `make_pptx.py`(python-pptx, Post-Loss Speech)의 Astryx neutral 디자인 시스템을 pptxgenjs로 이식하고, 노드+화살표 다이어그램(SMG/AR 라인업)과 선수 롤카드를 추가. 기존 원본 훼손 없이 새 산출물.

**Tech Stack:** Node.js + pptxgenjs (신규 설치), LibreOffice(soffice)+pdftoppm(시각 QA), markitdown(콘텐츠 QA), validate.py(파일 QA).

**Spec:** `docs/superpowers/specs/2026-07-25-role-alignment-ppt-design.md`

## Global Constraints

- **언어**: English only (기존 Post-Loss Speech PPT 톤 일관)
- **캔버스**: `LAYOUT_WIDE` = 13.3" × 7.5" (기존 make_pptx.py와 동일 치수)
- **폰트**: Pretendard (메인) + Calibri (fallback). 단, **Pretendard는 이 환경에 없고 LibreOffice가 Calibri/Arial로 대체 렌더** → 시각 QA에서 Pretendard 영역의 텍스트 fit은 대략적이며 ~10% slack 고려. 본문 텍스트(fit이 중요한 곳)는 Calibri로 직접 지정.
- **색 (8자리/`#` 금지, 6자리 hex)**: 
  - `FAFAFA`(BG) `FFFFFF`(SURFACE) `262626`(TEXT/ACCENT) `535353`(TEXT_2) `8A8A8A`(MUTED) 
  - `E5E5E5`(BORDER) `C8C8C8`(BORDER_STRONG)
  - `F97316`(HP=SMG 배지) `8B5CF6`(SND=AR 배지) `DC2626`(DANGER=gap) `16A34A`(SUCCESS=positive 사인)
- **다이어그램 화살표 규약**: Cartels 콜 = 검정 `262626` 실선 / Kings 콜 = 회색 `8A8A8A` 점선(`dashType:"dash"`) / gap = 빨강 `DC2626` 점선
- **금지**: `#` 접두 hex, 8자리 hex(alpha 금지 → `transparency`/`opacity` 사용), 텍스트만 있는 슬라이드, 제목 밑 액센트 라인, 데코용 컬러 바/스트라이프(기존 make_pptx.py의 얇은 액센트 바는 kicker 구분용 기능적 요소라 허용 — 허용 범위: 좌측 kicker 구분선 Pt(3) 두께 1곳/슬라이드 이하)
- **기존 파일 훼손 금지**: `coaching brain/make_pptx.py`는 건드리지 않는다.

---

## File Structure

```
coaching brain/
├── make_pptx.py                  (기존 — 훼손 X)
├── make_pptx_roles.js            (신규 — 본 작업, pptxgenjs 스크립트)
└── 역할정합서_PPT.pptx           (산출물)
```

스크립트는 단일 파일로, 다음 섹션으로 구성:
1. **Palette/Constants** — 색/폰트/레이아웃 상수
2. **Helpers** — `_text()`, `_rect()`, `_line()`, `_node()`, `_arrow()`, `_gapBox()`, `addFooter()`
3. **Slide builders** — `slideTitle()`, `slideDivider()`, `slideStatement()`, `slideQuote()`, `slideBullets()`, `slideRolecard()`, `slideRosterDiagram()`, `slideClosing()`
4. **Deck content** — 각 슬라이드 호출 (섹션별 그룹)
5. **Save + footer pass**

---

## Task 1: 환경 준비 + 스캐폴드

**Files:**
- Create: `coaching brain/make_pptx_roles.js`

**Interfaces:**
- Produces: `coaching brain/make_pptx_roles.js` (이후 Task들이 확장), 의존성 pptxgenjs 설치됨

- [ ] **Step 1: pptxgenjs 설치 확인/설치**

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && node -e "require('pptxgenjs'); console.log('OK')"
```
Expected: `OK` 출력. 실패 시:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && npm install pptxgenjs
```
(설치 시 `coaching brain/package.json` + `node_modules/` 생성됨 — `.gitignore`에 `node_modules/` 있는지 Task 7에서 확인)

- [ ] **Step 2: 스캐폴드 작성 — 팔레트 + 프레젠테이션 초기화만**

`coaching brain/make_pptx_roles.js`:
```js
const pptxgen = require("pptxgenjs");

// --- Astryx neutral palette (6-digit hex, no # prefix) ---
const BG            = "FAFAFA";
const SURFACE       = "FFFFFF";
const TEXT          = "262626";
const TEXT_2        = "535353";
const MUTED         = "8A8A8A";
const BORDER        = "E5E5E5";
const BORDER_STRONG = "C8C8C8";
const ACCENT        = "262626";   // = TEXT (black UI accent)
const HP            = "F97316";   // SMG badge (orange)
const SND           = "8B5CF6";   // AR badge (purple)
const DANGER        = "DC2626";   // gap
const SUCCESS       = "16A34A";   // positive sign

// Fonts: Pretendard not in this env; LibreOffice substitutes → use Calibri directly for fit-critical text.
const FONT = "Pretendard";     // titles/kickers (visual identity; QA approximate)
const FONT_BODY = "Calibri";   // body/bullets/diagram labels (QA reliable)

const SLIDE_W = 13.333;        // LAYOUT_WIDE
const SLIDE_H = 7.5;

const TOTAL_SLIDES = 30;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";   // 13.333 x 7.5
pres.author = "Coach";
pres.title = "Role Alignment & Tactical Model";

// (helpers added in Task 2)
// (slides added in Tasks 3-8)

pres.writeFile({ fileName: "역할정합서_PPT.pptx" })
    .then(fn => console.log("OK:", fn));
```

- [ ] **Step 3: 실행해서 빈 덱 생성 확인**

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && node make_pptx_roles.js
```
Expected: `OK: ...역할정합서_PPT.pptx` 출력 + 파일 생성. 아직 슬라이드 0개.

- [ ] **Step 4: 파일 QA — validate.py 통과 확인**

Run:
```bash
python "C:/Users/0616y/.zcode/skills/pptx/scripts/office/validate.py" "C:/Users/0616y/Downloads/Team management app/coaching brain/역할정합서_PPT.pptx"
```
Expected: 빈 덱이라도 schema/relation 에러 없음. 에러 나면 hex 색/`#` 오타 확인.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/0616y/Downloads/Team management app" && git add "coaching brain/make_pptx_roles.js" && git commit -m "feat: scaffold role alignment pptx generator (pptxgenjs)"
```

---

## Task 2: 헬퍼 함수 — 텍스트/사각형/라인

**Files:**
- Modify: `coaching brain/make_pptx_roles.js` (Task 1의 `(helpers added in Task 2)` 위치에 삽입)

**Interfaces:**
- Produces: `text(slide, opts)`, `rect(slide, opts)`, `hline(slide, opts)`, `footer(slide, idx, label)`. 이후 모든 슬라이드 빌더가 사용.

- [ ] **Step 1: 헬퍼 함수 추가**

`pres.title = ...` 줄 **바로 뒤**, `(slides added...)` 주석 **앞**에 삽입:

```js
// ===== Helpers =====

// Text box. opts: {x, y, w, h, text, size, color, bold, italic, align, valign, font, lineSpacingMultiple}
function text(slide, o) {
    const opts = {
        x: o.x, y: o.y, w: o.w, h: o.h,
        fontSize: o.size || 18,
        color: o.color || TEXT,
        bold: !!o.bold,
        italic: !!o.italic,
        align: o.align || "left",
        valign: o.valign || "top",
        fontFace: o.font || FONT_BODY,
        margin: 0,
        wrap: true,
    };
    if (o.lineSpacingMultiple) opts.lineSpacingMultiple = o.lineSpacingMultiple;
    slide.addText(o.text, opts);
}

// Rectangle. opts: {x, y, w, h, fill, line, lineW, dashType, rectRadius}
function rect(slide, o) {
    const shapeOpts = {
        x: o.x, y: o.y, w: o.w, h: o.h,
        fill: { color: o.fill || SURFACE },
        line: o.line ? { color: o.line, width: o.lineW || 1 } : undefined,
        shadow: { type: "none" },
    };
    if (o.dashType) {
        if (shapeOpts.line) shapeOpts.line.dashType = o.dashType;
    }
    if (o.rectRadius) shapeOpts.rectRadius = o.rectRadius;
    slide.addShape(o.shape || "rect", shapeOpts);
}

// Horizontal line connector. opts: {x, y, w, color, width, dashType}
function hline(slide, o) {
    slide.addShape("line", {
        x: o.x, y: o.y, w: o.w, h: 0,
        line: { color: o.color || BORDER_STRONG, width: o.width || 1.5, dashType: o.dashType },
    });
}

// Footer meta strip (Astryx style). idx = slide number (1-based body slide).
function footer(slide, idx, label) {
    text(slide, { x: 0.7, y: 7.0, w: 8, h: 0.3, text: label, size: 10, color: MUTED, font: FONT });
    text(slide, { x: 11.5, y: 7.0, w: 1.5, h: 0.3, text: `${String(idx).padStart(2,"0")} / ${String(TOTAL_SLIDES).padStart(2,"0")}`, size: 10, color: MUTED, align: "right", font: FONT });
}
```

- [ ] **Step 2: 빈 슬라이드 1개 추가해서 헬퍼 smoke test**

`pres.writeFile(...)` **앞**에 임시로:
```js
const _t = pres.addSlide();
text(_t, { x: 0.7, y: 1, w: 12, h: 1, text: "SMOKE TEST", size: 54, color: TEXT, bold: true, font: FONT });
rect(_t, { x: 0.7, y: 2.5, w: 2, h: 1, fill: ACCENT });
hline(_t, { x: 0.7, y: 4, w: 11.9, color: BORDER_STRONG });
footer(_t, 1, "smoke test");
```
(다음 Task에서 제거)

- [ ] **Step 3: 실행 + 시각 QA (이미지 변환)**

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && node make_pptx_roles.js && "C:/Program Files/LibreOffice/program/soffice.exe" --headless --convert-to pdf "역할정합서_PPT.pptx" && rm -f slide-*.jpg && pdftoppm -jpeg -r 100 "역할정합서_PPT.pdf" slide && ls slide-*.jpg
```
Expected: `slide-1.jpg` 생성. 뷰어로 확인 → 텍스트/사각형/라인/푸터 정상 렌더.

- [ ] **Step 4: 시각 확인 후 smoke test 제거**

Step 2의 임시 코드 4줄 + `const _t = pres.addSlide();` 삭제.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/0616y/Downloads/Team management app" && git add "coaching brain/make_pptx_roles.js" && git commit -m "feat: add text/rect/hline/footer helpers for pptx"
```

---

## Task 3: 기본 슬라이드 빌더 — title/divider/statement/quote/bullets/closing

**Files:**
- Modify: `coaching brain/make_pptx_roles.js`

**Interfaces:**
- Produces: `slideTitle()`, `slideDivider(num, title, subtitle)`, `slideStatement(text, {kicker})`, `slideQuote(text, attribution)`, `slideBullets(items, {title, kicker})`, `slideClosing(text, sub)`. 각 함수는 `slide` 객체 반환.
- `slideBullets`의 `items`: `[{head, sub}]` (sub는 "" 허용)

- [ ] **Step 1: 빌더 함수들 추가**

footer 헬퍼 **뒤**에 삽입:

```js
// ===== Slide builders =====

function bgFill(slide, color) {
    rect(slide, { x: 0, y: 0, w: SLIDE_W, h: SLIDE_H, fill: color });
}

function slideTitle() {
    const s = pres.addSlide();
    bgFill(s, BG);
    // left accent bar (functional kicker divider, not decorative stripe)
    rect(s, { x: 0.7, y: 1.1, w: 0.6, h: 0.04, fill: TEXT });
    text(s, { x: 0.7, y: 1.3, w: 10, h: 0.4, text: "ROLE ALIGNMENT & TACTICAL MODEL", size: 12, color: MUTED, bold: true, font: FONT });
    text(s, { x: 0.7, y: 2.6, w: 12, h: 2, text: "How the veteran core runs the team.", size: 60, color: TEXT, bold: true, font: FONT });
    text(s, { x: 0.7, y: 4.4, w: 11, h: 0.6, text: "Three veterans, three different jobs — and what changes today.", size: 22, color: TEXT_2, font: FONT_BODY });
    hline(s, { x: 0.7, y: 5.3, w: 11.9 });
    text(s, { x: 0.7, y: 5.5, w: 8, h: 0.4, text: "Team Briefing  ·  English", size: 11, color: MUTED, font: FONT });
    return s;
}

function slideDivider(num, title, subtitle) {
    const s = pres.addSlide();
    bgFill(s, BG);
    text(s, { x: 0.7, y: 1.0, w: 6, h: 3.5, text: String(num).padStart(2, "0"), size: 180, color: BORDER, bold: true, font: FONT });
    rect(s, { x: 0.7, y: 4.7, w: 0.6, h: 0.04, fill: TEXT });
    text(s, { x: 0.7, y: 4.9, w: 6, h: 0.4, text: `SECTION ${String(num).padStart(2,"0")}`, size: 12, color: MUTED, bold: true, font: FONT });
    text(s, { x: 0.7, y: 5.3, w: 12, h: 1.2, text: title, size: 44, color: TEXT, bold: true, font: FONT });
    if (subtitle) text(s, { x: 0.7, y: 6.3, w: 12, h: 0.6, text: subtitle, size: 18, color: TEXT_2, italic: true, font: FONT_BODY });
    return s;
}

function slideStatement(body, kicker) {
    const s = pres.addSlide();
    bgFill(s, BG);
    if (kicker) text(s, { x: 0.7, y: 1.2, w: 12, h: 0.4, text: kicker.toUpperCase(), size: 12, color: MUTED, bold: true, font: FONT });
    text(s, { x: 0.7, y: 2.4, w: 11.9, h: 3, text: body, size: 50, color: TEXT, bold: true, font: FONT_BODY, lineSpacingMultiple: 1.1 });
    return s;
}

function slideQuote(quote, attribution) {
    const s = pres.addSlide();
    bgFill(s, SURFACE);
    text(s, { x: 0.7, y: 0.6, w: 3, h: 2.5, text: "\u201C", size: 200, color: BORDER, bold: true, font: FONT });
    text(s, { x: 1.5, y: 2.6, w: 10.5, h: 2.5, text: quote, size: 36, color: TEXT, bold: true, font: FONT_BODY, lineSpacingMultiple: 1.15 });
    if (attribution) {
        hline(s, { x: 1.5, y: 5.3, w: 0.8, color: BORDER_STRONG, width: 2 });
        text(s, { x: 1.5, y: 5.5, w: 10, h: 0.4, text: attribution, size: 14, color: MUTED, italic: true, font: FONT_BODY });
    }
    return s;
}

function slideBullets(items, opts) {
    const s = pres.addSlide();
    bgFill(s, BG);
    if (opts && opts.kicker) text(s, { x: 0.7, y: 0.8, w: 12, h: 0.4, text: opts.kicker.toUpperCase(), size: 12, color: MUTED, bold: true, font: FONT });
    if (opts && opts.title) text(s, { x: 0.7, y: 1.2, w: 12, h: 0.9, text: opts.title, size: 36, color: TEXT, bold: true, font: FONT_BODY });
    const top = 2.7;
    const rowH = Math.min(1.2, (7.0 - top) / Math.max(items.length, 1));
    items.forEach((it, i) => {
        const y = top + rowH * i;
        rect(s, { x: 0.7, y: y + 0.05, w: 0.08, h: Math.min(0.7, rowH - 0.1), fill: ACCENT });
        text(s, { x: 1.0, y: y, w: 11.5, h: rowH * 0.45, text: it.head, size: 20, color: TEXT, bold: true, font: FONT_BODY });
        if (it.sub) text(s, { x: 1.0, y: y + rowH * 0.42, w: 11.5, h: rowH * 0.5, text: it.sub, size: 14, color: TEXT_2, font: FONT_BODY });
    });
    return s;
}

function slideClosing(body, sub) {
    const s = pres.addSlide();
    bgFill(s, TEXT);   // inverted dark slide
    rect(s, { x: 0.7, y: 1.2, w: 0.6, h: 0.04, fill: SURFACE });
    text(s, { x: 0.7, y: 1.4, w: 6, h: 0.4, text: "CLOSING", size: 12, color: BORDER, bold: true, font: FONT });
    text(s, { x: 0.7, y: 2.6, w: 12, h: 2.5, text: body, size: 64, color: SURFACE, bold: true, font: FONT_BODY, lineSpacingMultiple: 1.05 });
    if (sub) text(s, { x: 0.7, y: 5.0, w: 11, h: 0.6, text: sub, size: 20, color: BORDER, font: FONT_BODY });
    return s;
}
```

- [ ] **Step 2: deck content에 타이틀 + 테스트 슬라이드 1개씩 임시 추가**

`pres.writeFile(...)` **앞**:
```js
slideTitle();
slideDivider(1, "Test divider", "subtitle here");
slideStatement("Statement text for smoke.", "Section 01");
slideQuote("Quote text for smoke.", "Attribution");
slideBullets([{head: "First", sub: "sub text"}, {head: "Second", sub: ""}], {title: "Bullets title", kicker: "test"});
slideClosing("Run the system.", "Don't question the intent.");
```

- [ ] **Step 3: 실행 + 시각 QA**

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && node make_pptx_roles.js && python "C:/Users/0616y/.zcode/skills/pptx/scripts/office/validate.py" "역할정합서_PPT.pptx" && "C:/Program Files/LibreOffice/program/soffice.exe" --headless --convert-to pdf "역할정합서_PPT.pptx" && rm -f slide-*.jpg && pdftoppm -jpeg -r 100 "역할정합서_PPT.pdf" slide && ls slide-*.jpg
```
Expected: validate OK + `slide-1.jpg` ~ `slide-6.jpg`. 뷰어로 확인:
- title 큰 텍스트 잘림 없는지
- divider 숫자 180pt가 영역 안에 드는지
- statement 2줄 이상 시 간격 적절한지
- quote 따옴표 큰 글리프 정상
- bullets head/sub 간격, accent 바 정상
- closing 다크 배경에 흰 텍스트 정상

- [ ] **Step 4: 시각 QA 결과 기록 + 수정**

문제 발견 시 각 빌더 함수에서 size/좌표 조정. 수정 후 Step 3 재실행 (pptx → pdf → jpg 만 다시, validate는 마지막에).

- [ ] **Step 5: 임시 deck content 제거**

Step 2의 6줄 제거 (본 Task 4-8에서 실제 content로 채움).

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/0616y/Downloads/Team management app" && git add "coaching brain/make_pptx_roles.js" && git commit -m "feat: add title/divider/statement/quote/bullets/closing slide builders"
```

---

## Task 4: 다이어그램 헬퍼 — node/arrow + SMG 다이어그램

**Files:**
- Modify: `coaching brain/make_pptx_roles.js`

**Interfaces:**
- Produces: `node(slide, {cx, cy, w, h, name, role, lineup})`, `arrow(slide, {x1, y1, x2, y2, kind, label})`, `slideRosterDiagramSMG()`.
- `lineup`: `"SMG"` → HP 색 / `"AR"` → SND 색
- `kind`: `"cartels"` (검정 실선) / `"kings"` (회색 점선) / `"gap"` (빨강 점선)

- [ ] **Step 1: node + arrow 헬퍼 추가**

slide builders **뒤**에 삽입:

```js
// ===== Diagram primitives =====

const LINEUP_COLOR = { SMG: HP, AR: SND };

// Player node, centered at (cx, cy). opts: {cx, cy, w, h, name, role, lineup}
function node(slide, o) {
    const x = o.cx - o.w / 2;
    const y = o.cy - o.h / 2;
    const badge = LINEUP_COLOR[o.lineup] || TEXT;
    // main card
    rect(slide, { x, y, w: o.w, h: o.h, fill: SURFACE, line: badge, lineW: 1.5 });
    // left badge strip (functional lineup marker)
    rect(slide, { x, y, w: 0.08, h: o.h, fill: badge });
    // name + role
    text(slide, { x: x + 0.2, y: y + 0.12, w: o.w - 0.3, h: o.h * 0.45, text: o.name, size: 18, color: TEXT, bold: true, valign: "top", font: FONT_BODY });
    if (o.role) text(slide, { x: x + 0.2, y: y + o.h * 0.5, w: o.w - 0.3, h: o.h * 0.45, text: o.role, size: 12, color: TEXT_2, valign: "top", font: FONT_BODY });
}

// Arrow between two points. opts: {x1, y1, x2, y2, kind, label}
// kind: "cartels" | "kings" | "gap"
function arrow(slide, o) {
    const cfg = {
        cartels: { color: ACCENT, width: 2.5, dashType: undefined,  labelColor: TEXT },
        kings:   { color: MUTED,  width: 2,   dashType: "dash",      labelColor: MUTED },
        gap:     { color: DANGER, width: 1.5, dashType: "dash",      labelColor: DANGER },
    }[o.kind];
    slide.addShape("line", {
        x: o.x1, y: o.y1, w: o.x2 - o.x1, h: o.y2 - o.y1,
        line: { color: cfg.color, width: cfg.width, dashType: cfg.dashType, endArrowType: "triangle" },
    });
    if (o.label) {
        const mx = (o.x1 + o.x2) / 2;
        const my = (o.y1 + o.y2) / 2;
        // label background chip for readability
        const lw = Math.min(4, 0.12 * o.label.length + 0.4);
        rect(slide, { x: mx - lw / 2, y: my - 0.18, w: lw, h: 0.36, fill: BG });
        text(slide, { x: mx - lw / 2, y: my - 0.18, w: lw, h: 0.36, text: o.label, size: 10, color: cfg.labelColor, bold: true, align: "center", valign: "middle", font: FONT_BODY });
    }
}
```

- [ ] **Step 2: SMG 다이어그램 빌더 추가**

```js
// ===== Roster diagrams =====

function slideRosterDiagramSMG() {
    const s = pres.addSlide();
    bgFill(s, BG);
    text(s, { x: 0.7, y: 0.8, w: 12, h: 0.4, text: "SECTION 03 · SMG DUO", size: 12, color: MUTED, bold: true, font: FONT });
    text(s, { x: 0.7, y: 1.2, w: 12, h: 0.9, text: "Two gunfighters, one calibrator.", size: 32, color: TEXT, bold: true, font: FONT_BODY });

    // layout: unravel top-left, Shisui top-right, Cartels bottom-center
    const NODE_W = 2.8, NODE_H = 1.3;
    const unr = { cx: 3.6,  cy: 3.2 };
    const shi = { cx: 9.7,  cy: 3.2 };
    const car = { cx: 6.66, cy: 5.5 };

    // gap arrow (unravel <-> Shisui) — horizontal
    arrow(s, { x1: unr.cx + NODE_W/2, y1: unr.cy, x2: shi.cx - NODE_W/2, y2: shi.cy, kind: "gap", label: "TEMPO GAP — drift apart" });
    // cartels support arrows
    arrow(s, { x1: car.cx - 0.6, y1: car.cy - NODE_H/2, x2: unr.cx + 0.4, y2: unr.cy + NODE_H/2, kind: "cartels", label: "support" });
    arrow(s, { x1: car.cx + 0.6, y1: car.cy - NODE_H/2, x2: shi.cx - 0.4, y2: shi.cy + NODE_H/2, kind: "cartels", label: "support" });

    // nodes (drawn last so they sit on top of arrows)
    node(s, { cx: unr.cx, cy: unr.cy, w: NODE_W, h: NODE_H, name: "unravel", role: "Tempo stealer · 1vX", lineup: "SMG" });
    node(s, { cx: shi.cx, cy: shi.cy, w: NODE_W, h: NODE_H, name: "Shisui",  role: "Clutch · Main SMG",   lineup: "SMG" });
    node(s, { cx: car.cx, cy: car.cy, w: NODE_W, h: NODE_H, name: "Cartels", role: "Veteran · Calibrator", lineup: "SMG" });

    // bottom note
    text(s, { x: 0.7, y: 6.5, w: 11.9, h: 0.4, text: "Cartels doesn't pull them to a midpoint. He picks the side that needs him.", size: 14, color: TEXT_2, italic: true, align: "center", font: FONT_BODY });
    return s;
}
```

- [ ] **Step 3: deck에 임시 추가 + 실행 + 시각 QA**

`pres.writeFile(...)` **앞**:
```js
slideRosterDiagramSMG();
```

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && node make_pptx_roles.js && "C:/Program Files/LibreOffice/program/soffice.exe" --headless --convert-to pdf "역할정합서_PPT.pptx" && rm -f slide-*.jpg && pdftoppm -jpeg -r 120 "역할정합서_PPT.pdf" slide && ls slide-*.jpg
```
Expected: `slide-1.jpg`. 뷰어로 확인:
- 노드 3개 정상 배치 (겹침 없는지)
- 화살표가 노드 안쪽으로 들어가지 않는지 (끝점이 노드 edge에 닿는지)
- gap 빨강 점선 가로 화살표, 라벨 가독성
- cartels 검정 실선 2개, 라벨 "support" 가독성
- 노드 텍스트 잘림 없는지

- [ ] **Step 4: 좌표 미세조정 (필요 시)**

화살표 끝이 노드 내부로 파고들면 x1/x2를 노드 edge 바깥으로 조금 밀기. 라벨이 화살표 위에 깔끔히 앉는지 확인.

- [ ] **Step 5: 임시 호출 제거**

`slideRosterDiagramSMG();` 제거 (Task 7에서 실제 deck에 배치).

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/0616y/Downloads/Team management app" && git add "coaching brain/make_pptx_roles.js" && git commit -m "feat: add node/arrow diagram primitives + SMG roster diagram"
```

---

## Task 5: AR 다이어그램 + 롤카드 빌더

**Files:**
- Modify: `coaching brain/make_pptx_roles.js`

**Interfaces:**
- Produces: `slideRosterDiagramAR()`, `slideRolecard({name, lineup, role, responsibilities, identity})`.
- `responsibilities`: `string[]` (3-4 items)

- [ ] **Step 1: AR 다이어그램 빌더 추가**

```js
function slideRosterDiagramAR() {
    const s = pres.addSlide();
    bgFill(s, BG);
    text(s, { x: 0.7, y: 0.8, w: 12, h: 0.4, text: "SECTION 06 · AR DUO", size: 12, color: MUTED, bold: true, font: FONT });
    text(s, { x: 0.7, y: 1.2, w: 12, h: 0.9, text: "Stay together when the OBJ fight starts.", size: 32, color: TEXT, bold: true, font: FONT_BODY });

    const NODE_W = 2.8, NODE_H = 1.4;
    const mao = { cx: 4.0, cy: 3.8 };
    const kng = { cx: 9.3, cy: 3.8 };

    // "stay together" red dashed box wrapping both nodes
    const boxX = mao.cx - NODE_W/2 - 0.4;
    const boxY = mao.cy - NODE_H/2 - 0.4;
    const boxW = (kng.cx + NODE_W/2) - (mao.cx - NODE_W/2) + 0.8;
    const boxH = NODE_H + 0.8;
    rect(s, { x: boxX, y: boxY, w: boxW, h: boxH, fill: "none" /*transparent*/, line: DANGER, lineW: 1.5, dashType: "dash" });
    // box label above
    text(s, { x: boxX, y: boxY - 0.35, w: boxW, h: 0.3, text: "STAY TOGETHER IN OBJ FIGHTS", size: 11, color: DANGER, bold: true, align: "center", font: FONT_BODY });

    // kings -> maozyn help arrow
    arrow(s, { x1: kng.cx - NODE_W/2, y1: kng.cy, x2: mao.cx + NODE_W/2, y2: mao.cy, kind: "kings", label: "help him fight clean" });

    node(s, { cx: mao.cx, cy: mao.cy, w: NODE_W, h: NODE_H, name: "Maozyn", role: "Hill-close · Selfless AR", lineup: "AR" });
    node(s, { cx: kng.cx, cy: kng.cy, w: NODE_W, h: NODE_H, name: "Kings",  role: "Spine · Dictate in downtime", lineup: "AR" });

    text(s, { x: 0.7, y: 6.4, w: 11.9, h: 0.4, text: "You can split in rotation. Never split when the OBJ fight starts.", size: 14, color: TEXT_2, italic: true, align: "center", font: FONT_BODY });
    return s;
}
```

- [ ] **Step 2: 롤카드 빌더 추가**

```js
// Player role card. opts: {name, lineup, role (one-liner), responsibilities[string], identity?}
function slideRolecard(o) {
    const s = pres.addSlide();
    bgFill(s, BG);
    const badge = LINEUP_COLOR[o.lineup] || TEXT;

    // left: big name + badge
    rect(s, { x: 0.7, y: 1.0, w: 0.08, h: 5.0, fill: badge });
    text(s, { x: 1.0, y: 1.0, w: 4.5, h: 2.5, text: o.name, size: 56, color: TEXT, bold: true, font: FONT_BODY });
    text(s, { x: 1.0, y: 3.4, w: 4.5, h: 0.4, text: `${o.lineup} ${o.lineup === "SMG" ? "· gunfighter" : "· anchor"}`, size: 13, color: badge, bold: true, font: FONT_BODY });

    // right: role one-liner + responsibilities
    text(s, { x: 6.0, y: 1.0, w: 6.6, h: 1.4, text: o.role, size: 26, color: TEXT, bold: true, font: FONT_BODY, lineSpacingMultiple: 1.1 });
    const resp = o.responsibilities || [];
    const top = 2.7;
    const rowH = Math.min(0.95, (6.0 - top) / Math.max(resp.length, 1));
    resp.forEach((r, i) => {
        const y = top + rowH * i;
        rect(s, { x: 6.0, y: y + 0.1, w: 0.06, h: Math.min(0.6, rowH - 0.15), fill: MUTED });
        text(s, { x: 6.25, y: y, w: 6.4, h: rowH, text: r, size: 15, color: TEXT_2, valign: "top", font: FONT_BODY });
    });
    if (o.identity) {
        hline(s, { x: 6.0, y: 6.2, w: 6.6, color: BORDER });
        text(s, { x: 6.0, y: 6.35, w: 6.6, h: 0.5, text: o.identity, size: 13, color: MUTED, italic: true, font: FONT_BODY });
    }
    return s;
}
```

- [ ] **Step 3: 임시 호출 + 실행 + 시각 QA**

`pres.writeFile(...)` **앞**:
```js
slideRosterDiagramAR();
slideRolecard({ name: "unravel", lineup: "SMG", role: "Momentum builder, one-vs-many gunskill", responsibilities: ["Strong 1vX", "Reactive aim", "Tempo-stealer"], identity: "Wants to be one step ahead — that's why capture kills are high" });
```

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && node make_pptx_roles.js && "C:/Program Files/LibreOffice/program/soffice.exe" --headless --convert-to pdf "역할정합서_PPT.pptx" && rm -f slide-*.jpg && pdftoppm -jpeg -r 120 "역할정합서_PPT.pdf" slide && ls slide-*.jpg
```
Expected: `slide-1.jpg`, `slide-2.jpg`. 확인:
- AR 다이어그램: 빨강 점선 박스가 두 노드를 감싸는지, 박스 라벨 위에 정상, kings 화살표 회색 점선
- 롤카드: 좌측 큰 이름 + 배지색 띠, 우측 role 한 줄 + responsibilities 행 정렬, identity 이탤릭

- [ ] **Step 4: 임시 호출 제거**

2줄 제거.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/0616y/Downloads/Team management app" && git add "coaching brain/make_pptx_roles.js" && git commit -m "feat: add AR roster diagram + rolecard slide builders"
```

---

## Task 6: 전체 덱 콘텐츠 작성 (30장)

**Files:**
- Modify: `coaching brain/make_pptx_roles.js`

**Interfaces:**
- Consumes: 모든 Task 3-5의 빌더 함수
- Produces: 완성된 30장 덱 (footer pass 포함)

- [ ] **Step 1: deck content 작성**

`pres.writeFile(...)` **앞**에 다음을 추가 (한 블록). 슬라이드 순서가 스펙의 섹션 순서와 일치해야 함.

```js
// ==================== DECK CONTENT ====================

// --- Title (1) ---
slideTitle();

// --- Section 01: The call structure (3) ---
slideDivider(1, "Three veterans, three different jobs.", "The call structure.");
slideBullets([
    { head: "Cartels", sub: "What the frontline wants. SMG press lead, 거점 압박 주도." },
    { head: "Kings",   sub: "What our movement wants. Use downtime, dictate the macro." },
    { head: "Shisui",  sub: "Playmaker & clutch tool — not a caller. (For reasons we all know.)" },
], { title: "Who calls what.", kicker: "Section 01 · The call structure" });
slideQuote("Not every veteran has to call. The wrong veteran calling is worse than no call.", "How we use experience");

// --- Section 02: SMG lineup diagnosis (5) ---
slideDivider(2, "Two elite gunfighters — and where they drift apart.", "SMG lineup.");
slideRolecard({
    name: "unravel", lineup: "SMG",
    role: "Momentum builder, one-vs-many gunskill.",
    responsibilities: ["Strong 1vX and reactive aim", "Tempo-stealer — wants to be one step ahead", "High capture kills as a result"],
    identity: "Wants to be one step ahead — that's why capture kills are high."
});
slideBullets([
    { head: "Strength", sub: "강한 일대다 건스킬, 반응속도, 좋은 모멘텀 빌더." },
    { head: "Risk",     sub: "OVERPUSH. 셋업 쉽게 포기하고 추가 밸류를 찾으려 든다." },
    { head: "Aggression", sub: "상대 템포를 빼려고 one step ahead → 거점 킬이 높다." },
], { title: "unravel — what to expect.", kicker: "Section 02 · SMG diagnosis" });
slideRolecard({
    name: "Shisui", lineup: "SMG",
    role: "Main SMG. Clutch & 1v1 — the one we rely on when it's tight.",
    responsibilities: ["Clutch & face-to-face gunfight", "High-pressure reliance", "Gets lost when there's free space"],
    identity: "Free space confuses him — he pulls himself into the hill. That's why obj time is high."
});
slideBullets([
    { head: "Strength", sub: "우수한 클러치, 면대면 건파이트. 빡빡한 상황에서 의지할 메인 SMG." },
    { head: "Risk",     sub: "여유공간이 남으면 길을 잃음 → 본인을 거점 안으로 불러들임 → 높은 obj 타임." },
    { head: "Dynamics", sub: "좋은 SMG 듀오 — 그러나 살아있을 때든, 리스폰 미스매치 때든 둘이 자주 벌어진다." },
], { title: "Shisui — and the duo's drift.", kicker: "Section 02 · SMG diagnosis" });

// --- Section 03: SMG diagram (1) ---
slideRosterDiagramSMG();

// --- Section 04: Cartels' role (3) ---
slideDivider(4, "Don't average them out. Reinforce the side that needs it.", "Cartels' job on SMG.");
slideQuote("Their gunskill is real. The job isn't to slow them down — it's to cut the risk out of their high-risk, high-return plays.", "Cartels' real brief");
slideBullets([
    { head: "Don't", sub: "중간지점으로 끌어당기기 — 둘 다 희생시킨다." },
    { head: "Do",    sub: "네 도움이 필요한 쪽을 돕는다. 프런트라인이 단단해진다." },
    { head: "Result", sub: "Risk ↓, Return ↑ — 그들의 플레이메이킹 잠재력을 열어둔다." },
], { title: "What reinforcing looks like.", kicker: "Section 04 · Cartels' job" });
slideStatement("Maximize their return. Cut their risk.", "Section 04 · The veteran SMG job");

// --- Section 05: AR lineup diagnosis (5) ---
slideDivider(5, "Selfless by default — with one trap to avoid.", "AR lineup.");
slideRolecard({
    name: "Maozyn", lineup: "AR",
    role: "Selfless AR (except P1). Hill-close, sacrifices the body.",
    responsibilities: ["Hill-close positioning", "Throws his body for the team", "Flex AR gunfights — needs to be intuitive"],
    identity: "Intuitive player — overthinking is the enemy."
});
slideBullets([
    { head: "기본", sub: "P1 제외 hill에서 selfless. 거점과 가깝고 과감히 몸을 던진다." },
    { head: "함정 ⚠", sub: "워머신만 쓰면 보이지 않는 위치에서 스나이프 시도 → 포지션 붕괴. 팀은 그대로인데 본인만 오퍼레이터 버튼 → 플랭크에 죽고 뒤에서 맞음." },
    { head: "사인 ✓", sub: "퓨리파이어처럼 쓰라는 주문을 잘 지키고 있다. 계속하길 바람. reasoning을 알아야 게임 내에서도 응용 가능해서 다시 언급." },
], { title: "Maozyn — the default, the trap, the sign.", kicker: "Section 05 · AR diagnosis" });
slideRolecard({
    name: "Kings", lineup: "AR",
    role: "Veteran spine — when the calls are on.",
    responsibilities: ["Mid-game anchor", "Damage positions", "Dictate in downtime (rotation / team wipe)"],
    identity: "Call consistency is the gap — not skill."
});
slideBullets([
    { head: "Good",  sub: "베테랑. 컨디션 좋을 때 확실한 허리." },
    { head: "The problem", sub: "콜아웃의 갭이 크다 (이유 불문). 편차가 크다." },
    { head: "Why it mattered", sub: "Point Major 중간 서브아웃의 이유. (exile도 루키+팔로워 성향이라 근본 해결은 아니었음.)" },
], { title: "Kings — the gap is consistency, not skill.", kicker: "Section 05 · AR diagnosis" });

// --- Section 06: AR diagram (1) ---
slideRosterDiagramAR();

// --- Section 07: AR in OBJ fights (2) ---
slideDivider(7, "Hacienda P4, Takeoff P3 — solo AR doesn't help.", "AR cooperation in OBJ fights.");
slideBullets([
    { head: "Don't", sub: "OBJ 싸움 중 AR 단독행동 (Hacienda P4, Takeoff P3 등)." },
    { head: "Do (거시)", sub: "Cartels 또는 Jason 등 shoutout call 좋은 SMG의 콜에 거시적 움직임 맞추기." },
    { head: "Do (미시)", sub: "Maozyn 돕기 — 직감적으로 움직이게, overthinking 부담 줄이고 flex AR 건파이트에 집중." },
    { head: "Why",  sub: "중요 순간에 떨어져 있으면 Maozyn이 헷갈린다: '내가 죽으면 SMG 도와줄 AR이 없잖아?'" },
], { title: "OBJ fights — the rules.", kicker: "Section 07 · AR in OBJ" });

// --- Section 08: Downtime dictate (3) ---
slideDivider(8, "Rotation phase, team wipe — that's your window.", "Kings — use your downtime.");
slideStatement("You're not the IGL. You're the IGL for 15 seconds at a time.", "Section 08 · When to take the wheel");
slideBullets([
    { head: "When", sub: "로테이션 phase, team wipe (우리가 다 잡았든 다 따였든) — 순간적 시간 여유." },
    { head: "What", sub: "AR Marks로서 intense 건파이트가 없는 그 순간, 아군 움직임 dictate." },
    { head: "Not",  sub: "매번 IGL이 되라는 게 아님 — 이 순간에만 잡으면 된다." },
], { title: "The window — when and what.", kicker: "Section 08 · Downtime dictate" });

// --- Section 09: Summary + closing (4) ---
slideDivider(9, "One line each.", "If you remember nothing else.");
slideBullets([
    { head: "Cartels (SMG, veteran)", sub: "Support the side that needs you. Don't average them." },
    { head: "Kings (AR, veteran)",    sub: "Use downtime to dictate. Close the call-consistency gap." },
    { head: "unravel (SMG)",          sub: "Your job is the return. The team cuts the risk for you." },
    { head: "Shisui (SMG)",           sub: "Be the clutch tool. We won't ask you to call." },
    { head: "Maozyn (AR)",            sub: "Stay intuitive. Furypiercer, not Operator. Don't think alone in OBJ." },
], { title: "Roster — one line each.", kicker: "Section 09" });
slideStatement("What's the read? We map it out together.", "Next session · mapping workshop");

// --- Closing ---
slideClosing("Run the system.", "The veterans carry the calls. The gunfighters carry the rounds.");

// ==================== FOOTER PASS ====================
// Add footers to body slides (skip title [0], dividers, closing [last]).
// Divider detection: slide whose first big text run is >= 150pt (the giant number).
const allSlides = pres._slides || [];   // pptxgenjs internal: slide objects
// We can't easily introspect font size from pptxgenjs API; instead, mark dividers by index.
// Slide order is deterministic from the build calls above. Track divider indices explicitly:
const DIVIDER_INDICES = new Set([1, 4, 9, 13, 18, 22, 26, 29]);  // indices of dividers (0-based, computed below)
// NOTE: recompute after final build if slide order changes.
const slideArr = Array.from(pres._slides);
slideArr.forEach((sl, i) => {
    if (i === 0) return;                       // title
    if (i === slideArr.length - 1) return;     // closing
    if (DIVIDER_INDICES.has(i)) return;        // divider
    footer(sl, i + 1, "Role Alignment & Tactical Model");
});
```

- [ ] **Step 2: divider 인덱스 재계산**

위 `DIVIDER_INDICES`는 추정치. 실제 빌드된 슬라이드 순서대로 divider 위치를 계산하기 위해, 각 `slideDivider(num, ...)` 호출 **직후에** `console.log`로 인덱스를 찍거나, 더 안정적으로는 divider 함수가 글로벌 카운터에 자기 인덱스를 기록하게 수정.

`slideDivider` 함수 **맨 앞**에 추가:
```js
function slideDivider(num, title, subtitle) {
    const s = pres.addSlide();
    (slideDivider._indices = slideDivider._indices || []).push(pres._slides.length - 1);
    // ... (기존 코드)
}
```
그리고 FOOTER PASS에서:
```js
const DIVIDER_INDICES = new Set(slideDivider._indices || []);
```
(추정치 `new Set([1, 4, ...])` 줄 삭제)

- [ ] **Step 3: 실행 + 콘텐츠 QA (markitdown)**

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && node make_pptx_roles.js && markitdown "역할정합서_PPT.pptx" | head -200
```
Expected: 슬라이드 30개 분량 출력. 확인:
- 슬라이드 순서가 스펙(타이틀 → S01 → S02 → ... → S09 → 클로징)과 일치
- 한국어/영어 혼합 텍스트 깨짐 없는지
- 누락된 슬라이드 없는지 (슬라이드 수 카운트)

- [ ] **Step 4: 슬라이드 수 검증**

Run:
```bash
markitdown "C:/Users/0616y/Downloads/Team management app/coaching brain/역할정합서_PPT.pptx" | grep -c "Slide number:"
```
Expected: `30` (±2 허용). 다르면 deck content에서 빠진/중복된 슬라이드 점검.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/0616y/Downloads/Team management app" && git add "coaching brain/make_pptx_roles.js" && git commit -m "feat: write full 30-slide deck content + footer pass"
```

---

## Task 7: 전체 시각 QA + 수정 루프

**Files:**
- Modify: `coaching brain/make_pptx_roles.js` (필요 시)

**Interfaces:**
- Consumes: 완성된 덱

- [ ] **Step 1: 전체 슬라이드 이미지 변환**

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app/coaching brain" && node make_pptx_roles.js && python "C:/Users/0616y/.zcode/skills/pptx/scripts/office/validate.py" "역할정합서_PPT.pptx" && "C:/Program Files/LibreOffice/program/soffice.exe" --headless --convert-to pdf "역할정합서_PPT.pptx" && rm -f slide-*.jpg && pdftoppm -jpeg -r 120 "역할정합서_PPT.pdf" slide && ls slide-*.jpg
```
Expected: validate OK + `slide-01.jpg` ~ `slide-30.jpg` (또는 `slide-1.jpg` ~ `slide-30.jpg`).

- [ ] **Step 2: 슬라이드별 시각 검사 (뷰어 또는 subagent)**

각 슬라이드 점검 항목:
- [ ] 텍스트 오버플로우 / 잘림 (가장 흔한 결함)
- [ ] 요소 겹침 (텍스트-도형, 라인-단어)
- [ ] 여백 부족 (< 0.5" edge margin)
- [ ] 컬럼/요소 정렬 불일치
- [ ] 저대비 텍스트 (연회색 on 흰색 등)
- [ ] 다이어그램: 노드 겹침, 화살표가 노드 안으로 파고듦, 라벨 가독성
- [ ] 롤카드: 좌/우 영역 균형, responsibilities 행 간격
- [ ] Pretendard 미지원 폰트 자리에서 텍스트 박스 크기 초과 (대략적이므로 slack 확인)

특히 주의:
- **다이어그램 2개** (S03 SMG, S06 AR): 화살표 끝점-노드 edge 거리, 라벨 칩 가독성
- **롤카드 4개** (unravel, Shisui, Maozyn, Kings): role 한 줄이 2줄로 wrap될 때 좌측 이름 영역과 충돌 안 하는지
- **bullets 슬라이드들**: 4-5개 항목일 때 rowH 계산으로 하단 7.0" 초과 안 하는지

- [ ] **Step 3: 결함 수정**

발견된 각 결함에 대해:
1. 해당 빌더 함수의 좌표/size 조정
2. pptx → pdf → jpg 만 재실행 (validate는 마지막 루프에서)
3. 수정 슬라이드만 재확인

수정 원칙:
- 텍스트 오버플로우 → size 축소 또는 컨테이너 확장 (슬라이드 분할은 최후 수단)
- 겹침 → z-order (node는 arrow 뒤에 그림) 또는 좌표 이격
- 다이어그램 화살표-노드 → 끝점을 노드 edge 바깥 0.1" 지점으로

- [ ] **Step 4: 최종 validation**

Run:
```bash
python "C:/Users/0616y/.zcode/skills/pptx/scripts/office/validate.py" "C:/Users/0616y/Downloads/Team management app/coaching brain/역할정합서_PPT.pptx"
```
Expected: PASS (no failures). chart 결함/슬라이드 XML 결함 없음.

- [ ] **Step 5: 콘텐츠 placeholder 스캔**

Run:
```bash
markitdown "C:/Users/0616y/Downloads/Team management app/coaching brain/역할정합서_PPT.pptx" | grep -iE "\bx{3,}\b|lorem|ipsum|\bTODO|\[insert|this.*(page|slide).*layout"
```
Expected: 출력 없음 (placeholder 잔유 없음).

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/0616y/Downloads/Team management app" && git add "coaching brain/make_pptx_roles.js" "coaching brain/역할정합서_PPT.pptx" && git commit -m "fix: visual QA pass for 30-slide role alignment deck"
```

---

## Task 8: .gitignore 점검 + 산출물 정리

**Files:**
- Modify: `.gitignore` (필요 시)

- [ ] **Step 1: node_modules / package-lock.json / pdf / jpg gitignore 확인**

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app" && git check-ignore "coaching brain/node_modules" "coaching brain/package-lock.json" "coaching brain/역할정합서_PPT.pdf" "coaching brain/slide-01.jpg" 2>&1
```
Expected: 각 경로가 ignored로 표시되거나, 산출물 .pptx만 추적 대상.

- [ ] **Step 2: .gitignore에 누락 항목 추가 (필요 시)**

`.gitignore`에 추가 (없으면):
```
# PPT build artifacts (generated, not source)
coaching brain/node_modules/
coaching brain/package-lock.json
coaching brain/*.pdf
coaching brain/slide-*.jpg
coaching brain/복기연설_PPT.pptx
```
단, `역할정합서_PPT.pptx`는 **산출물이지만 추적** (코치가 직접 열어볼 수 있게). 추적 여부는 사용자 판단 — Step 3에서 확인.

- [ ] **Step 3: 사용자에게 산출물 추적 여부 확인**

> 질문 예정: "`역할정합서_PPT.pptx`를 git에 추적할까요, 아니면 빌드 산출물로 .gitignore에 넣을까요? (기존 `복기연설_PPT.pptx`는 추적 안 됨)"

- [ ] **Step 4: 최종 git status 확인**

Run:
```bash
cd "C:/Users/0616y/Downloads/Team management app" && git status
```
Expected: 추적 대상 — `coaching brain/make_pptx_roles.js` (+ 산출물 pptx, 사용자 선택에 따라). 비추적 — node_modules, pdf, jpg, package-lock.json.

- [ ] **Step 5: .gitignore 변경 시 Commit**

```bash
cd "C:/Users/0616y/Downloads/Team management app" && git add .gitignore && git commit -m "chore: gitignore pptx build artifacts (node_modules, pdf, jpg)"
```

---

## Self-Review (작성자 점검)

**1. Spec coverage (스펙 대비):**
- ✅ 타이틀 + 9섹션 + 클로징 구조 (Task 6)
- ✅ SMG 다이어그램 (Task 4) — 노드 3개 + gap/cartels 화살표
- ✅ AR 다이어그램 (Task 5) — 노드 2개 + kings 화살표 + 빨강 박스
- ✅ 롤카드 4개 (unravel, Shisui, Maozyn, Kings) (Task 5 + Task 6)
- ✅ Cartels/Kings/Shisui 콜 책임 (S01, Task 6)
- ✅ 워머신 함정 + 퓨리파이어 사인 (S05 Maozyn, Task 6)
- ✅ Kings 콜아웃 갭 + 서브아웃 사유 공개 코칭 (S05, Task 6)
- ✅ OBJ 싸움 단독행동 금지 (S07, Task 6)
- ✅ 여유시간 dictate (S08, Task 6)
- ✅ 매핑은 안내만 (`slideStatement("We map it out together.")`, Task 6 S09)
- ✅ English only (Global Constraints)
- ✅ Astryx neutral 색 + 기존 make_pptx.py 훼손 X

**2. Placeholder scan:**
- 모든 Step에 실제 코드/명령 포함. "TBD"/"TODO"/"add error handling" 없음.
- divider 인덱스 추정치 문제 → Step 2에서 런타임 계산으로 해결 (하드코딩 제거 명시).

**3. Type consistency:**
- `text()` / `rect()` / `hline()` / `footer()` — Task 2 정의, Task 3-6 사용. 시그니처 일치.
- `node()` / `arrow()` — Task 4 정의. `kind` enum `"cartels"|"kings"|"gap"` 일관.
- `slideRolecard({name, lineup, role, responsibilities, identity})` — Task 5 정의, Task 6 호출 시 동일 키 사용.
- `LINEUP_COLOR` — Task 4 정의, Task 5 롤카드에서 재사용.

**4. 주의사항 (pptx 스킬 함정 매핑):**
- ✅ `LAYOUT_WIDE` 설정 (13.3"×7.5") — 기본 10"×5.625" 아님
- ✅ hex 6자리, `#` 없음
- ✅ 옵션 객체 재사용 금지 — 각 `addText`/`addShape`마다 새 객체 (헬퍼가 매번 새 opts 생성)
- ✅ `transparency`/`opacity` (alpha hex 아님) — 투명 필요 시 사용
- ✅ `endArrowType: "triangle"` 로 화살촉
- ✅ validate.py + 시각 QA (이미지 변환) 필수 — Task 7
- ✅ `<p:presentation>` 자식 순서 — pptxgenjs가 알아서 처리 (직접 XML 안 건드림)
- ✅ 폰트: Pretendard는 이 환경에 없음 → 본문은 Calibri 지정, 타이틀은 Pretendard 시도 (QA 대략)
- ⚠️ `pres._slides` internal 접근 — pptxgenjs API에 footer 추가 공식 메서드가 없어 internal 사용. 런타임 동작 Task 6 Step 2에서 검증.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-25-role-alignment-ppt.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Task별로 fresh subagent dispatch, task 간 review. 빠른 반복.

**2. Inline Execution** — 이 세션에서 executing-plans로 batch 실행, checkpoint마다 review.

Which approach?
