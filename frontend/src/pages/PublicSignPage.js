/**
 * PublicSignPage — página pública, mobile-first, onde o CLIENTE assina
 * a OS pelo próprio celular via link enviado por WhatsApp.
 *
 * Fluxo:
 *   1. Cliente clica no link do WhatsApp → chega em /sign/:token
 *   2. GET /api/public/sign/:token carrega dados da OS (sem auth)
 *   3. Cliente confere OS + Nome do técnico → desenha assinatura
 *   4. POST /api/public/sign/:token/submit persiste a assinatura na OS
 *   5. Tela de sucesso — token é invalidado.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2, Check, RotateCcw, ShieldCheck, AlertCircle } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// —— canvas de assinatura, mobile-first ——
const SignaturePad = ({ onChange }) => {
  const canvasRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [hasDrawn, setHasDrawn] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const rect = canvas.parentElement.getBoundingClientRect();
    // Alta resolução — retina/mobile
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(260 * dpr);
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '260px';
    ctx.scale(dpr, dpr);
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, rect.width, 260);
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  }, []);

  const pos = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return { x: t.clientX - rect.left, y: t.clientY - rect.top };
  };

  const start = (e) => {
    e.preventDefault();
    const ctx = canvasRef.current.getContext('2d');
    const p = pos(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    setDrawing(true);
    setHasDrawn(true);
  };
  const move = (e) => {
    if (!drawing) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext('2d');
    const p = pos(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
  };
  const end = (e) => {
    e.preventDefault();
    setDrawing(false);
    if (hasDrawn) onChange?.(canvasRef.current.toDataURL('image/png'));
  };

  const clear = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = canvas.parentElement.getBoundingClientRect();
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, rect.width, 260);
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 2.5;
    setHasDrawn(false);
    onChange?.(null);
  };

  return (
    <div className="space-y-3">
      <div className="relative rounded-xl border-2 border-slate-200 bg-white overflow-hidden touch-none">
        <canvas
          ref={canvasRef}
          onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
          onTouchStart={start} onTouchMove={move} onTouchEnd={end}
          data-testid="public-sign-canvas"
          className="block w-full cursor-crosshair"
        />
        <div className="absolute bottom-4 left-4 right-4 border-t border-dashed border-slate-300 pointer-events-none" />
        {!hasDrawn && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="text-slate-300 text-sm select-none">Assine acima usando o dedo</span>
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={clear}
        className="text-xs text-slate-500 hover:text-slate-700 inline-flex items-center gap-1"
        data-testid="public-sign-clear"
      >
        <RotateCcw className="h-3.5 w-3.5" /> Limpar
      </button>
    </div>
  );
};

const Field = ({ label, value }) => value ? (
  <div className="flex flex-col">
    <span className="text-[11px] uppercase tracking-wide text-slate-400 font-medium">{label}</span>
    <span className="text-sm text-slate-800">{value}</span>
  </div>
) : null;

export default function PublicSignPage() {
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [signatureDataUrl, setSignatureDataUrl] = useState(null);
  const [cpf, setCpf] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/api/public/sign/${token}`);
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || 'Link inválido');
        }
        setData(await r.json());
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [token]);

  const submit = useCallback(async () => {
    if (!signatureDataUrl) return;
    setSubmitting(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/public/sign/${token}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signature_client: signatureDataUrl, client_cpf: cpf.trim() || null })
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || 'Falha ao registrar assinatura');
      }
      setSuccess(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }, [signatureDataUrl, cpf, token]);

  // ───── UI ─────
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6" data-testid="public-sign-error">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 max-w-md w-full text-center">
          <AlertCircle className="h-10 w-10 text-red-500 mx-auto mb-3" />
          <h1 className="text-lg font-semibold text-slate-900 mb-1">Link indisponível</h1>
          <p className="text-sm text-slate-500">{error}</p>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6" data-testid="public-sign-success">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 max-w-md w-full text-center">
          <div className="mx-auto w-14 h-14 rounded-full bg-emerald-50 flex items-center justify-center mb-4">
            <ShieldCheck className="h-7 w-7 text-emerald-600" />
          </div>
          <h1 className="text-xl font-semibold text-slate-900 mb-2">Assinatura registrada</h1>
          <p className="text-sm text-slate-500 mb-6">
            Obrigado! A OS <strong>#{data?.os_number}</strong> foi assinada com sucesso. Você já pode fechar esta página.
          </p>
          <div className="text-[11px] text-slate-400">Mastermaq Assistência Técnica</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-6 px-4 sm:py-10">
      <div className="max-w-md mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-widest text-slate-400 font-medium">Assinatura da OS</div>
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">OS #{data?.os_number}</h1>
          </div>
          <div className="text-right">
            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-medium">
              <ShieldCheck className="h-3 w-3" /> Link seguro
            </span>
          </div>
        </div>

        {/* Card resumo */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-800">Confira os dados</h2>
            <p className="text-[12px] text-slate-500 mt-0.5">Se algo estiver incorreto, entre em contato com o técnico antes de assinar.</p>
          </div>
          <div className="px-5 py-4 grid grid-cols-2 gap-x-4 gap-y-3">
            <div className="col-span-2">
              <Field label="Cliente" value={data?.customer_name} />
            </div>
            <Field label="Produto" value={data?.product} />
            <Field label="Marca" value={data?.brand} />
            <Field label="Modelo" value={data?.model} />
            <Field label="Tipo" value={data?.service_type} />
            <div className="col-span-2">
              <Field label="Defeito reclamado" value={data?.reported_defect} />
            </div>
            {data?.technical_diagnosis && (
              <div className="col-span-2">
                <Field label="Diagnóstico técnico" value={data.technical_diagnosis} />
              </div>
            )}
            <Field label="Técnico" value={data?.technician_name} />
            <Field label="Status" value={data?.status} />
          </div>
        </div>

        {/* Assinatura */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-800">Sua assinatura</h2>
            <p className="text-[12px] text-slate-500 mt-0.5">Assine no quadro abaixo usando o dedo. Pode limpar e refazer quantas vezes precisar.</p>
          </div>
          <div className="px-5 py-4 space-y-4">
            <SignaturePad onChange={setSignatureDataUrl} />
            <div>
              <label className="text-[11px] uppercase tracking-wide text-slate-400 font-medium">CPF (opcional)</label>
              <input
                value={cpf}
                onChange={e => setCpf(e.target.value)}
                placeholder="000.000.000-00"
                inputMode="numeric"
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
                data-testid="public-sign-cpf"
              />
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700 flex items-start gap-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" /> {error}
          </div>
        )}

        <button
          type="button"
          onClick={submit}
          disabled={!signatureDataUrl || submitting}
          className="w-full py-3.5 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
          data-testid="public-sign-submit"
        >
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          {submitting ? 'Enviando…' : 'Confirmar Assinatura'}
        </button>

        <p className="text-[11px] text-slate-400 text-center px-6 leading-relaxed">
          Ao assinar, você confirma o recebimento do serviço descrito e concorda com os termos apresentados pelo técnico.
        </p>

        <div className="text-center text-[11px] text-slate-400 pt-2">
          Mastermaq · Assistência Técnica
        </div>
      </div>
    </div>
  );
}
