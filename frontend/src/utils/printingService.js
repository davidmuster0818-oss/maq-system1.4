/**
 * PrintingService — adesivos térmicos.
 *
 * MÍDIA PADRÃO: bobina térmica direta de 58mm de largura com etiqueta
 * adesiva 50×30mm centralizada (4mm de liner em cada lateral).
 *
 *   |--4mm--|----- 50mm etiqueta -----|--4mm--|   ← bobina 58mm (horizontal)
 *
 * IMPORTANTE — gap entre etiquetas:
 *   O avanço entre etiquetas é controlado pelo sensor físico de gap da
 *   impressora, NÃO pelo CSS. Por isso paperH = 30mm (tamanho exato da
 *   etiqueta), sem nenhuma margem vertical extra.
 *
 * Suportado também:
 *   - '50x30-direct'  → impressora de etiqueta dedicada (papel já é 50×30mm)
 *   - '80x50'         → bobina 80×50mm
 *   - '100x50'        → bobina 100×50mm
 *   - '50x30-portrait'→ etiqueta em pé (caso alguém tenha bobina 30×50)
 *
 * Layouts:
 *   - `os`     → adesivo de OS: número + nome cliente + QR code
 *   - `store`  → adesivo da loja: logo + nome + telefone + QR pro site
 */
import QRCode from 'qrcode';

const LOGO_URL = '/assets/mastermaq-logo.png';

const SIZES = {
  '50x30': {
    paperW: 58, paperH: 30,
    contentW: 50, contentH: 30,
    marginH: 4, marginV: 0,
    orientation: 'landscape',
  },
  '50x30-direct': {
    paperW: 50, paperH: 30,
    contentW: 50, contentH: 30,
    marginH: 0, marginV: 0,
    orientation: 'landscape',
  },
  '50x30-portrait': {
    paperW: 30, paperH: 50,
    contentW: 30, contentH: 50,
    marginH: 0, marginV: 0,
    orientation: 'portrait',
  },
  '80x50': {
    paperW: 80, paperH: 50,
    contentW: 80, contentH: 50,
    marginH: 0, marginV: 0,
    orientation: 'landscape',
  },
  '100x50': {
    paperW: 100, paperH: 50,
    contentW: 100, contentH: 50,
    marginH: 0, marginV: 0,
    orientation: 'landscape',
  },
};

const getOrigin = () => (typeof window !== 'undefined' ? window.location.origin : '');

const generateQRDataURL = async (text, opts = {}) => {
  try {
    return await QRCode.toDataURL(text, {
      // 'L' (7% recovery) — gera QR com MENOS módulos (versão menor) →
      // cada módulo ocupa mais dots da impressora térmica → leitura
      // significativamente mais confiável em impressora de cupom 203 DPI.
      // Adesivo está em ambiente controlado (etiqueta sob plástico) então
      // não precisa de redundância pesada.
      errorCorrectionLevel: 'L',
      // Quiet zone: 4 módulos = padrão ISO/IEC 18004. Scanners precisam de
      // borda branca para detectar o QR. margin:0 ou margin:2 deixava o
      // adesivo "ilegível" em câmeras de iPhone/Android.
      margin: 4,
      width: 256,
      color: { dark: '#000000', light: '#FFFFFF' },
      ...opts,
    });
  } catch (_) {
    return null;
  }
};

const firstName = (full = '') => {
  const cleaned = String(full).trim().split(/\s+/);
  return cleaned[0] || '';
};

const fmtDate = (d) => {
  try {
    const dt = d ? new Date(d) : new Date();
    return dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' });
  } catch (_) {
    return '';
  }
};

/**
 * Retorna o tamanho do QR code em mm.
 * Landscape (etiqueta 50×30mm): 22mm — máximo que cabe sem invadir o texto.
 *   Com margin:4 da QR lib, o "lado útil" do QR fica ~17.6mm, dando módulos
 *   maiores e leitura mais confiável em térmica de 203 DPI.
 * Portrait: proporcional, clamp 14-26mm.
 */
const calcQrSizeMm = (contentW, contentH) => {
  const isPortrait = contentH > contentW;
  if (isPortrait) {
    const smaller = Math.min(contentW, contentH);
    return Math.min(Math.max(smaller * 0.80, 14), 26);
  }
  // Landscape: 22mm cabe direitinho na etiqueta de 30mm de altura (com 4mm
  // de respiro pra cima/baixo) e libera 26mm de largura para OS/cliente/data.
  return 22;
};

const baseStyles = (cfg) => {
  const { paperW, paperH, contentW, contentH, marginH, orientation } = cfg;
  const isPortrait = orientation === 'portrait';
  const qrMm = calcQrSizeMm(contentW, contentH);
  const gapMm = 4; // gap entre coluna de texto e QR (folga para quiet zone do QR)
  const leftW = contentW - qrMm - gapMm;

  return `
@page { size: ${paperW}mm ${paperH}mm ${isPortrait ? 'portrait' : 'landscape'}; margin: 0; }
@page :first { size: ${paperW}mm ${paperH}mm ${isPortrait ? 'portrait' : 'landscape'}; margin: 0; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body { margin: 0 !important; padding: 0 !important; font-family: 'Helvetica Neue', Arial, sans-serif; color: #000; background: #fff; width: ${paperW}mm; }
body { width: ${paperW}mm; }

.page {
  width: ${paperW}mm;
  height: ${paperH}mm;
  padding: 0;
  margin: 0;
  overflow: hidden;
  page-break-after: always;
  break-after: page;
  page-break-inside: avoid;
  break-inside: avoid;
}
.page:last-child { page-break-after: auto; break-after: auto; }

.label {
  width: ${contentW}mm;
  height: ${contentH}mm;
  margin-top: 0;
  padding-right: 2mm;
  margin-left: ${marginH}mm;
  display: flex;
  flex-direction: ${isPortrait ? 'column' : 'row'};
  justify-content: space-between;
  align-items: center;
}

.label .left {
  width: ${isPortrait ? contentW : leftW}mm;
  overflow: hidden;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.8mm;
  height: ${contentH}mm;
}

.label .right {
  width: ${isPortrait ? contentW : qrMm}mm;
  display: flex;
  justify-content: center;
  align-items: center;
  height: ${contentH}mm;
}
/* image-rendering: pixelated desliga anti-aliasing do driver da impressora.
   Sem isso, a térmica suaviza as bordas dos módulos do QR e produz um
   desenho borrado que muitos scanners não conseguem ler. */
.label .right img { display: block; image-rendering: pixelated; image-rendering: -moz-crisp-edges; image-rendering: crisp-edges; }

/* FIX: os-num aumentado de 3mm para 5mm para ser legível na etiqueta térmica */
.os-num { font-size: ${isPortrait ? '5.5mm' : '5mm'}; font-weight: 900; line-height: 1; letter-spacing: -0.3px; }
.client { font-size: ${isPortrait ? '2.8mm' : '2.6mm'}; font-weight: 700; line-height: 1.15; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.date   { font-size: ${isPortrait ? '2.2mm' : '2.2mm'}; font-weight: 500; color: #333; line-height: 1; }

@media print {
  html, body { width: ${paperW}mm; }
  body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
`;
};

export async function printOSLabel(order, { size = '50x30', qrToken = null } = {}) {
  const cfg = SIZES[size] || SIZES['50x30'];
  const origin = getOrigin();

  // QR encoded as ALPHANUMERIC (uppercase) → forces the qrcode lib into
  // alphanumeric mode (more efficient than binary), producing a smaller QR.
  //   • 'https://…/os-view/27691'  → 48 chars binary  → Version 3 (29×29 mod)
  //   • 'HTTPS://…/O/27691'        → 42 chars alpha   → Version 2 (25×25 mod)
  // At fixed 22mm physical size, V2 modules are ~30% larger than V3, which
  // makes the thermal-printed adesivo dramatically more legible by phone
  // cameras. The short path /o/:osNumber is mounted in App.js and just
  // forwards to OSQrRedirectPage (same handler as /os/:osNumber).
  // Note: protocol/domain are case-insensitive on the wire; only the path
  // is case-sensitive. React Router matches paths case-insensitively by
  // default, so '/O/27691' resolves the same as '/o/27691'.
  const qrPayload = `${origin}/o/${order.os_number}`.toUpperCase();

  const qrSizeMm = calcQrSizeMm(cfg.contentW, cfg.contentH);
  // Hi-res for thermal printer crispness (12px per mm ≈ 305 DPI).
  const qrPixelSize = Math.round(qrSizeMm * 12);
  const qrDataUrl = await generateQRDataURL(qrPayload, { width: qrPixelSize });
  const clientName = (firstName(order.customer_name) + ' ' + (order.customer_name?.split(' ').slice(1, 2).join(' ') || '')).trim();

  const html = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Imprimir adesivo OS ${order.os_number}</title>
<style>${baseStyles(cfg)}

/* Screen-only test panel — hidden from print.
   Shows the QR enlarged + URL so the user can test scanning directly from
   the monitor BEFORE printing. The actual print output is unchanged. */
@media screen {
  body { background: #f3f4f6; padding: 24px; }
  .screen-test {
    background: white; padding: 28px; border-radius: 12px; max-width: 380px;
    margin: 0 auto 24px; box-shadow: 0 4px 24px rgba(0,0,0,.08);
    font-family: 'Helvetica Neue', Arial, sans-serif; text-align: center;
  }
  .screen-test h2 { margin: 0 0 12px; font-size: 16px; color: #111; }
  .screen-test .qr-big { width: 220px; height: 220px; image-rendering: pixelated;
    image-rendering: -moz-crisp-edges; image-rendering: crisp-edges;
    display: block; margin: 0 auto 12px; }
  .screen-test .url { font-family: ui-monospace, Consolas, monospace; font-size: 11px;
    color: #2563eb; word-break: break-all; padding: 8px 12px;
    background: #eff6ff; border-radius: 6px; margin: 8px 0; }
  .screen-test .hint { font-size: 12px; color: #6b7280; line-height: 1.4;
    border-top: 1px solid #e5e7eb; padding-top: 12px; margin-top: 12px; }
  .screen-test .btn { background: #111; color: white; padding: 10px 18px;
    border: 0; border-radius: 6px; cursor: pointer; font-size: 13px;
    margin-top: 8px; font-weight: 600; }
  .screen-test .btn:hover { background: #374151; }
  /* Show the actual print preview at 3x on screen so user can see what
     will be printed without zooming */
  .page { transform: scale(3); transform-origin: top center; margin: 8mm auto 90mm; }
}
@media print {
  .screen-test { display: none !important; }
  .page { transform: none; margin: 0; }
}
</style></head>
<body>
  <div class="screen-test">
    <h2>Adesivo da OS ${order.os_number}</h2>
    <img class="qr-big" src="${qrDataUrl || ''}" alt="QR (tamanho ampliado para teste)" />
    <div class="url">${qrPayload}</div>
    <div class="hint">QR ampliado para teste na tela. Aponte a câmera do celular agora para validar a leitura. Após o teste, clique em <strong>Imprimir</strong>.</div>
    <button class="btn" onclick="window.print()" data-testid="print-button">Imprimir</button>
  </div>

  <div class="page">
    <div class="label">
      <div class="left">
        <div class="os-num">OS ${order.os_number}</div>
        <div class="client">${clientName}</div>
        <div class="date">Data: ${fmtDate(order.created_at)}</div>
      </div>
      <div class="right">
        ${qrDataUrl ? `<img src="${qrDataUrl}" style="width:${qrSizeMm}mm;height:${qrSizeMm}mm;image-rendering:pixelated;" alt="QR" />` : ''}
      </div>
    </div>
  </div>
  <script>
    // No auto-print: user clicks "Imprimir" after visually verifying the QR.
    // (Auto-print was triggering Chrome's dialog before the QR finished
    // loading, and prevented on-screen scan testing.)
    window.onafterprint = function() { setTimeout(function(){ try { window.close(); } catch(e){} }, 200); };
  </script>
</body></html>`;

  openPrintWindow(html);
}

export async function printStoreLabel({ size = '50x30', config = {}, copies = 1 } = {}) {
  const cfg = SIZES[size] || SIZES['50x30'];
  const storeName = config.storeName || 'Mastermaq Assistência Técnica';
  const phones = config.phones || ['(31) 3422-5293', '(31) 2526-8420'];
  const siteUrl = config.siteUrl || 'https://mastermaqassistencia.com.br';

  const qrSizeMm = calcQrSizeMm(cfg.contentW, cfg.contentH);
  const qrPixelSize = Math.round(qrSizeMm * 12);
  const qrDataUrl = await generateQRDataURL(siteUrl, { width: qrPixelSize });

  const n = Math.max(1, Math.min(500, Number(copies) || 1));
  const isPortrait = cfg.orientation === 'portrait';

  const oneLabel = `
  <div class="page">
    <div class="label">
      <div class="left">
        <div class="logo-row">
          <img src="${LOGO_URL}" alt="Mastermaq" />
          <div class="store-name">${storeName.split(' ')[0]}</div>
        </div>
        <div>
          <div class="phones">${phones.join('<br/>')}</div>
          <div class="site">${siteUrl.replace(/^https?:\/\//, '')}</div>
        </div>
      </div>
      <div class="right">
        ${qrDataUrl ? `<img src="${qrDataUrl}" style="width:${qrSizeMm}mm;height:${qrSizeMm}mm;image-rendering:pixelated;" alt="QR" />` : ''}
      </div>
    </div>
  </div>`;

  const labels = Array.from({ length: n }, () => oneLabel).join('');

  const html = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title></title>
<style>${baseStyles(cfg)}
.store-name { font-size: ${isPortrait ? '3mm' : '3.4mm'}; font-weight: 800; line-height: 1.05; letter-spacing: -0.2px; }
.phones { font-size: ${isPortrait ? '2.1mm' : '2.4mm'}; font-weight: 700; line-height: 1.15; margin-top: 0.5mm; }
.site { font-size: ${isPortrait ? '1.8mm' : '2mm'}; color: #555; margin-top: 0.5mm; }
.logo-row { display: flex; align-items: center; gap: 1mm; }
.logo-row img { height: ${isPortrait ? '4mm' : '4.5mm'}; }
</style></head>
<body>
  ${labels}
  <script>
    (function() {
      function doPrint() { try { window.focus(); window.print(); } catch(e){} }
      window.onafterprint = function() { setTimeout(function(){ try { window.close(); } catch(e){} }, 200); };
      var imgs = Array.from(document.images);
      if (imgs.length === 0) { setTimeout(doPrint, 200); return; }
      var pending = imgs.length;
      imgs.forEach(function(img) {
        if (img.complete) { if (--pending === 0) setTimeout(doPrint, 100); }
        else {
          img.onload = img.onerror = function() { if (--pending === 0) setTimeout(doPrint, 100); };
        }
      });
      setTimeout(doPrint, 3000);
    })();
  </script>
</body></html>`;

  openPrintWindow(html);
}

function openPrintWindow(html) {
  const w = window.open('', '_blank', 'width=520,height=420');
  if (!w) {
    alert('Por favor permita popups para imprimir o adesivo.');
    return;
  }
  w.document.open();
  w.document.write(html);
  w.document.close();
}

export const LABEL_SIZES = Object.keys(SIZES);

/**
 * Imprime um adesivo com conteúdo CUSTOMIZADO (imagem PNG) —
 * usado pelo editor de templates (LabelTemplatesPage). Reusa exatamente
 * a mesma geometria física dos adesivos de OS/Produto:
 *   • paper = bobina real (58×30mm, 80×50mm, 100×50mm)
 *   • orientação landscape/portrait correta
 *   • margem lateral (4mm de liner na bobina 58mm)
 *   • @page + page-break-after para NÃO passar várias etiquetas por impressão
 *
 * Antes, o LabelTemplatesPage usava `@page { size: 50mm 30mm }` sem
 * orientação nem margem, o que fazia a impressora térmica alinhar o
 * conteúdo em pé, fora da margem, e cuspir várias etiquetas em branco
 * até uma sair correta.
 *
 * O que essa função espera:
 *   - `pngDataUrl`: exportação do canvas do fabric.js já no tamanho do
 *     conteúdo (contentW × contentH mm), 3x multiplier para nitidez.
 *   - `sizeKey`: uma chave conhecida de SIZES ('50x30', '80x50', ...).
 *     Se o template tiver dimensões custom, chame com contentW/contentH
 *     via `customContent`.
 */
export function printCustomLabel(pngDataUrl, { sizeKey = '50x30', customContent = null, name = 'Adesivo' } = {}) {
  let cfg = SIZES[sizeKey];
  if (!cfg && customContent) {
    // Dimensões livres — assume papel = conteúdo, sem liner.
    const isPortrait = customContent.h > customContent.w;
    cfg = {
      paperW: customContent.w, paperH: customContent.h,
      contentW: customContent.w, contentH: customContent.h,
      marginH: 0, marginV: 0,
      orientation: isPortrait ? 'portrait' : 'landscape',
    };
  }
  if (!cfg) cfg = SIZES['50x30'];

  const { paperW, paperH, contentW, contentH, marginH, orientation } = cfg;
  const isPortrait = orientation === 'portrait';

  // MESMO padrão CSS de printOSLabel/printProductLabel — garante que a
  // impressora térmica reconheça o adesivo (58mm de bobina, 4mm de liner)
  // e alinhe o conteúdo dentro do 50×30mm útil.
  const html = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>${name}</title>
<style>
@page { size: ${paperW}mm ${paperH}mm ${isPortrait ? 'portrait' : 'landscape'}; margin: 0; }
@page :first { size: ${paperW}mm ${paperH}mm ${isPortrait ? 'portrait' : 'landscape'}; margin: 0; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body { margin: 0 !important; padding: 0 !important; background: #fff; width: ${paperW}mm; }
body { width: ${paperW}mm; }
.page {
  width: ${paperW}mm;
  height: ${paperH}mm;
  padding: 0;
  margin: 0;
  overflow: hidden;
  page-break-after: always;
  break-after: page;
  page-break-inside: avoid;
  break-inside: avoid;
}
.page:last-child { page-break-after: auto; break-after: auto; }
.label {
  width: ${contentW}mm;
  height: ${contentH}mm;
  margin-left: ${marginH}mm;
  overflow: hidden;
}
.label img {
  display: block;
  width: ${contentW}mm;
  height: ${contentH}mm;
  image-rendering: pixelated;
  image-rendering: -moz-crisp-edges;
  image-rendering: crisp-edges;
}
@media screen {
  body { background: #f3f4f6; padding: 24px; font-family: 'Helvetica Neue', Arial, sans-serif; }
  .screen-test { background: white; padding: 20px; border-radius: 12px; max-width: 420px;
    margin: 0 auto 24px; box-shadow: 0 4px 24px rgba(0,0,0,.08); text-align: center; }
  .screen-test h2 { margin: 0 0 12px; font-size: 15px; color: #111; }
  .screen-test .hint { font-size: 12px; color: #6b7280; line-height: 1.4;
    border-top: 1px solid #e5e7eb; padding-top: 12px; margin-top: 12px; }
  .screen-test .btn { background: #111; color: white; padding: 10px 18px;
    border: 0; border-radius: 6px; cursor: pointer; font-size: 13px;
    margin-top: 8px; font-weight: 600; }
  .screen-test .btn:hover { background: #374151; }
  .preview { border: 1px dashed #cbd5e1; padding: 8px; margin: 0 auto 12px;
    background: #fff; display: inline-block; }
  .page { transform: scale(3); transform-origin: top center; margin: 8mm auto 90mm; }
}
@media print {
  .screen-test { display: none !important; }
  .page { transform: none; margin: 0; }
}
</style></head>
<body>
  <div class="screen-test">
    <h2>${name} — ${contentW}×${contentH}mm</h2>
    <div class="preview"><img src="${pngDataUrl}" alt="preview" style="width:${contentW * 3}mm;height:${contentH * 3}mm;" /></div>
    <div class="hint">Preview do adesivo em tamanho 3×. Após conferir, clique em <strong>Imprimir</strong>. Só 1 adesivo por impressão — o gap entre etiquetas é controlado pelo sensor da impressora.</div>
    <button class="btn" onclick="window.print()" data-testid="print-button">Imprimir</button>
  </div>

  <div class="page">
    <div class="label">
      <img src="${pngDataUrl}" alt="${name}" />
    </div>
  </div>
  <script>
    window.onafterprint = function() { setTimeout(function(){ try { window.close(); } catch(e){} }, 200); };
  </script>
</body></html>`;

  openPrintWindow(html);
}

/**
 * Imprime um adesivo térmico para um PRODUTO de estoque.
 *
 * Reusa exatamente o mesmo motor da `printOSLabel`:
 *   • mesmo tamanho 50×30mm (com 4mm de liner em cada lateral em bobina 58mm)
 *   • QR code Versão 2 (25×25 mod) em ALPHANUMERIC mode → módulos grandes,
 *     leitura confiável em impressora 203 DPI / câmera de celular
 *   • payload curto `/P/:CODE` em UPPERCASE para forçar modo alphanumeric
 *   • mesmo screen-test panel antes da impressão para validar a leitura
 *
 * O QR aponta para uma página pública que NÃO exige login e mostra apenas:
 *   categoria, nome, marca, modelo, unidade, preço de venda.
 */
export async function printProductLabel(product, { size = '50x30' } = {}) {
  const cfg = SIZES[size] || SIZES['50x30'];
  const origin = getOrigin();
  const code = (product?.code || '').toString();
  // Short alphanumeric path so the QR stays at Version 2 (25×25) — same
  // optimization as printOSLabel for thermal printing legibility.
  const qrPayload = `${origin}/p/${encodeURIComponent(code)}`.toUpperCase();

  const qrSizeMm = calcQrSizeMm(cfg.contentW, cfg.contentH);
  const qrPixelSize = Math.round(qrSizeMm * 12);
  const qrDataUrl = await generateQRDataURL(qrPayload, { width: qrPixelSize });

  const name = (product?.name || '').toString();
  const priceNum = Number(product?.sale_price || 0);
  const priceStr = priceNum > 0
    ? priceNum.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
    : '';
  // Brand/model line — falls back gracefully when one is missing
  const brand = (product?.brand || '').trim();
  const model = (product?.model || '').trim();
  const subline = [brand, model].filter(Boolean).join(' · ');

  const html = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Imprimir adesivo Produto ${code}</title>
<style>${baseStyles(cfg)}
/* Override font sizes for product label — name takes the place of OS number
   so use the same prominent 5mm. Subline (brand · model) uses the 'client'
   style and price uses the 'date' slot but bolder. */
.prod-cat  { font-size: 3.0mm; font-weight: 800; color: #444; line-height: 1.05; text-transform: uppercase; letter-spacing: 0.3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 0.4mm; }
.prod-name { font-size: 3.6mm; font-weight: 900; line-height: 1.05; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  text-overflow: ellipsis; }
.prod-sub  { font-size: 2.4mm; font-weight: 600; color: #333; line-height: 1.15;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prod-price { font-size: 3.2mm; font-weight: 900; line-height: 1; letter-spacing: -0.2px; }
.prod-code { font-size: 1.8mm; font-weight: 500; color: #555; line-height: 1; font-family: ui-monospace, Consolas, monospace; }

@media screen {
  body { background: #f3f4f6; padding: 24px; }
  .screen-test {
    background: white; padding: 28px; border-radius: 12px; max-width: 380px;
    margin: 0 auto 24px; box-shadow: 0 4px 24px rgba(0,0,0,.08);
    font-family: 'Helvetica Neue', Arial, sans-serif; text-align: center;
  }
  .screen-test h2 { margin: 0 0 12px; font-size: 16px; color: #111; }
  .screen-test .qr-big { width: 220px; height: 220px; image-rendering: pixelated;
    image-rendering: -moz-crisp-edges; image-rendering: crisp-edges;
    display: block; margin: 0 auto 12px; }
  .screen-test .url { font-family: ui-monospace, Consolas, monospace; font-size: 11px;
    color: #2563eb; word-break: break-all; padding: 8px 12px;
    background: #eff6ff; border-radius: 6px; margin: 8px 0; }
  .screen-test .hint { font-size: 12px; color: #6b7280; line-height: 1.4;
    border-top: 1px solid #e5e7eb; padding-top: 12px; margin-top: 12px; }
  .screen-test .btn { background: #111; color: white; padding: 10px 18px;
    border: 0; border-radius: 6px; cursor: pointer; font-size: 13px;
    margin-top: 8px; font-weight: 600; }
  .screen-test .btn:hover { background: #374151; }
  .page { transform: scale(3); transform-origin: top center; margin: 8mm auto 90mm; }
}
@media print {
  .screen-test { display: none !important; }
  .page { transform: none; margin: 0; }
}
</style></head>
<body>
  <div class="screen-test">
    <h2>Adesivo do Produto ${code}</h2>
    <img class="qr-big" src="${qrDataUrl || ''}" alt="QR (tamanho ampliado para teste)" />
    <div class="url">${qrPayload}</div>
    <div class="hint">QR ampliado para teste. Aponte a câmera do celular agora para validar a leitura. Após o teste, clique em <strong>Imprimir</strong>.</div>
    <button class="btn" onclick="window.print()" data-testid="print-button">Imprimir</button>
  </div>

  <div class="page">
    <div class="label">
      <div class="left">
        ${product?.category ? `<div class="prod-cat">${product.category}</div>` : ''}
        <div class="prod-name">${name}</div>
        ${subline ? `<div class="prod-sub">${subline}</div>` : ''}
        ${priceStr ? `<div class="prod-price">${priceStr}</div>` : ''}
        <div class="prod-code">${code}</div>
      </div>
      <div class="right">
        ${qrDataUrl ? `<img src="${qrDataUrl}" style="width:${qrSizeMm}mm;height:${qrSizeMm}mm;image-rendering:pixelated;" alt="QR" />` : ''}
      </div>
    </div>
  </div>
  <script>
    window.onafterprint = function() { setTimeout(function(){ try { window.close(); } catch(e){} }, 200); };
  </script>
</body></html>`;

  openPrintWindow(html);
}