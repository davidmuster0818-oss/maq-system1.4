import { useEffect, useState, useCallback } from "react";
import { PluggyConnect } from "react-pluggy-connect";
import { Landmark, RefreshCw, Trash2, Link2, PlusCircle, EyeOff, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, errMsg } from "@/components/finance/api";
import { brl, fmtDate } from "@/lib/format";
import { useRef_ } from "@/components/finance/RefData";
import { Card, SectionTitle, SimpleSelect, Empty } from "@/components/finance/common";
import { toast } from "sonner";

const CreateDialog = ({ state, onClose, onSaved }) => {
  const { categories } = useRef_();
  const [cat, setCat] = useState("");
  const [desc, setDesc] = useState("");
  useEffect(() => { if (state) { setCat(""); setDesc(state.bt.description); } }, [state]);
  const save = async () => {
    if (!cat) return toast.error("Escolha a categoria");
    try {
      await api.post(`/banks/transactions/${state.bt.id}/create`, { category_id: cat, description: desc, os_ids: state.osId ? [state.osId] : [] });
      toast.success("Lançamento criado e conferido");
      onSaved();
      onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={!!state} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white max-w-md" data-testid="bank-create-dialog">
        <DialogHeader><DialogTitle>Criar lançamento a partir do extrato</DialogTitle></DialogHeader>
        {state && <p className="text-sm text-slate-500">{fmtDate(state.bt.date)} · {brl(state.bt.amount)} · {state.bt.type === "entrada" ? "Entrada" : "Saída"}{state.osLabel ? ` · vinculado a ${state.osLabel}` : ""}</p>}
        <Input value={desc} onChange={(e) => setDesc(e.target.value)} data-testid="bank-create-description" />
        <SimpleSelect className="w-full" value={cat} onChange={setCat} placeholder="Categoria" testId="bank-create-category" options={categories.filter((c) => c.type === state?.bt.type).map((c) => ({ value: c.id, label: c.name }))} />
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancelar</Button><Button className="bg-blue-600 hover:bg-blue-700" onClick={save} data-testid="bank-create-submit-btn">Criar</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const WebhookCard = ({ onSynced }) => {
  const [info, setInfo] = useState(null);
  const load = useCallback(() => { api.get("/banks/webhook").then((r) => setInfo(r.data)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const register = async () => {
    try { await api.post("/banks/webhook/register"); toast.success("Webhook registrado no Pluggy"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const syncAll = async () => {
    try { await api.post("/banks/sync-all"); toast.success("Sincronização iniciada"); setTimeout(() => { load(); onSynced(); }, 6000); } catch (e) { toast.error(errMsg(e)); }
  };
  const copy = () => { navigator.clipboard.writeText(info.url); toast.success("URL copiada"); };
  if (!info) return null;
  return (
    <Card className="p-5 space-y-3" data-testid="bank-webhook-card">
      <div className="flex flex-wrap justify-between items-start gap-2">
        <div>
          <h3 className="font-semibold text-slate-900">Atualização automática</h3>
          <p className="text-xs text-slate-500">Sincronização diária às 6h (Brasília) e webhook do Pluggy para novidades em tempo real.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={syncAll} data-testid="bank-sync-all-btn"><RefreshCw size={14} className="mr-1" />Sincronizar tudo agora</Button>
          {!info.registered && <Button size="sm" className="bg-blue-600 hover:bg-blue-700" onClick={register} data-testid="bank-webhook-register-btn">Registrar webhook no Pluggy</Button>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Input readOnly value={info.url} className="font-mono text-xs bg-slate-50" data-testid="bank-webhook-url" />
        <Button variant="outline" size="sm" onClick={copy} data-testid="bank-webhook-copy-btn">Copiar</Button>
      </div>
      <div className="text-xs text-slate-600 flex flex-wrap gap-x-4 gap-y-1">
        <span data-testid="bank-webhook-status">Webhook: <b className={info.registered ? "text-emerald-700" : "text-amber-700"}>{info.registered ? "registrado no Pluggy" : "não registrado"}</b></span>
        <span>Última sincronização: {info.last_sync ? `${new Date(info.last_sync.finished_at).toLocaleString("pt-BR")} (${info.last_sync.trigger === "cron" ? "automática" : "manual"})` : "-"}</span>
        <span>Último evento: {info.last_events[0] ? `${info.last_events[0].event} em ${new Date(info.last_events[0].received_at).toLocaleString("pt-BR")}` : "-"}</span>
      </div>
    </Card>
  );
};

const BankRow = ({ bt, onLink, onCreate, onIgnore }) => (
  <tr className="border-t border-slate-100 align-top" data-testid={`bank-tx-row-${bt.id}`}>
    <td className="px-4 py-3 whitespace-nowrap">{fmtDate(bt.date)}</td>
    <td className="px-4 py-3"><div className="font-medium">{bt.description}</div><div className="text-xs text-slate-500">{bt.account_name}</div></td>
    <td className={`px-4 py-3 text-right font-mono-num font-semibold whitespace-nowrap ${bt.type === "entrada" ? "text-emerald-700" : "text-rose-700"}`}>{bt.type === "entrada" ? "+" : "-"}{brl(bt.amount)}</td>
    <td className="px-4 py-3 min-w-[280px]">
      {bt.handled ? <span className="text-xs font-semibold text-blue-700 uppercase">{bt.handled}</span> : (
        <div className="space-y-1.5">
          {bt.suggestions.length === 0 && <span className="text-xs text-slate-400">Sem sugestão por valor e data</span>}
          {bt.suggestions.map((s, i) => (
            <div key={i} className="flex items-center justify-between gap-2 bg-blue-50/60 border border-blue-100 rounded-lg px-2.5 py-1.5">
              <span className="text-xs text-slate-700">{s.kind === "os" ? "OS" : "Lançamento"}: {s.label} · {fmtDate(s.date)}</span>
              {s.kind === "os"
                ? <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onCreate(bt, s)} data-testid={`bank-suggest-os-${bt.id}-${i}`}>Usar OS</Button>
                : <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onLink(bt, s)} data-testid={`bank-suggest-link-${bt.id}-${i}`}><Link2 size={12} className="mr-1" />Vincular</Button>}
            </div>
          ))}
          <div className="flex gap-1">
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => onCreate(bt)} data-testid={`bank-create-btn-${bt.id}`}><PlusCircle size={12} className="mr-1" />Criar lançamento</Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs text-slate-500" onClick={() => onIgnore(bt)} data-testid={`bank-ignore-btn-${bt.id}`}><EyeOff size={12} className="mr-1" />Ignorar</Button>
          </div>
        </div>
      )}
    </td>
  </tr>
);

export default function Banks() {
  const [configured, setConfigured] = useState(null);
  const [items, setItems] = useState([]);
  const [txs, setTxs] = useState([]);
  const [token, setToken] = useState(null);
  const [busy, setBusy] = useState(false);
  const [pendingOnly, setPendingOnly] = useState("pending");
  const [createState, setCreateState] = useState(null);

  const load = useCallback(() => {
    api.get("/banks/status").then((r) => setConfigured(r.data.configured));
    api.get("/banks/items").then((r) => setItems(r.data));
    api.get("/banks/transactions", { params: { pending_only: pendingOnly === "pending" } }).then((r) => setTxs(r.data));
  }, [pendingOnly]);
  useEffect(() => { load(); }, [load]);

  const connect = async () => {
    try { const r = await api.post("/banks/connect-token"); setToken(r.data.accessToken); } catch (e) { toast.error(errMsg(e)); }
  };
  const onSuccess = async ({ item }) => {
    setToken(null);
    setBusy(true);
    try { const r = await api.post("/banks/items", { item_id: item.id }); toast.success(`Importadas ${r.data.transactions} movimentações de ${r.data.accounts} conta(s)`); load(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const run = async (fn, msg) => { setBusy(true); try { await fn(); if (msg) toast.success(msg); load(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); } };

  return (
    <>
      <SectionTitle title="Bancos" subtitle="Open Finance via Pluggy (ambiente de testes): importe o extrato e concilie com lançamentos e OSs.">
        <Button className="bg-blue-600 hover:bg-blue-700" onClick={connect} disabled={!configured || busy} data-testid="bank-connect-btn"><Landmark size={16} className="mr-1" />Conectar banco</Button>
      </SectionTitle>
      {configured === false && <Card className="p-4 border-amber-200 bg-amber-50/50 text-sm text-amber-900" data-testid="bank-not-configured">As credenciais do Pluggy ainda não foram configuradas no servidor (PLUGGY_ID e PLUGGY_SECRET).</Card>}
      {configured && <WebhookCard onSynced={load} />}
      <Card className="p-4 text-xs text-slate-600 flex gap-2"><Info size={14} className="text-blue-600 shrink-0 mt-0.5" />Sandbox: escolha "Pluggy Bank" e use usuário <b>user-ok</b>, senha <b>password-ok</b> (código MFA 123456 se pedido). As sugestões de vínculo comparam valor exato e data (±5 dias).</Card>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.length === 0 && <Card className="md:col-span-3"><Empty text="Nenhuma conta conectada" testId="bank-items-empty" /></Card>}
        {items.map((it) => (
          <Card key={it.id} className="p-5" data-testid={`bank-item-${it.id}`}>
            <div className="flex justify-between items-start">
              <div><div className="font-semibold text-slate-900">{it.connector}</div><div className="text-xs text-slate-500">Última sincronização: {it.last_sync ? new Date(it.last_sync).toLocaleString("pt-BR") : "-"}</div></div>
              <div className="flex">
                <Button variant="ghost" size="icon" disabled={busy} onClick={() => run(() => api.post(`/banks/items/${it.id}/sync`), "Extrato atualizado")} data-testid={`bank-sync-${it.id}`}><RefreshCw size={15} /></Button>
                <Button variant="ghost" size="icon" onClick={() => window.confirm("Remover esta conexão?") && run(() => api.delete(`/banks/items/${it.id}`), "Conexão removida")} data-testid={`bank-remove-${it.id}`}><Trash2 size={15} className="text-rose-600" /></Button>
              </div>
            </div>
            {it.accounts.map((a) => <div key={a.id} className="flex justify-between text-sm mt-2"><span>{a.name}</span><span className="font-mono-num">{brl(a.balance)}</span></div>)}
          </Card>
        ))}
      </div>
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-slate-900">Extrato importado</h3>
        <SimpleSelect value={pendingOnly} onChange={setPendingOnly} testId="bank-filter-select" options={[{ value: "pending", label: "Só pendentes" }, { value: "all", label: "Todos" }]} />
      </div>
      <Card className="overflow-x-auto">
        {txs.length === 0 ? <Empty text="Nenhuma movimentação" /> : (
          <table className="w-full text-sm" data-testid="bank-tx-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-4 py-3 text-left">Data</th><th className="px-4 py-3 text-left">Descrição</th><th className="px-4 py-3 text-right">Valor</th><th className="px-4 py-3 text-left">Conciliação</th></tr></thead>
            <tbody>
              {txs.map((bt) => (
                <BankRow key={bt.id} bt={bt}
                  onLink={(b, s) => run(() => api.post(`/banks/transactions/${b.id}/link`, { transaction_id: s.transaction_id }), "Vinculado e conferido")}
                  onCreate={(b, s) => setCreateState({ bt: b, osId: s?.os_id, osLabel: s?.label })}
                  onIgnore={(b) => run(() => api.post(`/banks/transactions/${b.id}/ignore`))} />
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {token && <PluggyConnect connectToken={token} includeSandbox products={["ACCOUNTS", "TRANSACTIONS"]} language="pt" onSuccess={onSuccess} onError={(e) => toast.error(e?.message || "Erro na conexão")} onClose={() => setToken(null)} />}
      <CreateDialog state={createState} onClose={() => setCreateState(null)} onSaved={load} />
    </>
  );
}
