import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Home, Loader2, Navigation, Plus, RefreshCw, Route, Sparkles, Smartphone, Gauge } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { SearchBox } from "@/components/planner/SearchBox";
import { StopsList } from "@/components/planner/StopsList";
import { RouteSkeleton, RouteSummary } from "@/components/planner/RouteSummary";
import { SavedRoutes, StopDetails } from "@/components/planner/StopDetails";
import { fmtDist, fmtDur } from "@/lib/geo";

export function legLabelsFor(stops, rtb) {
  const names = ["Base", ...stops.map((s) => s.label), ...(rtb ? ["Base"] : [])];
  return names.slice(0, -1).map((n, i) => `${n} → ${names[i + 1]}`);
}

function StartNav({ onStart, gpsMode, setGpsMode, disabled }) {
  return (
    <div className="rf-card space-y-3" data-testid="start-navigation-panel">
      <div className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-black/30">
        <button data-testid="gps-mode-device" onClick={() => setGpsMode("device")} className={`rf-seg ${gpsMode === "device" ? "rf-seg-on" : ""}`}>
          <Smartphone className="h-3.5 w-3.5" />GPS do aparelho
        </button>
        <button data-testid="gps-mode-sim" onClick={() => setGpsMode("sim")} className={`rf-seg ${gpsMode === "sim" ? "rf-seg-on" : ""}`}>
          <Gauge className="h-3.5 w-3.5" />Simular trajeto
        </button>
      </div>
      <button data-testid="start-navigation-button" disabled={disabled} onClick={() => onStart()} className="rf-btn-go w-full h-12 rounded-2xl">
        <Navigation className="h-5 w-5" fill="currentColor" />Iniciar navegação
      </button>
      {gpsMode === "sim" && <p className="text-[11px] text-slate-500">Modo de teste: o veículo percorre a rota real sem usar seu GPS.</p>}
    </div>
  );
}

export function PlannerPanel({ planner, base, selectedId, setSelectedId, onStartNav, gpsMode, setGpsMode, header, extra, stopExtra }) {
  const [tab, setTab] = useState("route");
  const { stops, routes, selectedRoute, loading, error, stale, returnToBase } = planner;
  const route = stale ? null : routes[selectedRoute];
  const sel = stops.findIndex((s) => s.id === selectedId);
  const movable = returnToBase ? stops.length : stops.length - 1;
  const legLabels = legLabelsFor(stops, returnToBase);

  return (
    <div className="flex flex-col gap-4" data-testid="planner-panel">
      {header}
      {!planner.hideSaved && (
      <div className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-black/30">
        <button data-testid="route-tab" onClick={() => setTab("route")} className={`rf-seg ${tab === "route" ? "rf-seg-on" : ""}`}>Roteiro</button>
        <button data-testid="saved-routes-tab" onClick={() => { setTab("saved"); planner.refreshSaved(); }} className={`rf-seg ${tab === "saved" ? "rf-seg-on" : ""}`}>
          Salvos{planner.saved.length ? ` (${planner.saved.length})` : ""}
        </button>
      </div>
      )}

      {tab === "saved" ? (
        <div className="space-y-3">
          <button data-testid="new-itinerary-button" onClick={() => { planner.reset(); setTab("route"); }} className="rf-btn-ghost w-full h-10 rounded-xl text-sm">
            <Plus className="h-4 w-4" />Novo roteiro
          </button>
          <SavedRoutes items={planner.saved} loading={planner.savedLoading} currentId={planner.itinerary?.id}
            onLoad={(it) => { planner.load(it); setTab("route"); }} onDelete={planner.removeSaved} />
        </div>
      ) : (
        <>
          <input data-testid="itinerary-name-input" value={planner.name} readOnly={planner.hideSaved} onChange={(e) => planner.setName(e.target.value)}
            className="bg-transparent text-lg font-bold text-white outline-none border-b border-transparent focus:border-blue-500/60 pb-1" maxLength={120} />
          <SearchBox onPick={planner.addStop} />

          <div className="rf-stop" data-testid="base-card">
            <span className="rf-stop-num rf-stop-num-base"><Home className="h-3.5 w-3.5" /></span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-white">Saída · Base operacional</p>
              <p className="text-xs text-slate-400 truncate">{base.address}</p>
            </div>
          </div>

          <AnimatePresence>
            {sel >= 0 && (
              <StopDetails key={selectedId} stop={stops[sel]} index={sel} leg={route?.legs[sel]} canComplete={!!planner.itinerary}
                onClose={() => setSelectedId(null)} onNavigate={() => onStartNav(stops[sel].id)}
                onToggleDone={() => planner.setStopStatus(stops[sel].id, stops[sel].status !== "concluida")}
                onRemove={() => { planner.removeStop(stops[sel].id); setSelectedId(null); }} extra={stopExtra?.(stops[sel])} />
            )}
          </AnimatePresence>

          <StopsList stops={stops} legs={route?.legs} selectedId={selectedId} onSelect={setSelectedId}
            onReorder={planner.reorder} onRemove={planner.removeStop} />

          <label className="flex items-center justify-between gap-3 px-1">
            <span className="text-sm text-slate-300">Retornar à base no final</span>
            <Switch data-testid="return-to-base-switch" checked={returnToBase} onCheckedChange={planner.toggleReturn} />
          </label>

          {stale && stops.length > 0 && (
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-xs text-amber-300 flex items-center gap-2" data-testid="route-stale-notice">
              <RefreshCw className="h-3.5 w-3.5" />Roteiro alterado. Recalcule para atualizar a rota.
            </motion.p>
          )}

          <div className="grid grid-cols-2 gap-2">
            <button data-testid="optimize-route-button" disabled={loading || movable < 2} onClick={() => planner.compute(stops, { optimize: true })} className="rf-btn-ghost h-11 rounded-xl text-sm">
              <Sparkles className="h-4 w-4" />Otimizar ordem
            </button>
            <button data-testid="calculate-route-button" disabled={loading || !stops.length} onClick={() => planner.compute(stops)} className="rf-btn-primary h-11 rounded-xl text-sm">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Route className="h-4 w-4" />}Calcular rota
            </button>
          </div>
          {error && <p className="text-sm text-rose-400" data-testid="route-error">{error}</p>}
          {extra}

          {route && (
            <div className="flex items-baseline gap-3 px-1" data-testid="route-total">
              <span className="font-mono text-2xl font-bold text-white">{fmtDur(route.duration_s)}</span>
              <span className="font-mono text-sm text-slate-400">{fmtDist(route.distance_m)} · {stops.length} paradas</span>
            </div>
          )}
          {route && <StartNav onStart={onStartNav} gpsMode={gpsMode} setGpsMode={setGpsMode} disabled={loading} />}
          {loading ? <RouteSkeleton /> : route && <RouteSummary planner={planner} legLabels={legLabels} />}
        </>
      )}
    </div>
  );
}
