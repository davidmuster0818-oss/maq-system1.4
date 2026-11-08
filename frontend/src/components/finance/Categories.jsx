import { useState } from "react";
import { Plus, Pencil, Trash2, ChevronUp, ChevronDown, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { api, errMsg } from "@/components/finance/api";
import { GROUPS } from "@/lib/format";
import { useRef_ } from "@/components/finance/RefData";
import { Card, SectionTitle, SimpleSelect } from "@/components/finance/common";
import { toast } from "sonner";

const COLORS = ["#2563EB", "#16A34A", "#D97706", "#9333EA", "#0891B2", "#E11D48", "#4F46E5", "#059669", "#64748B"];

const CatForm = ({ state, onClose, onSaved }) => {
  const [f, setF] = useState(state.initial || { name: "", type: state.type, group: Object.keys(GROUPS[state.type])[0], color: COLORS[0] });
  const save = async () => {
    if (!f.name.trim()) return toast.error("Informe o nome");
    try {
      const body = { name: f.name, type: f.type, group: f.group, color: f.color };
      if (state.initial) await api.put(`/finance/categories/${state.initial.id}`, body);
      else await api.post("/finance/categories", body);
      toast.success("Categoria salva");
      onSaved();
      onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white max-w-md" data-testid="category-form-dialog">
        <DialogHeader><DialogTitle>{state.initial ? "Editar" : "Nova"} categoria</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label className="text-xs">Nome</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="category-form-name" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Grupo</Label>
            <SimpleSelect className="w-full" value={f.group} onChange={(v) => setF({ ...f, group: v })} testId="category-form-group" options={Object.entries(GROUPS[f.type]).map(([value, label]) => ({ value, label }))} />
          </div>
          <div className="space-y-1.5"><Label className="text-xs">Cor</Label>
            <div className="flex gap-2 flex-wrap">{COLORS.map((c) => (
              <button key={c} onClick={() => setF({ ...f, color: c })} className={`h-7 w-7 rounded-full border-2 ${f.color === c ? "border-slate-900" : "border-white"}`} style={{ background: c }} data-testid={`category-color-${c.slice(1)}`} />
            ))}</div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button className="bg-blue-600 hover:bg-blue-700" onClick={save} data-testid="category-form-submit-btn">Salvar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const Column = ({ type, title, onNew, onEdit }) => {
  const { categories, reload } = useRef_();
  const list = categories.filter((c) => c.type === type);
  const move = async (c, direction) => { await api.post(`/finance/categories/${c.id}/move`, { direction }); reload(); };
  const del = async (c) => {
    if (!window.confirm(`Excluir a categoria "${c.name}"?`)) return;
    try { await api.delete(`/finance/categories/${c.id}`); toast.success("Excluída"); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Card className="p-5" data-testid={`categories-column-${type}`}>
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
        <Button size="sm" className="bg-blue-600 hover:bg-blue-700" onClick={() => onNew(type)} data-testid={`new-category-${type}-btn`}><Plus size={14} className="mr-1" />Nova</Button>
      </div>
      {Object.entries(GROUPS[type]).map(([g, gl]) => (
        <div key={g} className="mb-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1.5">{gl}</div>
          {list.filter((c) => c.group === g).map((c) => (
            <div key={c.id} className="flex items-center justify-between px-3 py-2 rounded-lg border border-slate-100 mb-1.5 hover:border-slate-200" data-testid={`category-item-${c.id}`}>
              <span className="flex items-center gap-2 text-sm font-medium"><span className="h-3 w-3 rounded-full" style={{ background: c.color }} />{c.name}{c.system_key && <Lock size={12} className="text-slate-400" title="Usada pelo sistema" />}</span>
              <span className="flex">
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => move(c, "up")} data-testid={`category-up-${c.id}`}><ChevronUp size={15} /></Button>
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => move(c, "down")} data-testid={`category-down-${c.id}`}><ChevronDown size={15} /></Button>
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onEdit(c)} data-testid={`category-edit-${c.id}`}><Pencil size={14} /></Button>
                {!c.system_key && <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => del(c)} data-testid={`category-delete-${c.id}`}><Trash2 size={14} className="text-rose-600" /></Button>}
              </span>
            </div>
          ))}
        </div>
      ))}
    </Card>
  );
};

export default function Categories() {
  const { reload } = useRef_();
  const [state, setState] = useState(null);
  return (
    <>
      <SectionTitle title="Categorias" subtitle="Crie, edite e organize as categorias. As marcadas com cadeado são usadas na geração automática das OSs." />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Column type="entrada" title="Entradas" onNew={(type) => setState({ type })} onEdit={(c) => setState({ type: c.type, initial: c })} />
        <Column type="saida" title="Saídas" onNew={(type) => setState({ type })} onEdit={(c) => setState({ type: c.type, initial: c })} />
      </div>
      {state && <CatForm state={state} onClose={() => setState(null)} onSaved={reload} />}
    </>
  );
}
