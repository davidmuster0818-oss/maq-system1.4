import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import DashboardLayout from '../components/DashboardLayout';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { Loader2, RefreshCw, Send, AlertTriangle, CheckCircle2, Webhook } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

export default function WebhooksAdminPage() {
  const { getAuthHeader } = useAuth();
  const [config, setConfig] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [testOS, setTestOS] = useState('');
  const [testStatus, setTestStatus] = useState('TEST_DIAGNOSTIC');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, log] = await Promise.all([
        axios.get(`${API}/webhooks/config`, getAuthHeader()),
        axios.get(`${API}/webhooks/outbound-log?limit=100`, getAuthHeader()),
      ]);
      setConfig(cfg.data);
      setRows(log.data.rows || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha ao carregar logs');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeader]);

  useEffect(() => { load(); }, [load]);

  const replay = async (logId) => {
    setBusy(true);
    try {
      const res = await axios.post(`${API}/webhooks/outbound-log/${logId}/replay`, {}, getAuthHeader());
      const ok = res.data?.new_log?.ok;
      toast[ok ? 'success' : 'warning'](ok ? 'Webhook reenviado com sucesso' : `Reenvio retornou HTTP ${res.data?.new_log?.status_code}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha no reenvio');
    } finally {
      setBusy(false);
    }
  };

  const fireTest = async () => {
    if (!testOS || !testStatus) { toast.error('Informe OS e status'); return; }
    setBusy(true);
    try {
      const res = await axios.post(`${API}/webhooks/test-fire`,
        { os_number: testOS, status: testStatus, notes: 'Disparo manual via painel admin' },
        getAuthHeader());
      const ok = res.data?.log?.ok;
      toast[ok ? 'success' : 'warning'](ok ? 'Webhook disparado com sucesso (HTTP 2xx)' : `Disparado mas retornou HTTP ${res.data?.log?.status_code}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha no disparo');
    } finally {
      setBusy(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-4" data-testid="webhooks-admin-page">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Webhook className="h-5 w-5 text-gray-600" />
            <h2 className="text-xl font-semibold">Webhooks Outbound</h2>
            <Badge variant="outline">{rows.length}</Badge>
          </div>
          <Button onClick={load} variant="outline" className="gap-2" disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Recarregar
          </Button>
        </div>

        {/* Config card */}
        {config && (
          <div className="rounded-lg border bg-white p-4 space-y-2" data-testid="webhook-config-card">
            <h3 className="text-sm font-semibold text-gray-700">Configuração ativa</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div><span className="text-gray-500">URL destino:</span><br/><span className="font-mono break-all">{config.webhook_url}</span></div>
              <div><span className="text-gray-500">X-API-Key (preview):</span><br/><span className="font-mono">{config.api_key_preview}</span> <span className="text-gray-400">({config.api_key_length} chars)</span></div>
            </div>
          </div>
        )}

        {/* Manual fire / diagnostic */}
        <div className="rounded-lg border bg-white p-4 space-y-3" data-testid="webhook-fire-card">
          <h3 className="text-sm font-semibold text-gray-700">Disparo manual (diagnóstico)</h3>
          <p className="text-xs text-gray-500">
            Dispara um webhook de teste para o site externo sem alterar dados reais.
            Usado para confirmar que o receptor está respondendo.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <Label className="text-xs">Número da OS</Label>
              <Input value={testOS} onChange={e => setTestOS(e.target.value)} placeholder="ex: 27677" data-testid="webhook-test-os" />
            </div>
            <div>
              <Label className="text-xs">Status</Label>
              <Input value={testStatus} onChange={e => setTestStatus(e.target.value)} placeholder="TEST_DIAGNOSTIC" data-testid="webhook-test-status" />
            </div>
            <div className="flex items-end">
              <Button onClick={fireTest} disabled={busy} className="gap-2 w-full" data-testid="webhook-test-fire-btn">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Disparar
              </Button>
            </div>
          </div>
        </div>

        {/* Log table */}
        <div className="rounded-lg border bg-white overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 text-gray-600 border-b">
              <tr>
                <th className="text-left p-2">Quando</th>
                <th className="text-left p-2">OS</th>
                <th className="text-left p-2">Status enviado</th>
                <th className="text-left p-2">HTTP</th>
                <th className="text-left p-2">Resposta / Erro</th>
                <th className="text-right p-2">Ações</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="p-6 text-center text-gray-500"><Loader2 className="h-5 w-5 animate-spin inline mr-2" />Carregando…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={6} className="p-6 text-center text-gray-500">Nenhum webhook disparado ainda. Tente disparar um teste acima ou alterar o status de uma OS.</td></tr>
              ) : rows.map(r => (
                <tr key={r.id} className="border-b last:border-0 hover:bg-gray-50" data-testid={`webhook-row-${r.id}`}>
                  <td className="p-2 font-mono text-[10px]">{r.sent_at ? new Date(r.sent_at).toLocaleString('pt-BR') : ''}</td>
                  <td className="p-2 font-semibold">{r.os_number}</td>
                  <td className="p-2">{r.payload?.status}</td>
                  <td className="p-2">
                    {r.ok ? (
                      <Badge className="bg-green-100 text-green-700 hover:bg-green-100 gap-1"><CheckCircle2 className="h-3 w-3" />{r.status_code}</Badge>
                    ) : r.status_code ? (
                      <Badge className="bg-red-100 text-red-700 hover:bg-red-100 gap-1"><AlertTriangle className="h-3 w-3" />{r.status_code}</Badge>
                    ) : (
                      <Badge variant="secondary" className="gap-1"><AlertTriangle className="h-3 w-3" />ERROR</Badge>
                    )}
                  </td>
                  <td className="p-2 max-w-md truncate font-mono text-[10px]" title={r.response_body || r.error}>
                    {r.response_body || r.error || '—'}
                  </td>
                  <td className="p-2 text-right">
                    <Button size="sm" variant="ghost" onClick={() => replay(r.id)} disabled={busy} className="gap-1 text-[10px]" data-testid={`webhook-replay-${r.id}`}>
                      <RefreshCw className="h-3 w-3" /> Reenviar
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </DashboardLayout>
  );
}
