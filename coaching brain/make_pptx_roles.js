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
