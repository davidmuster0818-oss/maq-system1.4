import { motion } from "framer-motion";
import { CheckCircle2, MapPin, Navigation, RotateCcw, Trash2, X } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDist, fmtDur } from "@/lib/geo";

const STATUS = { planejado: "Planejado", em_andamento: "Em andamento", concluido: "Concluído" };

export function StopDetails({ stop, index, leg, onClose, onNavigate, onToggleDone, onRemove, canComplete, extra }) {
  const done = stop.status === "concluida";
  return (
    <motion.div initial={{ opacity: 0, y: 12, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12 }}
      transition={{ type: "spring", damping: 22, stiffness: 260 }} className="rf-card rf-card-accent" data-testid="stop-details">
      <div className="flex items-start gap-3">
        <span className={`rf-stop-num ${done ? "rf-stop-num-done" : ""}`}>{index + 1}</span>
        <div className="min-w-0 flex-1">
          <p className="font-bold text-white leading-tight" data-testid="stop-details-label">{stop.label}</p>
          <p className="text-xs text-slate-400 mt-1 flex gap-1"><MapPin className="h-3 w-3 mt-0.5 shrink-0" />{stop.address}</p>
          <p className="text-[11px] font-mono text-slate-500 mt-1">{stop.lat != null ? `${Number(stop.lat).toFixed(5)}, ${Number(stop.lng).toFixed(5)}` : "Sem localização"}{stop.precision === "approximate" && <span className="rf-chip rf-chip-amber ml-2">aproximado</span>}</p>
          {leg && <p className="text-xs font-mono text-blue-300 mt-1">Trecho: {fmtDist(leg.distance_m)} · {fmtDur(leg.duration_s)}</p>}
        </div>
        <button onClick={onClose} data-testid="stop-details-close" aria-label="Fechar"><X className="h-4 w-4 text-slate-400 hover:text-white" /></button>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-4">
        <button onClick={onNavigate} disabled={done} className="rf-btn-primary h-10 rounded-xl text-xs" data-testid="stop-navigate-button">
          <Navigation className="h-4 w-4" />Navegar
        </button>
        <button onClick={onToggleDone} disabled={!canComplete} className="rf-btn-ghost h-10 rounded-xl text-xs" data-testid="stop-toggle-done-button">
          {done ? <><RotateCcw className="h-4 w-4" />Reabrir</> : <><CheckCircle2 className="h-4 w-4" />Concluir</>}
        </button>
        <button onClick={onRemove} className="rf-btn-ghost h-10 rounded-xl text-xs hover:text-rose-300" data-testid="stop-details-remove-button">
          <Trash2 className="h-4 w-4" />Remover
        </button>
      </div>
      {extra}
    </motion.div>
  );
}

export function SavedRoutes({ items, loading, currentId, onLoad, onDelete }) {
  if (loading) return <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 rounded-2xl bg-white/5" />)}</div>;
  if (!items.length) return <p className="text-sm text-slate-400 py-6 text-center" data-testid="saved-empty">Nenhum roteiro salvo ainda.</p>;
  return (
    <div className="space-y-2" data-testid="saved-routes-list">
      {items.map((it, i) => {
        const done = it.stops.filter((s) => s.status === "concluida").length;
        return (
          <motion.div key={it.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
            className={`rf-stop ${it.id === currentId ? "rf-stop-selected" : ""}`} data-testid={`saved-route-${i}`}>
            <button className="min-w-0 flex-1 text-left" onClick={() => onLoad(it)} data-testid={`saved-route-load-${i}`}>
              <span className="flex items-center gap-2">
                <span className="text-sm font-semibold text-white truncate">{it.name}</span>
                <span className={`rf-chip ${it.status === "em_andamento" ? "rf-chip-amber" : it.status === "concluido" ? "rf-chip-green" : "rf-chip-muted"}`}>{STATUS[it.status]}</span>
              </span>
              <span className="block text-xs text-slate-400 mt-1 font-mono">
                {it.stops.length} paradas · {done} concluídas{it.last_route_summary ? ` · ${fmtDist(it.last_route_summary.distance_m)}` : ""}
              </span>
            </button>
            <button onClick={() => onDelete(it.id)} className="text-slate-500 hover:text-rose-400" aria-label="Excluir" data-testid={`saved-route-delete-${i}`}>
              <Trash2 className="h-4 w-4" />
            </button>
          </motion.div>
        );
      })}
    </div>
  );
}
