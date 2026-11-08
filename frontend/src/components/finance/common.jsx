import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { PERIODS, periodRange, STATUSES } from "@/lib/format";
import { ArrowDownRight, ArrowUpRight, CheckCircle2 } from "lucide-react";

export const Card = ({ className = "", children, ...rest }) => (
  <div className={`bg-white border border-slate-200 rounded-xl shadow-sm ${className}`} {...rest}>{children}</div>
);

const STATUS_CLS = {
  pago: "bg-emerald-50 text-emerald-700 border-emerald-200",
  previsto: "bg-amber-50 text-amber-700 border-amber-200",
  atrasado: "bg-rose-50 text-rose-700 border-rose-200",
};

export const StatusBadge = ({ status, testId }) => (
  <span data-testid={testId} className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border inline-flex items-center whitespace-nowrap ${STATUS_CLS[status] || ""}`}>
    {STATUSES[status] || status}
  </span>
);

export const ReconciledBadge = () => (
  <span className="text-xs px-2 py-0.5 rounded-full font-semibold border bg-blue-50 text-blue-700 border-blue-200 inline-flex items-center gap-1 whitespace-nowrap">
    <CheckCircle2 size={12} /> Conferido
  </span>
);

export const Delta = ({ value, invert = false, testId }) => {
  if (value === null || value === undefined) return <span className="text-xs text-slate-400" data-testid={testId}>sem base anterior</span>;
  const good = invert ? value <= 0 : value >= 0;
  const Icon = value >= 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span data-testid={testId} className={`text-xs font-semibold inline-flex items-center gap-0.5 ${good ? "text-emerald-600" : "text-rose-600"}`}>
      <Icon size={14} />{Math.abs(value).toFixed(1)}% vs período anterior
    </span>
  );
};

export const SimpleSelect = ({ value, onChange, options, placeholder, testId, className = "w-44" }) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger className={`bg-white ${className}`} data-testid={testId}><SelectValue placeholder={placeholder} /></SelectTrigger>
    <SelectContent className="bg-white">
      {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
    </SelectContent>
  </Select>
);

export const PeriodFilter = ({ period, setPeriod }) => {
  const onPreset = (p) => setPeriod(p === "custom" ? { ...period, preset: p } : { preset: p, ...periodRange(p) });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SimpleSelect value={period.preset} onChange={onPreset} options={PERIODS} testId="filter-period-select" />
      {period.preset === "custom" && (
        <>
          <Input type="date" className="w-40 bg-white" value={period.start} data-testid="filter-start-date"
            onChange={(e) => setPeriod({ ...period, start: e.target.value })} />
          <span className="text-slate-400 text-sm">até</span>
          <Input type="date" className="w-40 bg-white" value={period.end} data-testid="filter-end-date"
            onChange={(e) => setPeriod({ ...period, end: e.target.value })} />
        </>
      )}
    </div>
  );
};

export const initialPeriod = (preset = "mes") => ({ preset, ...periodRange(preset) });

export const SectionTitle = ({ title, subtitle, children }) => (
  <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
    <div>
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
    </div>
    {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
  </div>
);

export const Empty = ({ text, testId }) => (
  <div className="text-center text-sm text-slate-500 py-10" data-testid={testId}>{text}</div>
);
