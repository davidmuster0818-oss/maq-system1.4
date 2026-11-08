import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, MapPin, Search, X } from "lucide-react";
import { toast } from "sonner";
import { api, apiError } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

const newToken = () => (window.crypto?.randomUUID ? window.crypto.randomUUID() : String(Date.now()));

export function SearchBox({ onPick }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [osItems, setOsItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);
  const [err, setErr] = useState(null);
  const token = useRef(newToken());
  const reqId = useRef(0);

  useEffect(() => {
    if (q.trim().length < 3) {
      setItems([]);
      setOsItems([]);
      setLoading(false);
      return undefined;
    }
    const id = ++reqId.current;
    setLoading(true);
    const t = setTimeout(async () => {
      api.get("/os-search", { params: { q: q.trim() } }).then(({ data }) => { if (id === reqId.current) setOsItems(data); }).catch(() => {});
      try {
        const { data } = await api.post("/routes/autocomplete", { input: q.trim(), session_token: token.current });
        if (id === reqId.current) { setItems(data); setErr(null); }
      } catch (e) {
        if (id === reqId.current) { setItems([]); setErr(apiError(e)); }
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    }, 320);
    return () => clearTimeout(t);
  }, [q]);

  const done = (place) => {
    if (onPick(place)) setQ("");
    setItems([]);
    setOsItems([]);
    token.current = newToken();
  };

  const pickOS = async (o) => {
    setLoading(true);
    try {
      const { data } = await api.post("/os-stop", { os_numbers: [String(o.os_number)] });
      done(data[0]);
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setLoading(false);
    }
  };

  const pick = async (it) => {
    if (it.lat != null && it.lng != null) {
      done({ place_id: it.place_id, label: it.main, address: it.address, lat: it.lat, lng: it.lng });
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.get(`/routes/place/${encodeURIComponent(it.place_id)}`, { params: { session_token: token.current } });
      done({ ...data, label: data.label || it.main });
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setLoading(false);
    }
  };

  const geocode = async () => {
    if (q.trim().length < 3) return;
    setLoading(true);
    try {
      const { data } = await api.post("/routes/geocode", { address: q.trim() });
      done({ ...data, label: data.address.split(",")[0] });
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setLoading(false);
    }
  };

  const open = focused && q.trim().length >= 3;
  return (
    <div className="relative">
      <div className="rf-field rf-field-lg">
        <Search className="h-4 w-4 text-slate-400 shrink-0" />
        <input data-testid="search-stop-input" value={q} onChange={(e) => setQ(e.target.value)}
          onFocus={() => setFocused(true)} onBlur={() => setTimeout(() => setFocused(false), 180)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); items[0] ? pick(items[0]) : geocode(); } }}
          placeholder="Adicionar parada: OS, cliente, bairro ou endereço" />
        {loading ? <Loader2 className="h-4 w-4 animate-spin text-blue-400" /> : q && (
          <button data-testid="search-clear-button" onClick={() => setQ("")} aria-label="Limpar"><X className="h-4 w-4 text-slate-400 hover:text-white" /></button>
        )}
      </div>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
            className="absolute z-30 left-0 right-0 mt-2 rf-glass-solid rounded-2xl p-1.5 shadow-2xl" data-testid="search-results">
            {loading && !items.length && !osItems.length && [0, 1, 2].map((i) => (
              <div key={i} className="flex gap-3 p-2.5"><Skeleton className="h-8 w-8 rounded-xl bg-white/10" /><div className="flex-1 space-y-2"><Skeleton className="h-3 w-2/3 bg-white/10" /><Skeleton className="h-3 w-1/2 bg-white/5" /></div></div>
            ))}
            {osItems.map((o, i) => (
              <button key={`os-${o.os_number}`} data-testid={`search-os-result-${i}`} onMouseDown={(e) => e.preventDefault()} onClick={() => pickOS(o)}
                className="w-full flex items-start gap-3 p-2.5 rounded-xl text-left hover:bg-white/10 transition-colors">
                <span className="h-8 w-8 rounded-xl rf-os-badge grid place-items-center shrink-0 text-[10px] font-bold">OS</span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-white truncate">OS {o.os_number} · {o.customer_name}</span>
                  <span className="block text-xs text-slate-400 truncate">{[o.address, o.number, o.neighborhood].filter(Boolean).join(", ")}</span>
                </span>
              </button>
            ))}
            {items.map((it, i) => (
              <button key={it.place_id} data-testid={`search-result-${i}`} onMouseDown={(e) => e.preventDefault()} onClick={() => pick(it)}
                className="w-full flex items-start gap-3 p-2.5 rounded-xl text-left hover:bg-white/10 transition-colors">
                <span className="h-8 w-8 rounded-xl bg-white/5 grid place-items-center shrink-0"><MapPin className="h-4 w-4 text-blue-400" /></span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-white truncate">{it.main}</span>
                  <span className="block text-xs text-slate-400 truncate">{it.secondary}</span>
                </span>
              </button>
            ))}
            {!loading && !items.length && !osItems.length && (
              <button data-testid="search-geocode-button" onMouseDown={(e) => e.preventDefault()} onClick={geocode}
                className="w-full p-3 text-left text-sm text-slate-300 hover:bg-white/10 rounded-xl">
                {err ? <span className="text-amber-300 block text-xs mb-1">{err}</span> : null}
                Buscar endereço exato: <span className="font-semibold text-white">"{q}"</span>
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
