import { motion } from "framer-motion";
import { AlertTriangle, ArrowRightLeft, Coins, X } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDist, fmtDur, fmtMoney } from "@/lib/geo";

const LABELS = { DEFAULT_ROUTE: "Mais rápida", DEFAULT_ROUTE_ALTERNATE: "Alternativa", FUEL_EFFICIENT: "Econômica", SHORTER_DISTANCE: "Mais curta" };

function delay(r) {
  const d = (r.duration_s || 0) - (r.static_duration_s || 0);
  return d > 60 ? d : 0;
}

function RouteCard({ r, i, best, selected, onSelect, testid }) {
  const dd = r.duration_s - best.duration_s, dk = r.distance_m - best.distance_m;
  const toll = fmtMoney(r.tolls?.prices);
  return (
    <motion.button layout onClick={() => onSelect(i)} data-testid={testid}
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
      className={`rf-route-card ${selected ? "rf-route-card-on" : ""}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className={`font-mono text-xl font-bold ${delay(r) > 300 ? "text-amber-300" : "text-emerald-300"}`}>{fmtDur(r.duration_s)}</span>
        <span className="font-mono text-sm text-slate-300">{fmtDist(r.distance_m)}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="rf-chip">{LABELS[r.labels?.[0]] || (i === 0 ? "Recomendada" : `Alternativa ${i}`)}</span>
        {i > 0 && <span className="rf-chip rf-chip-muted">{dd >= 0 ? "+" : ""}{fmtDur(Math.abs(dd))}{dd < 0 ? " a menos" : ""} · {dk >= 0 ? "+" : "-"}{fmtDist(Math.abs(dk))}</span>}
        {delay(r) > 0 && <span className="rf-chip rf-chip-amber">+{fmtDur(delay(r))} trânsito</span>}
        {r.tolls?.has_tolls && <span className="rf-chip rf-chip-rose"><Coins className="h-3 w-3" />{toll || "Pedágio"}</span>}
      </div>
      {r.description && <p className="mt-1.5 text-xs text-slate-400 truncate">via {r.description}</p>}
    </motion.button>
  );
}

export function RouteSkeleton() {
  return (
    <div className="space-y-2" data-testid="route-loading">
      {[0, 1].map((i) => <Skeleton key={i} className="h-20 rounded-2xl bg-white/5" />)}
    </div>
  );
}

export function RouteSummary({ planner, legLabels }) {
  const { routes, selectedRoute, setSelectedRoute, legCompare, setLegCompare, compareLeg } = planner;
  const route = routes[selectedRoute];
  if (!route) return null;
  return (
    <div className="space-y-4" data-testid="route-summary">
      <div>
        <p className="rf-section">{routes.length > 1 ? "Rotas disponíveis" : "Rota calculada"}</p>
        <div className="space-y-2">
          {routes.map((r, i) => (
            <RouteCard key={i} r={r} i={i} best={routes[0]} selected={i === selectedRoute} onSelect={setSelectedRoute}
              testid={i === 0 ? "route-option-primary" : `route-option-alternative-${i}`} />
          ))}
        </div>
        {routes.length === 1 && route.legs.length > 1 && (
          <p className="mt-2 text-[11px] text-slate-500">Com várias paradas, compare alternativas trecho a trecho abaixo.</p>
        )}
        {route.warnings?.map((w, i) => (
          <p key={i} className="mt-2 flex gap-2 text-xs text-amber-300"><AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />{w}</p>
        ))}
      </div>

      {legCompare && (
        <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className="rf-card" data-testid="leg-compare-panel">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-bold text-white">Alternativas: {legLabels[legCompare.legIdx]}</p>
            <button onClick={() => setLegCompare(null)} data-testid="leg-compare-close" aria-label="Fechar"><X className="h-4 w-4 text-slate-400 hover:text-white" /></button>
          </div>
          {legCompare.loading ? <RouteSkeleton /> : (
            <div className="space-y-2">
              {legCompare.routes.map((r, i) => (
                <RouteCard key={i} r={r} i={i} best={legCompare.routes[0]} selected={i === legCompare.selected}
                  onSelect={(k) => setLegCompare({ ...legCompare, selected: k })} testid={`leg-alt-${i}`} />
              ))}
              {legCompare.routes.length === 1 && <p className="text-xs text-slate-400">Não há alternativas relevantes para este trecho.</p>}
            </div>
          )}
        </motion.div>
      )}

      <div>
        <p className="rf-section">Trechos</p>
        <div className="space-y-1.5">
          {route.legs.map((l, i) => (
            <div key={i} className="flex items-center gap-3 rounded-xl px-3 py-2 bg-white/[0.03]" data-testid={`leg-row-${i}`}>
              <div className="min-w-0 flex-1">
                <p className="text-xs text-slate-300 truncate">{legLabels[i]}</p>
                <p className="font-mono text-xs text-slate-400">{fmtDist(l.distance_m)} · {fmtDur(l.duration_s)}{delay(l) ? ` · +${fmtDur(delay(l))}` : ""}{l.tolls?.has_tolls ? " · pedágio" : ""}</p>
              </div>
              <button onClick={() => compareLeg(i)} data-testid={`leg-compare-button-${i}`} className="rf-mini-btn" title="Comparar alternativas">
                <ArrowRightLeft className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
