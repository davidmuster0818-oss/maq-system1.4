import { useEffect, useState, useCallback } from "react";
import { Trash2, AlertTriangle, OctagonAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, errMsg } from "@/components/finance/api";
import { brl } from "@/lib/format";
import { useRef_ } from "@/components/finance/RefData";
import { Card, SectionTitle, SimpleSelect, Empty } from "@/components/finance/common";
import { toast } from "sonner";

const LEVEL = {
  ok: { bar: "bg-blue-600", text: "text-slate-600", label: "Dentro do limite" },
  alerta: { bar: "bg-amber-500", text: "text-amber-700", label: "Atenção: passou de 80%" },
  estourado: { bar: "bg-rose-600", text: "text-rose-700", label: "Limite atingido" },
};

export default function Budgets() {
  const { categories } = useRef_();
  const [items, setItems] = useState([]);
  const [cat, setCat] = useState("");
  const [limit, setLimit] = useState("");
  const load = useCallback(() => { api.get("/finance/budgets").then((r) => setItems(r.data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!cat || !limit) return toast.error("Escolha a categoria e o limite");
    try { await api.post("/finance/budgets", { category_id: cat, monthly_limit: Number(limit) }); setCat(""); setLimit(""); toast.success("Limite salvo"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async (b) => { try { await api.delete(`/finance/budgets/${b.id}`); load(); } catch (e) { toast.error(errMsg(e)); } };

  return (
    <>
      <SectionTitle title="Metas e Limites" subtitle="Teto mensal por categoria de saída, com aviso ao chegar em 80% e 100%." />
      <Card className="p-5 flex flex-wrap items-end gap-3" data-testid="budget-form">
        <div className="space-y-1.5"><div className="text-xs text-slate-600">Categoria</div>
          <SimpleSelect className="w-56" value={cat} onChange={setCat} placeholder="Escolha" testId="budget-form-category" options={categories.filter((c) => c.type === "saida").map((c) => ({ value: c.id, label: c.name }))} />
        </div>
        <div className="space-y-1.5"><div className="text-xs text-slate-600">Limite mensal (R$)</div>
          <Input type="number" className="w-40" value={limit} onChange={(e) => setLimit(e.target.value)} data-testid="budget-form-limit" />
        </div>
        <Button className="bg-blue-600 hover:bg-blue-700" onClick={save} data-testid="budget-form-submit-btn">Salvar limite</Button>
        <span className="text-xs text-slate-500">Se a categoria já tem limite, ele é atualizado.</span>
      </Card>
      {items.length === 0 ? <Card><Empty text="Nenhum limite definido" /></Card> : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((b) => {
            const lv = LEVEL[b.level];
            return (
              <Card key={b.id} className={`p-5 ${b.level === "estourado" ? "border-rose-300" : b.level === "alerta" ? "border-amber-300" : ""}`} data-testid={`budget-card-${b.category_id}`}>
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-2 font-semibold text-slate-900"><span className="h-3 w-3 rounded-full" style={{ background: b.color }} />{b.category_name}</div>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => del(b)} data-testid={`budget-delete-${b.category_id}`}><Trash2 size={14} className="text-rose-600" /></Button>
                </div>
                <div className="mt-3 flex justify-between text-sm"><span className="font-mono-num font-semibold">{brl(b.spent)}</span><span className="text-slate-500">de {brl(b.monthly_limit)}</span></div>
                <div className="h-2.5 bg-slate-100 rounded-full mt-2 overflow-hidden"><div className={`h-full rounded-full ${lv.bar}`} style={{ width: `${Math.min(b.pct, 100)}%` }} /></div>
                <div className={`mt-2 text-xs font-semibold flex items-center gap-1 ${lv.text}`} data-testid={`budget-level-${b.category_id}`}>
                  {b.level === "alerta" && <AlertTriangle size={13} />}{b.level === "estourado" && <OctagonAlert size={13} />}
                  {b.pct}% · {lv.label}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
