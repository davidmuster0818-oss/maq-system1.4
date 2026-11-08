import { useEffect, useState } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Legend } from "recharts";
import { AlertTriangle, CalendarClock, Trophy } from "lucide-react";
import { api, errMsg } from "@/components/finance/api";
import { brl, fmtDate, change } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { useRef_ } from "@/components/finance/RefData";
import { Card, Delta, PeriodFilter, initialPeriod, SimpleSelect, SectionTitle, Empty, StatusBadge } from "@/components/finance/common";
import { toast } from "sonner";

const Kpi = ({ id, label, value, delta, invert, hint, tone }) => (
  <Card className="p-5" data-testid={`kpi-card-${id}`}>
    <div className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</div>
    <div className={`text-2xl font-bold mt-2 font-mono-num ${tone}`} data-testid={`kpi-value-${id}`}>{brl(value)}</div>
    <div className="mt-1.5 min-h-[18px]">{delta !== undefined ? <Delta value={delta} invert={invert} /> : <span className="text-xs text-slate-500">{hint}</span>}</div>
  </Card>
);

const CategoryPie = ({ title, data, testId }) => (
  <Card className="p-5" data-testid={testId}>
    <h3 className="text-base font-semibold text-slate-900 mb-2">{title}</h3>
    {data.length === 0 ? <Empty text="Sem lançamentos no período" /> : (
      <div className="h-64">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="total" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
              {data.map((d) => <Cell key={d.category_id} fill={d.color} />)}
            </Pie>
            <Tooltip formatter={(v) => brl(v)} />
            <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    )}
  </Card>
);

const Alerts = ({ alerts, due }) => {
  if (!alerts.length && !due.length) return null;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {alerts.length > 0 && (
        <Card className="p-5 border-amber-200 bg-amber-50/40" data-testid="overview-budget-alerts">
          <h3 className="font-semibold text-slate-900 flex items-center gap-2"><AlertTriangle size={16} className="text-amber-600" />Limites de categoria</h3>
          <ul className="mt-3 space-y-1.5 text-sm">
            {alerts.map((b) => (
              <li key={b.id} className="flex justify-between">
                <span>{b.category_name}</span>
                <span className={b.pct >= 100 ? "text-rose-700 font-semibold" : "text-amber-700 font-semibold"}>{b.pct}% de {brl(b.monthly_limit)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {due.length > 0 && (
        <Card className="p-5" data-testid="overview-due-soon">
          <h3 className="font-semibold text-slate-900 flex items-center gap-2"><CalendarClock size={16} className="text-blue-600" />Contas a pagar (próximos 7 dias e em atraso)</h3>
          <ul className="mt-3 space-y-1.5 text-sm">
            {due.slice(0, 6).map((t) => (
              <li key={t.id} className="flex justify-between gap-2">
                <span className="truncate">{fmtDate(t.date)} · {t.description}</span>
                <span className="flex items-center gap-2 shrink-0"><StatusBadge status={t.status} />{brl(t.amount)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
};

const Ranking = ({ rows }) => (
  <Card className="p-5" data-testid="overview-tech-ranking">
    <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2"><Trophy size={16} className="text-amber-500" />Ranking de técnicos por valor gerado</h3>
    {rows.length === 0 ? <Empty text="Nenhum valor vinculado a técnicos" /> : (
      <div className="mt-3 space-y-3">
        {rows.map((r, i) => (
          <div key={r.technician_id} data-testid={`ranking-row-${r.technician_id}`}>
            <div className="flex justify-between text-sm">
              <span className="font-medium text-slate-800">{i + 1}. {r.name} <span className="text-slate-400 font-normal">· {r.os} OS</span></span>
              <span className="font-mono-num font-semibold">{brl(r.total)}</span>
            </div>
            <div className="h-2 bg-slate-100 rounded-full mt-1 overflow-hidden">
              <div className="h-full bg-blue-600 rounded-full" style={{ width: `${(r.total / rows[0].total) * 100}%` }} />
            </div>
            <div className="text-xs text-slate-500 mt-0.5">Recebido {brl(r.recebido)}</div>
          </div>
        ))}
      </div>
    )}
  </Card>
);

export default function Overview() {
  const { isAdmin } = useAuth();
  const { techs } = useRef_();
  const [period, setPeriod] = useState(initialPeriod());
  const [tech, setTech] = useState("all");
  const [data, setData] = useState(null);

  useEffect(() => {
    const params = { start: period.start, end: period.end };
    if (tech !== "all") params.technician_id = tech;
    api.get("/finance/overview", { params }).then((r) => setData(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [period.start, period.end, tech]);

  if (!data) return <div className="text-sm text-slate-500">Carregando…</div>;
  const c = data.current, p = data.previous;
  const entradas = data.by_category.filter((x) => x.type === "entrada");
  const saidas = data.by_category.filter((x) => x.type === "saida");
  const recv = [{ name: "Período", Recebido: c.entradas_pagas, "A receber": c.a_receber, "Em atraso": c.atrasado_receber }];

  return (
    <>
      <SectionTitle title="Visão Geral" subtitle={`Comparando com ${fmtDate(data.previous_range.start)} a ${fmtDate(data.previous_range.end)}`}>
        <PeriodFilter period={period} setPeriod={setPeriod} />
        {isAdmin && <SimpleSelect value={tech} onChange={setTech} testId="filter-technician-select"
          options={[{ value: "all", label: "Todos os técnicos" }, ...techs.map((t) => ({ value: t.id, label: t.name }))]} />}
      </SectionTitle>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi id="entradas" label="Entrou (recebido)" value={c.entradas_pagas} delta={change(c.entradas_pagas, p.entradas_pagas)} tone="text-emerald-700" />
        <Kpi id="saidas" label="Saiu (pago)" value={c.saidas_pagas} delta={change(c.saidas_pagas, p.saidas_pagas)} invert tone="text-rose-700" />
        <Kpi id="saldo" label="Saldo do período" value={c.saldo} delta={change(c.saldo, p.saldo)} tone={c.saldo >= 0 ? "text-slate-900" : "text-rose-700"} />
        <Kpi id="a-receber" label="Falta receber" value={c.a_receber} hint={`${brl(c.atrasado_receber)} em atraso · saldo previsto ${brl(c.saldo_previsto)}`} tone="text-amber-700" />
      </div>
      {isAdmin && <Alerts alerts={data.budget_alerts} due={data.due_soon} />}
      <Card className="p-5" data-testid="overview-series-chart">
        <h3 className="text-base font-semibold text-slate-900 mb-3">Entradas x saídas por dia</h3>
        {data.series.length === 0 ? <Empty text="Sem lançamentos no período" /> : (
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={data.series.map((s) => ({ ...s, dia: fmtDate(s.date).slice(0, 5) }))}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                <XAxis dataKey="dia" fontSize={11} tickLine={false} />
                <YAxis fontSize={11} tickLine={false} axisLine={false} width={60} tickFormatter={(v) => `R$${v}`} />
                <Tooltip formatter={(v) => brl(v)} />
                <Bar dataKey="entradas" name="Entradas" fill="#16A34A" radius={[4, 4, 0, 0]} />
                <Bar dataKey="saidas" name="Saídas" fill="#DC2626" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <CategoryPie title="Entradas por categoria" data={entradas} testId="overview-income-categories" />
        <CategoryPie title="Saídas por categoria" data={saidas} testId="overview-expense-categories" />
        <Card className="p-5" data-testid="overview-receivable-chart">
          <h3 className="text-base font-semibold text-slate-900 mb-2">A receber x recebido</h3>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={recv} layout="vertical">
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" hide />
                <Tooltip formatter={(v) => brl(v)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Recebido" fill="#2563EB" radius={4} />
                <Bar dataKey="A receber" fill="#D97706" radius={4} />
                <Bar dataKey="Em atraso" fill="#E11D48" radius={4} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <Ranking rows={data.ranking} />
    </>
  );
}
