import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Loader2, AlertTriangle, Package, Tag } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

/**
 * Public product viewer — no auth required.
 *
 * Opened when a customer scans a thermal-label QR code printed from the
 * Inventory page. Shows only the curated subset the backend exposes
 * (category, name, brand, model, unit, sale price) — cost and stock are
 * intentionally omitted.
 */
export default function ProductPublicViewPage() {
  const { code } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios
      .get(`${API}/product/public/by-code/${encodeURIComponent(code || '')}`)
      .then((res) => setData(res.data))
      .catch((e) => {
        const c = e?.response?.status;
        if (c === 404) setErr('Produto não encontrado.');
        else setErr('Não foi possível carregar o produto.');
      })
      .finally(() => setLoading(false));
  }, [code]);

  if (loading)
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" data-testid="product-public-loading" />
      </div>
    );

  if (err)
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 px-4 text-center" data-testid="product-public-error">
        <AlertTriangle className="h-10 w-10 text-amber-500 mb-3" />
        <h1 className="text-lg font-semibold text-gray-800">{err}</h1>
        <p className="text-sm text-gray-500 mt-1">Código: <span className="font-mono">{code}</span></p>
      </div>
    );

  const price = Number(data?.sale_price || 0);
  const priceStr = price.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-8" data-testid="product-public-view">
      <div className="max-w-md mx-auto">
        {/* Header */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="bg-gradient-to-br from blue-900 to-blue-700 px-6 py-8 text-white">
            <Package className="h-10 w-10 mb-3 opacity-80" />
            <p className="text-xs uppercase tracking-widest text-gray-300 mb-1">{data?.category || 'Produto'}</p>
            <h1 className="text-2xl font-bold leading-tight" data-testid="product-name">{data?.name || '—'}</h1>
          </div>

          {/* Details */}
          <div className="px-6 py-5 space-y-3">
            {data?.brand ? (
              <Row label="Marca" value={data.brand} testid="product-brand" />
            ) : null}
            {data?.model ? (
              <Row label="Modelo" value={data.model} testid="product-model" />
            ) : null}
            {data?.unit ? (
              <Row label="Unidade" value={data.unit} testid="product-unit" />
            ) : null}

            {/* Price */}
            <div className="pt-3 mt-3 border-t border-gray-100">
              <p className="text-xs uppercase tracking-widest text-gray-500 mb-1">Preço de venda</p>
              <p className="text-3xl font-bold text-gray-900" data-testid="product-price">{priceStr}</p>
            </div>
          </div>

          {/* Footer / code */}
          <div className="px-6 py-3 bg-gray-50 border-t border-gray-100 flex items-center gap-2 text-xs text-gray-500">
            <Tag size={12} />
            <span>Código: <span className="font-mono">{data?.code}</span></span>
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 mt-6">Mastermaq Assistência Técnica</p>
      </div>
    </div>
  );
}

const Row = ({ label, value, testid }) => (
  <div className="flex items-baseline justify-between gap-3" data-testid={testid}>
    <span className="text-xs uppercase tracking-widest text-gray-500 shrink-0">{label}</span>
    <span className="text-sm font-medium text-gray-900 text-right">{value}</span>
  </div>
);
