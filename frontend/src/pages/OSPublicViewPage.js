import { useEffect, useState } from 'react';
import { useParams, useLocation } from 'react-router-dom';
import axios from 'axios';
import { Loader2, AlertTriangle, Wrench, MapPin, Calendar, Tag } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const STATUS_COLORS = {
  'Aguardando Analise A.T': 'bg-amber-100 text-amber-700 border-amber-200',
  'Em Andamento': 'bg-blue-100 text-blue-700 border-blue-200',
  'Aguardando Peças': 'bg-orange-100 text-orange-700 border-orange-200',
  'Concluida': 'bg-green-100 text-green-700 border-green-200',
  'Finalizada': 'bg-green-100 text-green-700 border-green-200',
  'Cancelada': 'bg-red-100 text-red-700 border-red-200',
};

export default function OSPublicViewPage() {
  const { osNumber } = useParams();
  const location = useLocation();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = new URLSearchParams(location.search).get('t');
    // Two fetch modes:
    //  • signed (?t=JWT) → /api/os/public/{token} (legacy, kept for compat)
    //  • by-number (default) → /api/os/public/by-number/{os_number}
    //    – fired when the QR has no token (current default) so the scan flow
    //      always lands on a public OS view, never on /login.
    const url = token
      ? `${API}/os/public/${token}`
      : `${API}/os/public/by-number/${encodeURIComponent(osNumber || '')}`;
    axios.get(url)
      .then(res => setData(res.data))
      .catch(e => {
        const code = e?.response?.status;
        if (code === 410) setErr('Link expirado. Solicite um novo à Mastermaq.');
        else if (code === 401) setErr('Link inválido.');
        else if (code === 404) setErr('OS não encontrada.');
        else setErr('Não foi possível carregar a OS.');
      })
      .finally(() => setLoading(false));
  }, [osNumber, location.search]);

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
    </div>
  );

  if (err) return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="bg-white rounded-xl shadow-lg p-8 max-w-md text-center" data-testid="os-public-error">
        <AlertTriangle className="h-12 w-12 text-amber-500 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-gray-900">{err}</h1>
      </div>
    </div>
  );

  const status = data?.status || '—';
  const statusColor = STATUS_COLORS[status] || 'bg-gray-100 text-gray-700 border-gray-200';

  return (
    <div className="min-h-screen bg-gray-50 py-6 px-4" data-testid="os-public-page">
      <div className="max-w-md mx-auto">
        <header className="text-center mb-6">
          <img src="/assets/mastermaq-logo.png" alt="Mastermaq" className="h-10 mx-auto mb-3" onError={(e) => e.target.style.display = 'none'} />
          <h1 className="text-base font-semibold text-gray-900">Mastermaq Assistência Técnica</h1>
          <p className="text-xs text-gray-500">Detalhes da Ordem de Serviço</p>
        </header>

        <div className="bg-white rounded-xl shadow-md border overflow-hidden">
          <div className="p-5 border-b">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Ordem de Serviço</p>
            <p className="text-2xl font-bold text-gray-900" data-testid="os-public-number">Nº {data.os_number}</p>
            <span className={`inline-block mt-2 text-xs font-medium px-2.5 py-1 rounded-full border ${statusColor}`} data-testid="os-public-status">
              {status}
            </span>
          </div>

          <div className="p-5 space-y-3 text-sm">
            <Field icon={<Tag className="h-4 w-4" />} label="Cliente" value={data.customer_name} />
            <Field icon={<Wrench className="h-4 w-4" />} label="Equipamento"
              value={[data.product, data.brand, data.model].filter(Boolean).join(' ') || '—'} />
            {data.reported_defect && (
              <Field icon={<AlertTriangle className="h-4 w-4" />} label="Defeito relatado" value={data.reported_defect} multiline />
            )}
            <Field icon={<MapPin className="h-4 w-4" />} label="Local"
              value={[data.address, data.neighborhood, data.city].filter(Boolean).join(' — ') || '—'} />
            {data.complement && (
              <Field icon={<MapPin className="h-4 w-4" />} label="Complemento" value={data.complement} />
            )}
            {data.created_at && (
              <Field icon={<Calendar className="h-4 w-4" />} label="Criada em"
                value={new Date(data.created_at).toLocaleDateString('pt-BR')} />
            )}
          </div>

          <footer className="bg-gray-50 px-5 py-3 text-center text-[11px] text-gray-500">
            Mastermaq • (31) 3422-5293 • mastermaqassistencia.com.br
          </footer>
        </div>
      </div>
    </div>
  );
}

function Field({ icon, label, value, multiline = false }) {
  return (
    <div className="flex items-start gap-3">
      <div className="text-gray-400 mt-0.5">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-[11px] text-gray-500 uppercase tracking-wide">{label}</p>
        <p className={`text-gray-900 ${multiline ? 'whitespace-pre-wrap' : 'truncate'}`}>{value || '—'}</p>
      </div>
    </div>
  );
}
