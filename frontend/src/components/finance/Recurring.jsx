import { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, BellRing, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { api, errMsg } from "@/components/finance/api";
import { brl, fmtDate, METHODS, todayIso } from "@/lib/format";
import { useRef_ } from "@/components/finance/RefData";
import { Card, SectionTitle, SimpleSelect, StatusBadge, Empty } from "@/components/finance/common";
import { toast } from "sonner";

const daysUntil = (d) => Math.round((new Date(`${d}T12:00:00`) - new Date(`${todayIso()}T12:00:00`)) / 86400000);

const RecForm = ({ state, onClose, onSaved }) => {
  const { categories } = useRef_();
  const [f, setF] = useState(state.initial || { description: "", amount: "", category_id: "", day_of_month: 10, payment_method: "pix", active: true });
  const save = async () => {
    if (!f.description || !f.amount || !f.category_id) return toast.error("Preencha descrição, valor e categoria");
    const body = { description: f.description, amount: Number(f.amount), category_id: f.category_id, day_of_month: Number(f.day_of_month), payment_method: f.payment_method, active: f.active };
    try {
      if (state.initial) await api.put(`/finance/recurring/${state.initial.id}`, body);
      else await api.post("/finance/recurring", body);
      toast.success("Despesa fixa salva");
      onSaved();
      onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white max-w-md" data-testid="recurring-form-dialog">
        <DialogHeader><DialogTitle>{state.initial ? "Editar" : "Nova"} despesa fixa</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2 space-y-1.5"><Label className="text-xs">Descrição</Label><Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} data-testid="recurring-form-description" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Valor mensal (R$)</Label><Input type="number" step="0.01" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} data-testid="recurring-form-amount" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Dia do vencimento</Label><Input type="number" min="1" max="31" value={f.day_of_month} onChange={(e) => setF({ ...f, day_of_month: e.target.value })} data-testid="recurring-form-day" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Categoria</Label><SimpleSelect className="w-full" value={f.category_id} onChange={(v) => setF({ ...f, category_id: v })} placeholder="Escolha" testId="recurring-form-category" options={categories.filter((c) => c.type === "saida").map((c) => ({ value: c.id, label: c.name }))} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Forma de pagamento</Label><SimpleSelect className="w-full" value={f.payment_method} onChange={(v) => setF({ ...f, payment_method: v })} testId="recurring-form-method" options={Object.entries(METHODS).map(([value, label]) => ({ value, label }))} /></div>
          <label className="col-span-2 flex items-center gap-2 text-sm"><Switch checked={f.active} onCheckedChange={(v) => setF({ ...f, active: v })} data-testid="recurring-form-active" />Ativa (lança todo mês)</label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button className="bg-blue-600 hover:bg-blue-700" onClick={save} data-testid="recurring-form-submit-btn">Salvar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const DueInfo = ({ cur }) => {
  if (!cur) return <span className="text-xs text-slate-400">Não lançada neste mês</span>;
  if (cur.status === "pago") return <StatusBadge status="pago" />;
  const d = daysUntil(cur.date);
  return (
    <span className="flex items-center gap-2">
      <StatusBadge status={cur.status} />
      {d >= 0 && d <= 5 && <span className="text-xs font-semibold text-amber-700 inline-flex items-center gap-1"><BellRing size={12} />vence {d === 0 ? "hoje" : `em ${d} dia(s)`}</span>}
    </span>
  );
};

export default function Recurring() {
  const { catById } = useRef_();
  const [items, setItems] = useState([]);
  const [state, setState] = useState(null);
  const load = useCallback(() => { api.get("/finance/recurring").then((r) => setItems(r.data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);

  const del = async (r) => {
    if (!window.confirm(`Excluir "${r.description}"? Lançamentos futuros não pagos serão removidos.`)) return;
    try { await api.delete(`/finance/recurring/${r.id}`); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const pay = async (t) => {
    try { await api.put(`/finance/transactions/${t.id}`, { ...t, status: "pago" }); toast.success("Marcada como paga"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const total = items.filter((r) => r.active).reduce((a, r) => a + r.amount, 0);
  const alerts = items.filter((r) => r.current && r.current.status !== "pago" && daysUntil(r.current.date) <= 5);

  return (
    <>
      <SectionTitle title="Despesas Fixas" subtitle={`Cadastre uma vez e o sistema lança todo mês. Total mensal ativo: ${brl(total)}`}>
        <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => setState({})} data-testid="new-recurring-btn"><Plus size={16} className="mr-1" />Nova despesa fixa</Button>
      </SectionTitle>
      {alerts.length > 0 && (
        <Card className="p-4 border-amber-200 bg-amber-50/50 flex items-start gap-3" data-testid="recurring-due-alert">
          <BellRing size={18} className="text-amber-600 mt-0.5" />
          <div className="text-sm text-amber-900"><strong>{alerts.length} despesa(s)</strong> vencendo em até 5 dias ou em atraso: {alerts.map((r) => `${r.description} (${fmtDate(r.current.date)})`).join(", ")}</div>
        </Card>
      )}
      <Card className="overflow-x-auto">
        {items.length === 0 ? <Empty text="Nenhuma despesa fixa cadastrada" /> : (
          <table className="w-full text-sm" data-testid="recurring-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-3 text-left">Descrição</th><th className="px-4 py-3 text-left">Categoria</th><th className="px-4 py-3 text-left">Vence dia</th><th className="px-4 py-3 text-left">Este mês</th><th className="px-4 py-3 text-right">Valor</th><th className="px-4 py-3 text-right">Ações</th></tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="border-t border-slate-100" data-testid={`recurring-row-${r.id}`}>
                  <td className="px-4 py-3 font-medium">{r.description}{!r.active && <span className="ml-2 text-xs text-slate-400">(pausada)</span>}</td>
                  <td className="px-4 py-3">{catById[r.category_id]?.name}</td>
                  <td className="px-4 py-3">{r.day_of_month}</td>
                  <td className="px-4 py-3"><DueInfo cur={r.current} /></td>
                  <td className="px-4 py-3 text-right font-mono-num font-semibold">{brl(r.amount)}</td>
                  <td className="px-2 py-3 text-right whitespace-nowrap">
                    {r.current && r.current.status !== "pago" && <Button variant="outline" size="sm" className="mr-1" onClick={() => pay(r.current)} data-testid={`recurring-pay-${r.id}`}><Check size={14} className="mr-1" />Pagar</Button>}
                    <Button variant="ghost" size="icon" onClick={() => setState({ initial: r })} data-testid={`recurring-edit-${r.id}`}><Pencil size={15} /></Button>
                    <Button variant="ghost" size="icon" onClick={() => del(r)} data-testid={`recurring-delete-${r.id}`}><Trash2 size={15} className="text-rose-600" /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {state && <RecForm state={state} onClose={() => setState(null)} onSaved={load} />}
    </>
  );
}
