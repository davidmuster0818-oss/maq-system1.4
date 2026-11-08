import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { api, errMsg } from "@/components/finance/api";
import { METHODS, STATUSES, todayIso, brl } from "@/lib/format";
import { useRef_ } from "@/components/finance/RefData";
import { SimpleSelect } from "@/components/finance/common";
import { toast } from "sonner";

const blank = (type, preset) => ({
  type, date: todayIso(), amount: "", description: "", category_id: "", payment_method: "pix", status: "pago",
  os_ids: [], technician_id: null, part_name: "", ...preset,
});

export const useOsSearch = (q) => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api.get("/finance/os", { params: { q } }).then((r) => setRows(r.data)).catch(() => setRows([])).finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);
  return { rows, loading };
};

export const OsPicker = ({ value, onChange, testPrefix = "os-pick", single = false }) => {
  const [q, setQ] = useState("");
  const { rows, loading } = useOsSearch(q);
  const toggle = (id) => onChange(single ? (value.includes(id) ? [] : [id]) : value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid={`${testPrefix}-selected`}>
          {value.map((id) => (
            <span key={id} className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-full px-2 py-0.5">
              OS #{String(id).trim()}
              <button type="button" onClick={() => toggle(id)} data-testid={`${testPrefix}-remove-${String(id).trim()}`}><X size={12} /></button>
            </span>
          ))}
        </div>
      )}
      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar OS por número ou cliente" className="pl-8 bg-white" data-testid={`${testPrefix}-search`} />
      </div>
      <div className="max-h-44 overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100">
        {loading && <div className="px-3 py-2 text-xs text-slate-400">Buscando…</div>}
        {!loading && rows.length === 0 && <div className="px-3 py-2 text-xs text-slate-400">Nenhuma OS encontrada</div>}
        {!loading && rows.map((o) => (
          <label key={o.id} className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-slate-50">
            <Checkbox checked={value.includes(o.id)} onCheckedChange={() => toggle(o.id)} data-testid={`${testPrefix}-${o.number}`} />
            <span className="flex-1 min-w-0">
              <span className="block truncate">OS #{o.number} · {o.client}</span>
              <span className="block text-[11px] text-slate-500 truncate">{o.status}{o.technician ? ` · ${o.technician}` : ""}</span>
            </span>
            <span className="text-xs text-slate-500">{brl(o.total)}</span>
          </label>
        ))}
      </div>
    </div>
  );
};

const Field = ({ label, children }) => (
  <div className="space-y-1.5"><Label className="text-xs text-slate-600">{label}</Label>{children}</div>
);

export default function TxForm({ open, onClose, type, initial, preset, onSaved }) {
  const { categories, techs, catById } = useRef_();
  const [f, setF] = useState(blank(type));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setF(initial ? { ...initial, part_name: initial.part_name || "", status: initial.status === "atrasado" ? "previsto" : initial.status } : blank(type, preset));
    }
  }, [open, initial, type, preset]);

  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v }));
  const cats = categories.filter((c) => c.type === type);
  const isPart = catById[f.category_id]?.group === "peca";

  const save = async () => {
    if (!f.description || !f.amount || !f.category_id) {
      toast.error("Preencha descrição, valor e categoria");
      return;
    }
    setSaving(true);
    const body = { ...f, amount: Number(f.amount), part_name: f.part_name || null, technician_id: f.technician_id || null };
    try {
      if (initial) await api.put(`/finance/transactions/${initial.id}`, body);
      else await api.post("/finance/transactions", body);
      toast.success("Lançamento salvo");
      onSaved();
      onClose();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white max-w-lg max-h-[90vh] overflow-y-auto" data-testid="transaction-form-dialog">
        <DialogHeader><DialogTitle>{initial ? "Editar" : "Nova"} {type === "entrada" ? "entrada" : "saída"}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2"><Field label="Descrição"><Input value={f.description} onChange={(e) => set("description")(e.target.value)} data-testid="tx-form-description" /></Field></div>
          <Field label="Data"><Input type="date" value={f.date} onChange={(e) => set("date")(e.target.value)} data-testid="tx-form-date" /></Field>
          <Field label="Valor (R$)"><Input type="number" step="0.01" min="0" value={f.amount} onChange={(e) => set("amount")(e.target.value)} data-testid="tx-form-amount" /></Field>
          <Field label="Categoria"><SimpleSelect className="w-full" value={f.category_id} onChange={set("category_id")} placeholder="Escolha" testId="tx-form-category" options={cats.map((c) => ({ value: c.id, label: c.name }))} /></Field>
          <Field label="Forma de pagamento"><SimpleSelect className="w-full" value={f.payment_method} onChange={set("payment_method")} testId="tx-form-method" options={Object.entries(METHODS).map(([value, label]) => ({ value, label }))} /></Field>
          <Field label="Status"><SimpleSelect className="w-full" value={f.status} onChange={set("status")} testId="tx-form-status" options={Object.entries(STATUSES).map(([value, label]) => ({ value, label }))} /></Field>
          <Field label="Técnico"><SimpleSelect className="w-full" value={f.technician_id || "none"} onChange={(v) => set("technician_id")(v === "none" ? null : v)} testId="tx-form-technician" options={[{ value: "none", label: "Nenhum" }, ...techs.map((t) => ({ value: t.id, label: t.name }))]} /></Field>
          {isPart && <div className="col-span-2"><Field label="Peça vendida"><Input value={f.part_name} onChange={(e) => set("part_name")(e.target.value)} placeholder="Ex.: Capacitor 35uF" data-testid="tx-form-part" /></Field></div>}
          <div className="col-span-2"><Field label="Vincular a OS (opcional, uma ou várias)"><OsPicker value={f.os_ids} onChange={set("os_ids")} testPrefix="tx-form-os" /></Field></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button className="bg-blue-600 hover:bg-blue-700" onClick={save} disabled={saving} data-testid="transaction-form-submit-btn">{saving ? "Salvando…" : "Salvar"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
