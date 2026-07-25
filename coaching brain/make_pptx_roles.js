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
