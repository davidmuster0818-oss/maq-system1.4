import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errMsg } from "@/components/finance/api";
import { METHODS, todayIso, brl } from "@/lib/format";
import { SimpleSelect } from "@/components/finance/common";
import { OsPicker } from "@/components/finance/TxForm";
import { toast } from "sonner";

const Stat = ({ label, value, tone = "text-slate-900", testId }) => (
  <div className="rounded-lg border border-slate-200 px-3 py-2" data-testid={testId}>
    <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
    <div className={`font-mono-num font-semibold ${tone}`}>{brl(value)}</div>
  </div>
);

const emptyForm = { service_value: "", fee_value: "", parts: [], payment_method: "pix", status: "previsto", date: todayIso() };

function PartsEditor({ parts, setParts }) {
  const upd = (i, k, v) => setParts(parts.map((p, j) => (j === i ? { ...p, [k]: v } : p)));
  return (
    <div className="space-y-2" data-testid="os-launch-parts">
      {parts.map((p, i) => (
        <div key={i} className="grid grid-cols-12 gap-1.5 items-center">
          <Input className="col-span-5 h-9" placeholder="Peça" value={p.name} onChange={(e) => upd(i, "name", e.target.value)} data-testid={`os-part-name-${i}`} />
          <Input className="col-span-2 h-9" type="number" min="1" placeholder="Qtd" value={p.qty} onChange={(e) => upd(i, "qty", e.target.value)} data-testid={`os-part-qty-${i}`} />
          <Input className="col-span-2 h-9" type="number" step="0.01" placeholder="Preço" value={p.unit_price} onChange={(e) => upd(i, "unit_price", e.target.value)} data-testid={`os-part-price-${i}`} />
          <Input className="col-span-2 h-9" type="number" step="0.01" placeholder="Custo" value={p.unit_cost} onChange={(e) => upd(i, "unit_cost", e.target.value)} data-testid={`os-part-cost-${i}`} />
          <Button type="button" variant="ghost" size="icon" className="col-span-1" onClick={() => setParts(parts.filter((_, j) => j !== i))}><Trash2 size={14} className="text-rose-600" /></Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => setParts([...parts, { name: "", qty: 1, unit_price: "", unit_cost: "" }])} data-testid="os-part-add-btn"><Plus size={14} className="mr-1" />Adicionar peça</Button>
    </div>
  );
}

export default function OsFinanceDialog({ open, onClose, onSaved }) {
  const [ids, setIds] = useState([]);
  const [fin, setFin] = useState(null);
  const [f, setF] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const osNum = ids[0];

  useEffect(() => { if (!open) { setIds([]); setFin(null); } }, [open]);
  useEffect(() => {
    if (!osNum) { setFin(null); return; }
    api.get(`/finance/os/${encodeURIComponent(osNum)}/finance`).then((r) => {
      setFin(r.data);
      const v = r.data.os.values;
      setF({ ...emptyForm, service_value: v?.service_value || "", fee_value: v ? v.fee_value || "" : r.data.os.visit_fee || "",
        parts: v?.parts || [], status: r.data.os.visit_fee_paid ? "pago" : "previsto" });
    }).catch((e) => toast.error(errMsg(e)));
  }, [osNum]);

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...f, service_value: Number(f.service_value || 0), fee_value: Number(f.fee_value || 0),
        parts: f.parts.filter((p) => p.name).map((p) => ({ name: p.name, qty: Number(p.qty || 1), unit_price: Number(p.unit_price || 0), unit_cost: Number(p.unit_cost || 0) })) };
      const r = await api.post(`/finance/os/${encodeURIComponent(osNum)}/launch`, body);
      toast.success(`${r.data.created} entrada(s) lançada(s) para a OS`);
      onSaved();
      onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="os-finance-dialog">
        <DialogHeader><DialogTitle>Financeiro da OS</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-500">Escolha a OS, informe serviço, taxa e peças: as entradas são lançadas vinculadas à OS e ao técnico. Lançar de novo substitui os valores anteriores.</p>
        <OsPicker value={ids} onChange={setIds} single testPrefix="os-launch" />
        {fin && (
          <div className="space-y-4">
            <div className="text-sm"><b>OS #{fin.os.number}</b> · {fin.os.client} · {fin.os.status}{fin.os.technician ? ` · Técnico: ${fin.os.technician}` : ""}</div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Stat label="Cobrado" value={fin.cobrado} testId="os-fin-cobrado" />
              <Stat label="Recebido" value={fin.recebido} tone="text-emerald-700" testId="os-fin-recebido" />
              <Stat label="A receber" value={fin.a_receber} tone="text-amber-700" testId="os-fin-a-receber" />
              <Stat label="Custo" value={fin.custo} tone="text-rose-700" testId="os-fin-custo" />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Serviço (R$)</Label><Input type="number" step="0.01" value={f.service_value} onChange={(e) => setF({ ...f, service_value: e.target.value })} data-testid="os-launch-service" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Taxa (R$)</Label><Input type="number" step="0.01" value={f.fee_value} onChange={(e) => setF({ ...f, fee_value: e.target.value })} data-testid="os-launch-fee" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Forma</Label><SimpleSelect className="w-full" value={f.payment_method} onChange={(v) => setF({ ...f, payment_method: v })} testId="os-launch-method" options={Object.entries(METHODS).map(([value, label]) => ({ value, label }))} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Status</Label><SimpleSelect className="w-full" value={f.status} onChange={(v) => setF({ ...f, status: v })} testId="os-launch-status" options={[{ value: "previsto", label: "Previsto" }, { value: "pago", label: "Pago" }]} /></div>
              <div className="space-y-1.5 col-span-2"><Label className="text-xs">Data</Label><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} data-testid="os-launch-date" /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Peças (quantidade, preço de venda e custo unitário)</Label><PartsEditor parts={f.parts} setParts={(parts) => setF({ ...f, parts })} /></div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
          <Button className="bg-blue-600 hover:bg-blue-700" disabled={!fin || saving} onClick={save} data-testid="os-launch-submit-btn">{saving ? "Lançando…" : "Lançar entradas da OS"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
