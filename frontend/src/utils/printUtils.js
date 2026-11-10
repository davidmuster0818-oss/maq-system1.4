import axios from 'axios';
import html2pdf from 'html2pdf.js';

const MASTERMAQ_LOGO = '/assets/mastermaq-logo.png';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

export const buildCopyHtml = (order, sigData = null) => {
  const qrImgUrl = `${window.location.origin}/assets/qr-code.png`;
  const logoUrl = `${window.location.origin}${MASTERMAQ_LOGO}`;
  const formatPhone = (phone) => {
    if (!phone) return '';
    const clean = phone.replace(/\D/g, '');
    if (clean.length === 11) return `(${clean.slice(0,2)}) ${clean.slice(2,7)}-${clean.slice(7)}`;
    if (clean.length === 10) return `(${clean.slice(0,2)}) ${clean.slice(2,6)}-${clean.slice(6)}`;
    return phone;
  };
  const formatDatePrint = (dateStr) => {
    if (!dateStr) return '';
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateStr)) return dateStr;
    const isoMatch = dateStr.match(/^(\d{4})[-/](\d{2})[-/](\d{2})/);
    if (isoMatch) return `${isoMatch[3]}/${isoMatch[2]}/${isoMatch[1]}`;
    return dateStr;
  };
  const mapServiceType = (type) => {
    if (!type) return '';
    const t = String(type).trim();
    const lc = t.toLowerCase();
    if (lc === 'orcamento' || lc === 'orçamento') return 'Orçamento';
    if (lc === 'instalação' || lc === 'instalacao') return 'Orçamento';
    if (lc === 'contrato') return 'Garantia de Loja';
    if (lc === 'fora de garantia') return 'Fora de Garantia';
    return t;
  };
  const U = (val) => val ? String(val).toUpperCase() : '';
  const contacts = [formatPhone(order.phone1), formatPhone(order.phone2), formatPhone(order.landline)].filter(Boolean).join('&nbsp;&nbsp;&nbsp;');
  const addressFull = [order.address, order.number, order.complement].filter(Boolean).join(', ');
  const isTelecontrol = order.source === 'telecontrol' || order.source === 'telecontrol_hisense' || order.source === 'telecontrol_hq';
  const telecontrolLabel = order.source === 'telecontrol_hq' ? 'TELECONTROL HQ' : 'TELECONTROL HISENSE';
  const printDate = formatDatePrint(order.attendance_date || order.registration_date || '');
  const printServiceType = mapServiceType(order.service_type);

  return `
    <div style="border:2px solid #000;font-size:11px;line-height:1.5;height:100%;box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;">
      <div style="display:flex;border-bottom:2px solid #000;padding:4px 6px;">
        <div style="width:22%;padding:2px;display:flex;align-items:center;justify-content:center;"><img style="max-width:90%;max-height:54px;" src="${logoUrl}" onerror="this.style.display='none'" /></div>
        <div style="width:36%;padding:3px;font-size:10px;line-height:1.4;">
          <div style="margin-bottom:2px;"><strong>MASTERMAQ ASSIST&Ecirc;NCIA T&Eacute;CNICA EIRELI</strong></div>
          <div>RUA DESCALVADO 636A - RENASCEN&Ccedil;A</div>
          <div>BELO HORIZONTE - MG | CNPJ 19.955.560/0001-28</div>
          <div>(31) 3422-5293 | (31) 2526-8420</div>
        </div>
        <div style="width:22%;padding:3px;">
          <div><strong style="font-size:13px;">ORDEM DE SERVI&Ccedil;O</strong></div>
          <div style="margin-top:2px;"><strong style="font-size:19px;">N&ordm; OS: ${order.os_number || ''}</strong></div>
          ${isTelecontrol ? `<div style="font-size:10px;font-weight:bold;margin-top:2px;">${telecontrolLabel}</div>` : ''}
        </div>
        <div style="width:20%;text-align:center;padding:3px;display:flex;flex-direction:column;align-items:center;justify-content:center;">
          <img src="${qrImgUrl}" style="width:20mm;height:20mm;" />
          <div style="font-size:8px;font-weight:bold;margin-top:2px;line-height:1.2;">AVALIE O ATENDIMENTO</div>
        </div>
      </div>
      <div style="display:flex;border-bottom:1px solid #000;padding:4px 6px;line-height:1.5;">
        <div style="width:62%;padding:2px 3px;">
          <div style="margin-bottom:2px;"><strong>CLIENTE: </strong>${U(order.customer_name)}</div>
          <div style="margin-bottom:2px;"><strong>ENDERE&Ccedil;O: </strong>${U(addressFull)}</div>
          <div style="margin-bottom:2px;"><strong>BAIRRO: </strong>${U(order.neighborhood)}</div>
          <div style="margin-bottom:2px;"><strong>CONTATO(S): </strong>${contacts}</div>
          <div><strong>REFERENCIA: </strong>${U(order.reference_point)}</div>
        </div>
        <div style="width:38%;padding:2px 3px;">
          <div style="margin-bottom:2px;"><strong>DATA: </strong>${printDate}</div>
          <div style="margin-bottom:2px;"><strong>CIDADE: </strong>${U(order.city)}</div>
          <div style="margin-bottom:2px;"><strong>ESTADO: </strong>${U(order.state)}</div>
          <div style="margin-bottom:2px;"><strong>EMAIL: </strong>${U(order.email)}</div>
          <div><strong>CEP: </strong>${order.cep || ''}</div>
        </div>
      </div>
      <div style="display:flex;border-bottom:1px solid #000;padding:4px 6px;text-align:center;">
        <div style="flex:1;padding:2px 3px;"><strong>PRODUTO</strong><br/>${U(order.product)}</div>
        <div style="flex:1;padding:2px 3px;"><strong>TIPO ATENDIMENTO</strong><br/>${U(printServiceType)}</div>
        <div style="flex:1;padding:2px 3px;"><strong>MARCA</strong><br/>${U(order.brand)}</div>
        <div style="flex:1;padding:2px 3px;"><strong>MODELO</strong><br/>${U(order.model)}</div>
      </div>
      <div style="display:flex;border-bottom:1px solid #000;padding:4px 6px;">
        <div style="width:30%;padding:2px 3px;"><strong>TAXA DE VISITA: </strong>${order.visit_fee != null && order.visit_fee !== '' ? 'R$ ' + Number(order.visit_fee).toFixed(2) : ''}</div>
        <div style="width:70%;padding:2px 3px;"><strong>OBSERVA&Ccedil;&Otilde;ES: </strong>${U(order.observations)}</div>
      </div>
      <div style="border-bottom:1px solid #000;padding:4px 6px;"><strong>DEFEITO: </strong>${U(order.reported_defect)}</div>
      <div style="padding:4px 6px;flex:1;display:flex;flex-direction:column;min-height:0;">
        <div style="margin-bottom:4px;"><strong style="font-size:11px;">OBSERVA&Ccedil;&Otilde;ES T&Eacute;CNICAS:</strong>${order.technical_diagnosis ? ' ' + U(order.technical_diagnosis) : ''}</div>
        <div style="border-top:1px solid #000;margin-top:20px;"></div>
        <div style="border-top:1px solid #000;margin-top:20px;"></div>
        <div style="border-top:1px solid #000;margin-top:20px;"></div>
        <div style="border-top:1px solid #000;margin-top:20px;"></div>
      </div>
      <div style="padding:4px 6px;">
        <div style="display:flex;gap:8px;margin-bottom:10px;padding-right:12px;">
          <div style="flex:1;font-size:10px;"><strong>Signat&aacute;rio: </strong>${order.signature_client_name || ''}</div>
          <div style="font-size:10px;padding-right:8px;"><strong>CPF: </strong>${order.signature_client_cpf || ''}</div>
        </div>
        <div style="display:flex;">
          <div style="flex:1;text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;">${sigData?.signature_client ? `<img src="${sigData.signature_client}" style="height:36px;object-fit:contain;display:block;margin:0 auto 2px;" />` : '<div style="height:36px;"></div>'}<div style="border-top:1px solid #000;width:80%;"></div><div style="font-size:9px;margin-top:3px;"><strong>(ASSINATURA DO CLIENTE)</strong></div></div>
          <div style="flex:1;text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;">${sigData?.signature_technician ? `<img src="${sigData.signature_technician}" style="height:36px;object-fit:contain;display:block;margin:0 auto 2px;" />` : '<div style="height:36px;"></div>'}<div style="border-top:1px solid #000;width:80%;"></div><div style="font-size:9px;margin-top:3px;"><strong>(ASSINATURA DO T&Eacute;CNICO)</strong></div></div>
        </div>
      </div>
      <div style="font-size:8px;padding:3px 6px;text-align:center;border-top:1px solid #ccc;"><strong>OR&Ccedil;AMENTO V&Aacute;LIDO POR 30 DIAS E GARANTIA DE SERVI&Ccedil;O DE 90 DIAS. PRODUTOS N&Atilde;O PROCURADOS EM 30 DIAS CORRIDOS SER&Atilde;O DESCARTADOS.</strong></div>
    </div>`;
};

export const printOS = (order, sigData = null) => {
  const copyHtml = buildCopyHtml(order, sigData);
  // Uma única cópia por página (usuário confirmou 30/09/2026 — pedia
  // "somente uma cópia, não o documento completo"). O separador
  // tracejado e a segunda cópia foram removidos.
  const printContent = `<!DOCTYPE html><html><head><meta charset="utf-8"/><title></title><style>@page{size:A4;margin:0;}html,body{margin:0;padding:0;font-family:Arial,sans-serif;}.print-page{width:210mm;min-height:297mm;padding:10mm;box-sizing:border-box;margin:0;}.copy{width:190mm;}</style></head><body><div class="print-page"><div class="copy">${copyHtml}</div></div></body></html>`;

  const existingFrame = document.getElementById('mastermaq-print-frame');
  if (existingFrame) { try { existingFrame.parentNode.removeChild(existingFrame); } catch (_) {} }

  const iframe = document.createElement('iframe');
  iframe.id = 'mastermaq-print-frame';
  iframe.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:0;height:0;border:none;';
  document.body.appendChild(iframe);

  const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
  iframeDoc.open();
  iframeDoc.write(printContent);
  iframeDoc.close();

  // Só imprime depois que logo e QR code carregarem (senão saem em branco)
  const imgs = Array.from(iframeDoc.images);
  const loaded = imgs.map((img) => (img.complete && img.naturalWidth ? Promise.resolve() : new Promise((res) => {
    img.addEventListener('load', res, { once: true });
    img.addEventListener('error', res, { once: true });
  })));
  const timeout = new Promise((res) => setTimeout(res, 5000));
  Promise.race([Promise.all(loaded), timeout]).then(() => {
    setTimeout(() => {
      try { iframe.contentWindow.focus(); iframe.contentWindow.print(); } catch(e) { console.error('Print error:', e); }
    }, 150);
  });
};

export const sendWhatsAppCopy = async (order, sigData = null, toast) => {
  const phone = (order.phone1 || '').replace(/\D/g, '');
  if (!phone) {
    if (toast) toast.error('Nenhum telefone cadastrado para este cliente');
    return;
  }
  const phoneNum = phone.startsWith('55') ? phone : `55${phone}`;

  if (toast) toast.loading('Gerando PDF da OS...', { id: 'wa-copy' });

  let pdfBase64 = null;
  let pdfBlob = null;
  let wrapper = null;
  try {
    const copyHtml = buildCopyHtml(order, sigData);
    wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:fixed;top:0;left:0;width:210mm;min-height:148mm;background:#fff;z-index:-1;opacity:0;pointer-events:none';
    const inner = document.createElement('div');
    inner.style.cssText = 'width:210mm;min-height:148mm;padding:8mm;box-sizing:border-box;font-family:Arial,sans-serif;font-size:11px;background:#fff;';
    inner.innerHTML = copyHtml;
    wrapper.appendChild(inner);
    document.body.appendChild(wrapper);

    // Wait for images to load
    const imgs = Array.from(wrapper.querySelectorAll('img'));
    await Promise.all(imgs.map(img => {
      if (img.complete && img.naturalHeight !== 0) return Promise.resolve();
      return new Promise(resolve => {
        const done = () => resolve();
        img.addEventListener('load', done, { once: true });
        img.addEventListener('error', done, { once: true });
        setTimeout(done, 3000);
      });
    }));
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

    pdfBlob = await html2pdf().from(inner).set({
      margin: 0,
      filename: `OS_${order.os_number}.pdf`,
      image: { type: 'jpeg', quality: 0.92 },
      html2canvas: {
        scale: 2, useCORS: true, allowTaint: true, logging: false,
        backgroundColor: '#ffffff',
        windowWidth: inner.scrollWidth,
        windowHeight: inner.scrollHeight,
      },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
    }).output('blob');

    pdfBase64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(pdfBlob);
    });
  } catch (err) {
    if (toast) toast.error('Não foi possível gerar o PDF da OS', { id: 'wa-copy' });
    console.error('PDF generation error:', err);
    if (wrapper && wrapper.parentNode) wrapper.parentNode.removeChild(wrapper);
    return;
  }
  if (wrapper && wrapper.parentNode) wrapper.parentNode.removeChild(wrapper);

  if (pdfBlob && pdfBlob.size < 3000) {
    console.warn('PDF suspiciously small:', pdfBlob.size, 'bytes');
  }

  // Upload PDF to permanent public URL (never expires)
  const token = localStorage.getItem('token');
  let pdfUrl = null;
  try {
    const tempRes = await axios.post(`${API}/files/temp-pdf`, {
      pdf_base64: pdfBase64,
      os_number: String(order.os_number),
      filename: `OS_${order.os_number}.pdf`,
    }, { headers: { Authorization: `Bearer ${token}` } });
    pdfUrl = `${window.location.origin}${tempRes.data.path}`;
  } catch (err) {
    if (toast) toast.error('Falha ao publicar PDF para envio', { id: 'wa-copy' });
    return;
  }

  // Open the customer's WhatsApp conversation directly with message + PDF link.
  // This works for *any* number — no Meta API allowlist required.
  // Use the device's native WhatsApp if mobile; otherwise WhatsApp Web.
  const msg = encodeURIComponent(
    `Olá! Segue cópia eletrônica da OS Nº ${order.os_number}:\n${pdfUrl}\n\n` +
    `Mastermaq Assistência Técnica\n(31) 3422-5293 | (31) 2526-8420`
  );
  const waUrl = `https://wa.me/${phoneNum}?text=${msg}`;
  const opened = window.open(waUrl, '_blank');
  if (!opened) {
    // Popup blocked — fall back to same-tab navigation as last resort
    window.location.href = waUrl;
  }
  if (toast) toast.success(`WhatsApp aberto. Clique "Enviar" para entregar a cópia ao cliente.`, { id: 'wa-copy', duration: 6000 });
};
