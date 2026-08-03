const pptxgen = require('pptxgenjs');
const pres = new pptxgen();

// 포스터 사이즈 (16:9 비율, 넓게)
pres.layout = 'LAYOUT_WIDE'; // 13.33" x 7.5"
const slide = pres.addSlide();

// 다크 그라데이션 배경 (이미지 대신 단색 + 오버레이)
slide.background = { color: '0F0F0F' };

// 상단 트로피 라벨
slide.addText('🏆 TOURNAMENT MVP', {
    x: 0, y: 0.6, w: '100%', h: 0.6,
    align: 'center', valign: 'middle',
    fontSize: 18, bold: true, color: 'F59E0B',
    charSpacing: 8, fontFace: 'Arial',
});

// MVP 닉네임 — 대문짝만하게
slide.addText('LoseJai', {
    x: 0.5, y: 1.6, w: 12.33, h: 2.2,
    align: 'center', valign: 'middle',
    fontSize: 96, bold: true, color: 'F97316',
    fontFace: 'Arial Black',
});

// 소속팀
slide.addText('4uNion', {
    x: 0, y: 3.8, w: '100%', h: 0.6,
    align: 'center', valign: 'middle',
    fontSize: 28, bold: true, color: 'A3A3A3',
    fontFace: 'Arial',
});

// 간단 스탯 (ZCS 제외) — 3개 블록, 중앙 정렬
const statY = 4.6;
const statW = 2.6;
const gap = 0.4;
const totalW = statW * 3 + gap * 2;  // 8.6
const startX = (13.33 - totalW) / 2;  // 2.365

// RDS
slide.addText('72.87', {
    x: startX, y: statY, w: statW, h: 0.6,
    align: 'center', valign: 'bottom',
    fontSize: 38, bold: true, color: '8B5CF6',
    fontFace: 'Arial',
});
slide.addText('avg RDS', {
    x: startX, y: statY + 0.6, w: statW, h: 0.35,
    align: 'center', valign: 'top',
    fontSize: 12, color: '737373',
    fontFace: 'Arial', charSpacing: 3,
});

// K/D
slide.addText('1.57', {
    x: startX + statW + gap, y: statY, w: statW, h: 0.6,
    align: 'center', valign: 'bottom',
    fontSize: 38, bold: true, color: 'FFFFFF',
    fontFace: 'Arial',
});
slide.addText('K / D', {
    x: startX + statW + gap, y: statY + 0.6, w: statW, h: 0.35,
    align: 'center', valign: 'top',
    fontSize: 12, color: '737373',
    fontFace: 'Arial', charSpacing: 3,
});

// 경기 수
slide.addText('7', {
    x: startX + (statW + gap) * 2, y: statY, w: statW, h: 0.6,
    align: 'center', valign: 'bottom',
    fontSize: 38, bold: true, color: 'FFFFFF',
    fontFace: 'Arial',
});
slide.addText('경기 출전 (HP4 · SND3)', {
    x: startX + (statW + gap) * 2, y: statY + 0.6, w: statW, h: 0.35,
    align: 'center', valign: 'top',
    fontSize: 12, color: '737373',
    fontFace: 'Arial', charSpacing: 3,
});

// 하단 우승팀 정보
slide.addText('CHAMPION 4uNion  ·  세트 10-0', {
    x: 0, y: 6.8, w: '100%', h: 0.5,
    align: 'center', valign: 'middle',
    fontSize: 14, color: '525252',
    fontFace: 'Arial', charSpacing: 5,
});

pres.writeFile({ fileName: 'mvp_poster.pptx' })
    .then(name => console.log('생성:', name));
