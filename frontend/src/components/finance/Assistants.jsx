import { useEffect, useState, useCallback } from "react";
import { Bot, Plus, Play, Trash2, Loader2, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { api, errMsg } from "@/components/finance/api";
import { Card, SectionTitle, SimpleSelect, Empty } from "@/components/finance/common";
import { toast } from "sonner";

const inline = (s) => s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p));

const Markdown = ({ text }) => (
  <div className="text-sm text-slate-800 space-y-1.5 leading-relaxed">
    {text.split("\n").map((line, i) => {
      const l = line.trim();
      if (!l) return null;
      if (l.startsWith("#")) return <h4 key={i} className="font-semibold text-slate-900 pt-2">{l.replace(/^#+\s*/, "")}</h4>;
      if (/^[-*•]\s/.test(l)) return <div key={i} className="pl-4 relative"><span className="absolute left-0 text-blue-600">•</span>{inline(l.slice(2))}</div>;
      return <p key={i}>{inline(l)}</p>;
    })}
  </div>
);

const AsstForm = ({ state, functions, onClose, onSaved }) => {
  const [f, setF] = useState(state.initial || { name: "", function: "resumo_semanal", instructions: "", active: true });
  const save = async () => {
    if (!f.name.trim()) return toast.error("Informe o nome");
    const body = { name: f.name, function: f.function, instructions: f.instructions, active: f.active };
    try {
      if (state.initial) await api.put(`/assistants/${state.initial.id}`, body);
      else await api.post("/assistants", body);
      onSaved();
      onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white max-w-md" data-testid="assistant-form-dialog">
        <DialogHeader><DialogTitle>{state.initial ? "Editar" : "Novo"} assistente</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label className="text-xs">Nome</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="assistant-form-name" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Função</Label><SimpleSelect className="w-full" value={f.function} onChange={(v) => setF({ ...f, function: v })} testId="assistant-form-function" options={Object.entries(functions).map(([value, label]) => ({ value, label }))} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Instruções extras (opcional)</Label><Textarea value={f.instructions} onChange={(e) => setF({ ...f, instructions: e.target.value })} data-testid="assistant-form-instructions" /></div>
          <label className="flex items-center gap-2 text-sm"><Switch checked={f.active} onCheckedChange={(v) => setF({ ...f, active: v })} />Ativo</label>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancelar</Button><Button className="bg-blue-600 hover:bg-blue-700" onClick={save} data-testid="assistant-form-submit-btn">Salvar</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const AssistantCard = ({ a, functions, onEdit, onChanged }) => {
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState([]);
  const loadRuns = useCallback(() => { api.get(`/assistants/${a.id}/runs`).then((r) => setRuns(r.data)); }, [a.id]);
  useEffect(() => { loadRuns(); }, [loadRuns]);
  const run = async () => {
    setRunning(true);
    try { await api.post(`/assistants/${a.id}/run`); loadRuns(); toast.success("Resumo gerado"); } catch (e) { toast.error(errMsg(e)); } finally { setRunning(false); }
  };
  const del = async () => { if (window.confirm(`Excluir "${a.name}"?`)) { await api.delete(`/assistants/${a.id}`); onChanged(); } };
  const [latest, ...older] = runs;
  return (
    <Card className="p-5" data-testid={`assistant-card-${a.id}`}>
      <div className="flex flex-wrap justify-between items-start gap-3">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center"><Bot size={20} /></div>
          <div><div className="font-semibold text-slate-900">{a.name}{!a.active && <span className="text-xs text-slate-400 ml-2">(inativo)</span>}</div><div className="text-xs text-slate-500">{functions[a.function]}</div></div>
        </div>
        <div className="flex items-center gap-1">
          <Button className="bg-blue-600 hover:bg-blue-700" onClick={run} disabled={running || !a.active} data-testid="ai-summary-generate-btn">
            {running ? <Loader2 size={16} className="mr-1 animate-spin" /> : <Play size={16} className="mr-1" />}{running ? "Gerando…" : "Gerar resumo agora"}
          </Button>
          <Button variant="ghost" size="icon" onClick={() => onEdit(a)} data-testid={`assistant-edit-${a.id}`}><Pencil size={15} /></Button>
          <Button variant="ghost" size="icon" onClick={del} data-testid={`assistant-delete-${a.id}`}><Trash2 size={15} className="text-rose-600" /></Button>
        </div>
      </div>
      <div className="mt-4 border-t border-slate-100 pt-4" data-testid="ai-summary-output">
        {latest ? (
          <>
            <div className="text-xs text-slate-500 mb-2">Gerado em {new Date(latest.created_at).toLocaleString("pt-BR")} · modelo {latest.model}</div>
            <Markdown text={latest.content} />
          </>
        ) : <Empty text="Nenhum resumo gerado ainda. Clique em “Gerar resumo agora”." />}
      </div>
      {older.length > 0 && (
        <details className="mt-4 text-sm"><summary className="cursor-pointer text-blue-700 font-medium">Resumos anteriores ({older.length})</summary>
          <div className="mt-3 space-y-4">{older.map((r) => <div key={r.id} className="border-l-2 border-blue-200 pl-3"><div className="text-xs text-slate-500 mb-1">{new Date(r.created_at).toLocaleString("pt-BR")}</div><Markdown text={r.content} /></div>)}</div>
        </details>
      )}
    </Card>
  );
};

export default function Assistants() {
  const [data, setData] = useState({ assistants: [], functions: {} });
  const [state, setState] = useState(null);
  const load = useCallback(() => { api.get("/assistants").then((r) => setData(r.data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  return (
    <>
      <SectionTitle title="Assistentes" subtitle="Assistentes de IA com uma função. Disponível agora: resumo semanal (últimos 7 dias x semana anterior).">
        <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => setState({})} data-testid="new-assistant-btn"><Plus size={16} className="mr-1" />Novo assistente</Button>
      </SectionTitle>
      {data.assistants.length === 0 && <Card><Empty text="Nenhum assistente criado" /></Card>}
      {data.assistants.map((a) => <AssistantCard key={a.id} a={a} functions={data.functions} onEdit={(x) => setState({ initial: x })} onChanged={load} />)}
      {state && <AsstForm state={state} functions={data.functions} onClose={() => setState(null)} onSaved={load} />}
    </>
  );
}
