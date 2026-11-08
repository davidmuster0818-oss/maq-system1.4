import { AnimatePresence, Reorder, motion, useDragControls } from "framer-motion";
import { Check, GripVertical, Trash2 } from "lucide-react";
import { fmtDist, fmtDur } from "@/lib/geo";

function StopRow({ stop, index, leg, selected, onSelect, onRemove, locked }) {
  const controls = useDragControls();
  const done = stop.status === "concluida";
  return (
    <Reorder.Item value={stop} dragListener={false} dragControls={controls} layout
      initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, height: 0 }}
      whileDrag={{ scale: 1.02, boxShadow: "0 18px 40px rgba(0,0,0,.45)" }}
      className={`rf-stop ${selected ? "rf-stop-selected" : ""}`} data-testid={`stop-item-${index}`}>
      <button onPointerDown={(e) => !locked && controls.start(e)} className="touch-none text-slate-500 hover:text-white cursor-grab active:cursor-grabbing disabled:opacity-30"
        disabled={locked} aria-label="Arrastar para reordenar" data-testid={`stop-drag-handle-${index}`}>
        <GripVertical className="h-4 w-4" />
      </button>
      <motion.span layout className={`rf-stop-num ${done ? "rf-stop-num-done" : ""}`}>
        <AnimatePresence mode="wait" initial={false}>
          {done ? (
            <motion.span key="c" initial={{ scale: 0, rotate: -90 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 400, damping: 15 }}>
              <Check className="h-3.5 w-3.5" strokeWidth={3} />
            </motion.span>
          ) : <motion.span key="n" initial={{ scale: 0.5 }} animate={{ scale: 1 }}>{index + 1}</motion.span>}
        </AnimatePresence>
      </motion.span>
      <button className="min-w-0 flex-1 text-left" onClick={() => onSelect(stop.id)} data-testid={`stop-select-${index}`}>
        <span className={`block text-sm font-semibold truncate ${done ? "text-slate-500 line-through" : "text-white"}`}>{stop.label}</span>
        <span className="block text-xs text-slate-400 truncate">{stop.address}</span>
        {leg && (
          <span className="block mt-1 text-[11px] font-mono text-blue-300" data-testid={`stop-leg-info-${index}`}>
            {fmtDist(leg.distance_m)} · {fmtDur(leg.duration_s)}
          </span>
        )}
      </button>
      <button onClick={() => onRemove(stop.id)} disabled={locked} className="text-slate-500 hover:text-rose-400 transition-colors disabled:opacity-30"
        aria-label="Remover parada" data-testid={`stop-remove-button-${index}`}>
        <Trash2 className="h-4 w-4" />
      </button>
    </Reorder.Item>
  );
}

export function StopsList({ stops, legs, selectedId, onSelect, onReorder, onRemove, locked }) {
  if (!stops.length) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 p-5 text-center" data-testid="stops-empty">
        <p className="text-sm text-slate-300 font-semibold">Nenhuma parada ainda</p>
        <p className="text-xs text-slate-500 mt-1">Busque um endereço acima para montar o roteiro.</p>
      </div>
    );
  }
  return (
    <Reorder.Group axis="y" values={stops} onReorder={onReorder} className="space-y-2" data-testid="stops-list">
      <AnimatePresence initial={false}>
        {stops.map((s, i) => (
          <StopRow key={s.id} stop={s} index={i} leg={legs?.[i]} selected={selectedId === s.id}
            onSelect={onSelect} onRemove={onRemove} locked={locked} />
        ))}
      </AnimatePresence>
    </Reorder.Group>
  );
}
