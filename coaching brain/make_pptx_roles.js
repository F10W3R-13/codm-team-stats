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

// Total slide count is finalized after the deck content is built (see FOOTER PASS).
// Declared with `let` so it can be set to pres._slides.length once all builders ran.
let TOTAL_SLIDES = 30;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";   // 13.333 x 7.5
pres.author = "Coach";
pres.title = "Role Alignment & Tactical Model";

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
// fill === "none" → transparent (outline-only). Any other string → solid RGB.
function rect(slide, o) {
    const fillVal = o.fill === "none" ? { type: "none" } : { color: o.fill || SURFACE };
    const shapeOpts = {
        x: o.x, y: o.y, w: o.w, h: o.h,
        fill: fillVal,
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
    (slideDivider._indices = slideDivider._indices || []).push(pres._slides.length - 1);
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
    // pad arrow endpoints ~0.18" outside node edges so arrowhead triangles
    // (drawn under the node fills) remain visible in clear space.
    const PAD = 0.18;

    // gap arrow (unravel <-> Shisui) — horizontal, endpoints pulled inside the gap
    arrow(s, { x1: unr.cx + NODE_W/2 + PAD, y1: unr.cy, x2: shi.cx - NODE_W/2 - PAD, y2: shi.cy, kind: "gap", label: "TEMPO GAP — drift apart" });
    // cartels support arrows — endpoints dropped below top-node bottom edges
    arrow(s, { x1: car.cx - 0.6, y1: car.cy - NODE_H/2, x2: unr.cx + 0.4, y2: unr.cy + NODE_H/2 + PAD + 0.05, kind: "cartels", label: "support" });
    arrow(s, { x1: car.cx + 0.6, y1: car.cy - NODE_H/2, x2: shi.cx - 0.4, y2: shi.cy + NODE_H/2 + PAD + 0.05, kind: "cartels", label: "support" });

    // nodes (drawn last so they sit on top of arrows)
    node(s, { cx: unr.cx, cy: unr.cy, w: NODE_W, h: NODE_H, name: "unravel", role: "Tempo stealer · 1vX", lineup: "SMG" });
    node(s, { cx: shi.cx, cy: shi.cy, w: NODE_W, h: NODE_H, name: "Shisui",  role: "Clutch · Main SMG",   lineup: "SMG" });
    node(s, { cx: car.cx, cy: car.cy, w: NODE_W, h: NODE_H, name: "Cartels", role: "Veteran · Calibrator", lineup: "SMG" });

    // bottom note
    text(s, { x: 0.7, y: 6.5, w: 11.9, h: 0.4, text: "Cartels doesn't pull them to a midpoint. He picks the side that needs him.", size: 14, color: TEXT_2, italic: true, align: "center", font: FONT_BODY });
    return s;
}

function slideRosterDiagramAR() {
    const s = pres.addSlide();
    bgFill(s, BG);
    text(s, { x: 0.7, y: 0.8, w: 12, h: 0.4, text: "SECTION 06 · AR DUO", size: 12, color: MUTED, bold: true, font: FONT });
    text(s, { x: 0.7, y: 1.2, w: 12, h: 0.9, text: "Stay together when the OBJ fight starts.", size: 32, color: TEXT, bold: true, font: FONT_BODY });

    const NODE_W = 2.8, NODE_H = 1.4;
    const mao = { cx: 4.0, cy: 3.8 };
    const kng = { cx: 9.3, cy: 3.8 };
    // pad arrow endpoints ~0.18" outside node edges so arrowhead triangle (drawn
    // under the node fills) stays visible in the gap. Same principle as SMG diagram.
    const PAD = 0.18;

    // "stay together" red dashed box wrapping both nodes
    const boxX = mao.cx - NODE_W/2 - 0.4;
    const boxY = mao.cy - NODE_H/2 - 0.4;
    const boxW = (kng.cx + NODE_W/2) - (mao.cx - NODE_W/2) + 0.8;
    const boxH = NODE_H + 0.8;
    rect(s, { x: boxX, y: boxY, w: boxW, h: boxH, fill: "none" /*transparent*/, line: DANGER, lineW: 1.5, dashType: "dash" });
    // box label above
    text(s, { x: boxX, y: boxY - 0.35, w: boxW, h: 0.3, text: "STAY TOGETHER IN OBJ FIGHTS", size: 11, color: DANGER, bold: true, align: "center", font: FONT_BODY });

    // kings -> maozyn help arrow (Kings on right, Maozyn on left; arrow goes right→left)
    // x1 near Kings's left edge pulled into the gap, x2 near Maozyn's right edge pulled into the gap.
    arrow(s, { x1: kng.cx - NODE_W/2 - PAD, y1: kng.cy, x2: mao.cx + NODE_W/2 + PAD, y2: mao.cy, kind: "kings", label: "help him fight clean" });

    node(s, { cx: mao.cx, cy: mao.cy, w: NODE_W, h: NODE_H, name: "Maozyn", role: "Hill-close · Selfless AR", lineup: "AR" });
    node(s, { cx: kng.cx, cy: kng.cy, w: NODE_W, h: NODE_H, name: "Kings",  role: "Spine · Dictate in downtime", lineup: "AR" });

    text(s, { x: 0.7, y: 6.4, w: 11.9, h: 0.4, text: "You can split in rotation. Never split when the OBJ fight starts.", size: 14, color: TEXT_2, italic: true, align: "center", font: FONT_BODY });
    return s;
}

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
// Divider indices are recorded by slideDivider() at call time, so they stay
// correct even if slide order/count changes.
const DIVIDER_INDICES = new Set(slideDivider._indices || []);
const slideArr = Array.from(pres._slides);
TOTAL_SLIDES = slideArr.length;   // finalize the "X / N" denominator to the real count
slideArr.forEach((sl, i) => {
    if (i === 0) return;                       // title
    if (i === slideArr.length - 1) return;     // closing
    if (DIVIDER_INDICES.has(i)) return;        // divider
    footer(sl, i + 1, "Role Alignment & Tactical Model");
});

// --- write + post-write fixup ---
// pptxgenjs 4.x omits the slideMaster <Override> in [Content_Types].xml when the
// deck has zero slides, which fails OOXML content-type validation (ECMA-376).
// Once Task 2+ add slides, pptxgenjs emits the override itself and this fixup
// becomes a no-op. We patch the written file so the empty Task-1 deck validates.
const fs = require("fs");
const FILE_NAME = "역할정합서_PPT.pptx";

const SLIDE_MASTER_OVERRIDE =
    '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>';

pres.write({ outputType: "nodebuffer" })
    .then(async buf => {
        const JSZip = require("jszip");
        const zip = await JSZip.loadAsync(buf);
        const ctFile = zip.file("[Content_Types].xml");
        if (ctFile) {
            const ct = await ctFile.async("string");
            if (ct.indexOf(SLIDE_MASTER_OVERRIDE) === -1) {
                zip.file(
                    "[Content_Types].xml",
                    ct.replace("</Types>", `  ${SLIDE_MASTER_OVERRIDE}\n</Types>`)
                );
            }
        }
        const out = await zip.generateAsync({
            type: "nodebuffer",
            compression: "DEFLATE",
            compressionOptions: { level: 6 },
        });
        fs.writeFileSync(FILE_NAME, out);
        console.log("OK:", FILE_NAME);
    });
