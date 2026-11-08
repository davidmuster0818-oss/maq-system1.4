import { useEffect, useState, useCallback, Fragment } from "react";
import { Plus, Pencil, Trash2, Link2, CheckCircle2, Circle, Package, ClipboardList, DownloadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, errMsg } from "@/components/finance/api";
import { brl, fmtDate, groupKey, groupLabel, METHODS, STATUSES } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { useRef_ } from "@/components/finance/RefData";
import { Card, StatusBadge, ReconciledBadge, PeriodFilter, initialPeriod, SimpleSelect, SectionTitle, Empty } from "@/components/finance/common";
import TxForm from "@/components/finance/TxForm";
import LinkOsDialog from "@/components/finance/LinkOsDialog";
import OsFinanceDialog from "@/components/finance/OsFinanceDialog";
import { toast } from "sonner";

const Totals = ({ rows, type }) => {
  const sum = (fn) => rows.filter(fn).reduce((a, t) => a + t.amount, 0);
  const items = [
    ["Total", sum(() => true), "text-slate-900"],
    ["Pago", sum((t) => t.status === "pago"), "text-emerald-700"],
    ["Previsto", sum((t) => t.status === "previsto"), "text-amber-700"],
    ["Em atraso", sum((t) => t.status === "atrasado"), "text-rose-700"],
  ];
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map(([label, v, tone]) => (
        <Card key={label} className="p-4" data-testid={`${type}-total-${label.toLowerCase().replace(" ", "-")}`}>
          <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
          <div className={`text-xl font-bold font-mono-num mt-1 ${tone}`}>{brl(v)}</div>
        </Card>
      ))}
    </div>
  );
};

const Row = ({ t, isAdmin, catById, osById, techById, onEdit, onDelete, onLink, onReconcile }) => (
  <tr className="border-t border-slate-100 hover:bg-slate-50/60" data-testid={`tx-row-${t.id}`}>
    <td className="px-4 py-3 whitespace-nowrap text-slate-600">{fmtDate(t.date)}</td>
    <td className="px-4 py-3 min-w-[220px]">
      <div className="font-medium text-slate-900">{t.description}</div>
      <div className="text-xs text-slate-500 flex flex-wrap gap-x-2 mt-0.5">
        {t.part_name && <span className="inline-flex items-center gap-1"><Package size={11} />{t.part_name}</span>}
        {t.os_ids?.map((id) => <span key={id} className="text-blue-600">OS #{osById[id]?.number || String(id).trim()}</span>)}
        {t.technician_id && <span>{techById[t.technician_id]?.name || ""}</span>}
      </div>
    </td>
    <td className="px-4 py-3 whitespace-nowrap">
      <span className="inline-flex items-center gap-1.5 text-slate-700"><span className="h-2 w-2 rounded-full" style={{ background: catById[t.category_id]?.color }} />{catById[t.category_id]?.name || "-"}</span>
    </td>
    <td className="px-4 py-3 text-slate-600">{METHODS[t.payment_method]}</td>
    <td className="px-4 py-3"><div className="flex flex-col gap-1 items-start"><StatusBadge status={t.status} testId={`tx-status-${t.id}`} />{t.reconciled && <ReconciledBadge />}</div></td>
    <td className="px-4 py-3 text-right font-mono-num font-semibold whitespace-nowrap">{brl(t.amount)}</td>
    {isAdmin && (
      <td className="px-2 py-3 whitespace-nowrap text-right">
        <Button variant="ghost" size="icon" title={t.reconciled ? "Desmarcar conferido" : "Marcar como conferido com o extrato"} onClick={() => onReconcile(t)} data-testid={`reconcile-transaction-btn-${t.id}`}>
          {t.reconciled ? <CheckCircle2 size={16} className="text-blue-600" /> : <Circle size={16} className="text-slate-400" />}
        </Button>
        <Button variant="ghost" size="icon" title="Vincular OS" onClick={() => onLink(t)} data-testid={`tx-link-btn-${t.id}`}><Link2 size={16} /></Button>
        <Button variant="ghost" size="icon" title="Editar" onClick={() => onEdit(t)} data-testid={`tx-edit-btn-${t.id}`}><Pencil size={16} /></Button>
        <Button variant="ghost" size="icon" title="Excluir" onClick={() => onDelete(t)} data-testid={`tx-delete-btn-${t.id}`}><Trash2 size={16} className="text-rose-600" /></Button>
      </td>
    )}
  </tr>
);

export default function Transactions({ type }) {
  const { isAdmin } = useAuth();
  const ref = useRef_();
  const [period, setPeriod] = useState(initialPeriod());
  const [filters, setFilters] = useState({ category_id: "all", technician_id: "all", status: "all", payment_method: "all" });
  const [mode, setMode] = useState("dia");
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ open: false });
  const [linkTx, setLinkTx] = useState(null);
  const [osOpen, setOsOpen] = useState(false);
  const importDone = async () => {
    try {
      const r = await api.post("/finance/os/import-done", { start: period.start, end: period.end });
      toast.success(`${r.data.checked} OS(s) finalizada(s) com taxa verificadas, ${r.data.created} entrada(s) nova(s)`);
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const load = useCallback(() => {
    const params = { type, start: period.start, end: period.end };
    Object.entries(filters).forEach(([k, v]) => { if (v !== "all") params[k] = v; });
    api.get("/finance/transactions", { params }).then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [type, period.start, period.end, filters]);

  useEffect(() => {
    load();
  }, [load]);

  const setF = (k) => (v) => setFilters((x) => ({ ...x, [k]: v }));
  const del = async (t) => {
    if (!window.confirm(`Excluir "${t.description}"?`)) return;
    try { await api.delete(`/finance/transactions/${t.id}`); toast.success("Excluído"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const reconcile = async (t) => {
    try { await api.patch(`/finance/transactions/${t.id}/reconcile`, { reconciled: !t.reconciled }); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const partPreset = { category_id: ref.categories.find((c) => c.system_key === "peca")?.id || "", description: "Venda avulsa de peça" };

  const groups = [];
  rows.forEach((t) => {
    const k = groupKey(t.date, mode);
    if (!groups.length || groups[groups.length - 1].key !== k) groups.push({ key: k, items: [] });
    groups[groups.length - 1].items.push(t);
  });

  const label = type === "entrada" ? "Entradas" : "Saídas";
  return (
    <>
      <SectionTitle title={label} subtitle={type === "entrada" ? "Receitas de OS, vendas avulsas de peças e outras entradas" : "Despesas fixas, variáveis e outras saídas"}>
        {isAdmin && type === "entrada" && <Button variant="outline" onClick={importDone} title="Lança a taxa de visita das OSs finalizadas no período" data-testid="import-done-os-btn"><DownloadCloud size={16} className="mr-1" />Importar OSs finalizadas</Button>}
        {isAdmin && type === "entrada" && <Button variant="outline" onClick={() => setOsOpen(true)} data-testid="os-finance-btn"><ClipboardList size={16} className="mr-1" />Lançar OS</Button>}
        {isAdmin && type === "entrada" && <Button variant="outline" onClick={() => setForm({ open: true, preset: partPreset })} data-testid="new-part-sale-btn"><Package size={16} className="mr-1" />Venda de peça avulsa</Button>}
        {isAdmin && <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => setForm({ open: true })} data-testid={`new-${type}-btn`}><Plus size={16} className="mr-1" />Nova {type === "entrada" ? "entrada" : "saída"}</Button>}
      </SectionTitle>
      <div className="flex flex-wrap items-center gap-2">
        <PeriodFilter period={period} setPeriod={setPeriod} />
        <SimpleSelect value={filters.category_id} onChange={setF("category_id")} testId="filter-category-select"
          options={[{ value: "all", label: "Todas as categorias" }, ...ref.categories.filter((c) => c.type === type).map((c) => ({ value: c.id, label: c.name }))]} />
        {isAdmin && <SimpleSelect value={filters.technician_id} onChange={setF("technician_id")} testId="filter-technician-select"
          options={[{ value: "all", label: "Todos os técnicos" }, { value: "none", label: "Sem técnico" }, ...ref.techs.map((t) => ({ value: t.id, label: t.name }))]} />}
        <SimpleSelect value={filters.status} onChange={setF("status")} testId="filter-status-select" className="w-36"
          options={[{ value: "all", label: "Todos status" }, ...Object.entries(STATUSES).map(([value, l]) => ({ value, label: l }))]} />
        <SimpleSelect value={filters.payment_method} onChange={setF("payment_method")} testId="filter-method-select" className="w-36"
          options={[{ value: "all", label: "Todas formas" }, ...Object.entries(METHODS).map(([value, l]) => ({ value, label: l }))]} />
        <ToggleGroup type="single" value={mode} onValueChange={(v) => v && setMode(v)} className="ml-auto border border-slate-200 rounded-lg p-0.5" data-testid="group-mode-toggle">
          {[["dia", "Dia"], ["semana", "Semana"], ["mes", "Mês"]].map(([v, l]) => (
            <ToggleGroupItem key={v} value={v} className="h-8 px-3 text-sm data-[state=on]:bg-blue-600 data-[state=on]:text-white" data-testid={`group-mode-${v}`}>{l}</ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <Totals rows={rows} type={type} />
      <Card className="overflow-x-auto">
        {rows.length === 0 ? <Empty text="Nenhum lançamento encontrado" testId="transactions-empty" /> : (
          <table className="w-full text-sm" data-testid="transaction-list-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-3 text-left">Data</th><th className="px-4 py-3 text-left">Descrição</th><th className="px-4 py-3 text-left">Categoria</th><th className="px-4 py-3 text-left">Forma</th><th className="px-4 py-3 text-left">Status</th><th className="px-4 py-3 text-right">Valor</th>{isAdmin && <th className="px-4 py-3 text-right">Ações</th>}</tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <Fragment key={g.key}>
                  <tr className="bg-blue-50/50 border-t border-slate-200" data-testid={`group-header-${g.key}`}>
                    <td colSpan={5} className="px-4 py-2 text-xs font-semibold text-blue-800 uppercase tracking-wide">{groupLabel(g.key, mode)} · {g.items.length} lançamento(s)</td>
                    <td className="px-4 py-2 text-right font-mono-num font-bold text-blue-800">{brl(g.items.reduce((a, t) => a + t.amount, 0))}</td>
                    {isAdmin && <td />}
                  </tr>
                  {g.items.map((t) => <Row key={t.id} t={t} isAdmin={isAdmin} {...ref} onEdit={(x) => setForm({ open: true, initial: x })} onDelete={del} onLink={setLinkTx} onReconcile={reconcile} />)}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <TxForm open={form.open} initial={form.initial} preset={form.preset} type={type} onClose={() => setForm({ open: false })} onSaved={load} />
      <LinkOsDialog tx={linkTx} onClose={() => setLinkTx(null)} onSaved={load} />
      <OsFinanceDialog open={osOpen} onClose={() => setOsOpen(false)} onSaved={load} />
    </>
  );
}
