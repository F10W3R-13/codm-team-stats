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

// (slides added in Tasks 3-8)

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
