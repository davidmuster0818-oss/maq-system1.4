import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, apiError, sysApi } from "@/lib/api";
import { fmtDist, fmtDur, haversine } from "@/lib/geo";

// Planner do RotaFlow ligado a um roteiro do sistema: paradas = OSs do roteiro (+ avulsas).
// Ordem/avulsas/removidas/status/retorno ficam salvos no servidor por roteiro (/tracking/map-state) + cópia no aparelho.
const newId = () => (window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
const addrOf = (o) => [[o.address, o.number].filter(Boolean).join(" "), o.neighborhood, o.city].filter(Boolean).join(", ");
const ROUTE_FIELDS = ["os_number", "customer_name", "neighborhood", "city", "address", "number", "phone1", "technician",
  "conclusion", "observation", "attendance_date", "status"];

export const osToStop = (o, extra = {}) => ({
  id: `os-${o.os_number}`, os_number: String(o.os_number), label: `OS ${o.os_number}${o.customer_name ? ` · ${o.customer_name}` : ""}`,
  address: addrOf(o), place_id: null, lat: o.lat, lng: o.lng, status: "pendente", precision: o.precision, order: o, ...extra,
});

export function usePlanner(base, { routeId, routeName, orders, onPersistOrders, readOnly }) {
  const key = `rf-route-${routeId}`;
  const local = useRef(JSON.parse(localStorage.getItem(key) || "{}"));
  const [stops, setStops] = useState([]);
  const [returnToBase, setReturnToBase] = useState(local.current.rtb ?? true);
  const [routes, setRoutes] = useState([]);
  const [selectedRoute, setSelectedRoute] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [stale, setStale] = useState(false);
  const [legCompare, setLegCompare] = useState(null);
  const [preparing, setPreparing] = useState(true);
  const osKey = useRef("");
  const routeIds = useRef([]);

  const saveLocal = useCallback((list, rtb) => {
    const ids = new Set(list.map((s) => s.id));
    const data = {
      rtb, order: list.map((s) => s.id),
      extras: list.filter((s) => !routeIds.current.includes(s.id)),
      removed: routeIds.current.filter((id) => !ids.has(id)),
      status: Object.fromEntries(list.map((s) => [s.id, s.status])),
    };
    local.current = data;
    localStorage.setItem(key, JSON.stringify(data));
    if (!readOnly) sysApi.put(`/tracking/map-state/${routeId}`, data).catch(() => toast.error("Não foi possível salvar as alterações do mapa."));
  }, [key, readOnly, routeId]);

  const persist = useCallback(async (list, rtb) => {
    saveLocal(list, rtb);
    const os = list.filter((s) => s.os_number);
    const sig = os.map((s) => s.os_number).join(",");
    if (!onPersistOrders || sig === osKey.current) return;
    if (!os.length) { toast.error("O roteiro precisa de ao menos uma OS — ordem não salva."); return; }
    const clean = os.map((s, i) => ({
      ...Object.fromEntries(ROUTE_FIELDS.map((f) => [f, s.order?.[f] ?? null])), os_number: s.os_number, sequence: i + 1,
      lat: s.precision === "exact" ? s.lat : null, lng: s.precision === "exact" ? s.lng : null,
    }));
    if (await onPersistOrders(clean) !== false) osKey.current = sig;
  }, [onPersistOrders, saveLocal]);

  const compute = useCallback(async (list, { optimize = false, rtb } = {}) => {
    const useRtb = rtb ?? returnToBase;
    const valid = list.filter((s) => s.lat != null && s.lng != null);
    if (!base || !valid.length) return;
    setLoading(true);
    setError(null);
    setLegCompare(null);
    const pts = valid.map((s) => ({ lat: s.lat, lng: s.lng }));
    const b = { lat: base.lat, lng: base.lng };
    const body = { origin: b, destination: useRtb ? b : pts[pts.length - 1], intermediates: useRtb ? pts : pts.slice(0, -1), optimize, alternatives: true };
    try {
      const { data } = await api.post("/routes/compute-route", body);
      const r0 = data.routes[0];
      let ordered = valid;
      if (optimize && r0.optimized_order?.length) {
        const inter = useRtb ? valid : valid.slice(0, -1);
        const re = r0.optimized_order.map((i) => inter[i]);
        ordered = useRtb ? re : [...re, valid[valid.length - 1]];
        toast.success(`Ordem otimizada: ${fmtDist(r0.distance_m)} · ${fmtDur(r0.duration_s)}`);
      }
      ordered = [...ordered, ...list.filter((s) => s.lat == null)];
      setStops(ordered);
      setRoutes(data.routes);
      setSelectedRoute(0);
      setStale(false);
      await persist(ordered, useRtb);
    } catch (e) {
      setError(apiError(e));
    } finally {
      setLoading(false);
    }
  }, [base, returnToBase, persist]);

  // Carrega as OSs do roteiro (com coordenada validada/aproximada) + avulsas salvas no aparelho.
  useEffect(() => {
    if (!base) return;
    let alive = true;
    (async () => {
      const nums = orders.map((o) => String(o.os_number));
      routeIds.current = nums.map((n) => `os-${n}`);
      const [infoR, stateR] = await Promise.allSettled([
        api.post("/os-stops", { os_numbers: nums }),
        sysApi.get(`/tracking/map-state/${routeId}`),
      ]);
      if (!alive) return;
      if (infoR.status === "rejected") toast.error(apiError(infoR.reason));
      const info = infoR.status === "fulfilled" ? infoR.value.data : [];
      const server = stateR.status === "fulfilled" ? stateR.value.data : null;
      if (server?.order) { local.current = server; localStorage.setItem(key, JSON.stringify(server)); }
      if (local.current.rtb != null) setReturnToBase(local.current.rtb);
      const byNum = Object.fromEntries(info.map((i) => [i.os_number, i]));
      const st = local.current.status || {};
      const removed = new Set(local.current.removed || []);
      const fromRoute = orders.map((o) => osToStop({ ...o, ...(byNum[String(o.os_number)] || {}) }, { order: o, status: o.stop_status === "completed" ? "concluida" : "pendente" }))
        .filter((s) => !removed.has(s.id));
      const extras = (local.current.extras || []).filter((e) => !fromRoute.some((s) => s.id === e.id));
      const all = [...fromRoute, ...extras].map((s) => ({ ...s, status: st[s.id] || s.status }));
      const idx = (local.current.order || []);
      const pos = (s) => { const i = idx.indexOf(s.id); return i >= 0 ? i : 1000 + (s.os_number ? nums.indexOf(s.os_number) : 999); };
      all.sort((a, b) => pos(a) - pos(b));
      osKey.current = all.filter((s) => s.os_number).map((s) => s.os_number).join(",");
      setStops(all);
      setPreparing(false);
      const miss = all.filter((s) => s.precision && s.precision !== "exact");
      if (miss.length) toast.warning(`Endereço impreciso: ${miss.map((s) => `OS ${s.os_number}`).join(", ")} — confira número, bairro e cidade.`, { duration: 8000 });
      if (all.some((s) => s.lat != null)) compute(all);
    })();
    return () => { alive = false; };
  }, [base, routeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const markChanged = useCallback(() => { setStale(true); setLegCompare(null); }, []);

  const addStop = useCallback((place) => {
    const dup = stops.find((s) => (place.os_number && s.os_number === String(place.os_number))
      || (place.place_id && s.place_id === place.place_id) || (place.lat != null && s.lat != null && haversine(s, place) < 15));
    if (dup) { toast.error(`"${dup.label}" já está no roteiro`); return false; }
    if (place.lat == null) { toast.error("Sem localização para este endereço — corrija na OS."); return false; }
    const stop = place.os_number ? osToStop(place) : { id: newId(), label: place.label || place.address, address: place.address || "", place_id: place.place_id || null, lat: place.lat, lng: place.lng, status: "pendente" };
    const next = [...stops, stop];
    setStops(next);
    saveLocal(next, returnToBase);
    markChanged();
    return true;
  }, [stops, markChanged, saveLocal, returnToBase]);

  const removeStop = useCallback((id) => {
    const next = stops.filter((s) => s.id !== id);
    setStops(next); saveLocal(next, returnToBase); markChanged();
  }, [stops, markChanged, saveLocal, returnToBase]);
  const reorder = useCallback((list) => { setStops(list); saveLocal(list, returnToBase); markChanged(); }, [markChanged, saveLocal, returnToBase]);
  const toggleReturn = useCallback((v) => { setReturnToBase(v); saveLocal(stops, v); markChanged(); }, [markChanged, saveLocal, stops]);

  const setStopStatus = useCallback((id, done) => {
    setStops((prev) => {
      const next = prev.map((s) => (s.id === id ? { ...s, status: done ? "concluida" : "pendente" } : s));
      saveLocal(next, returnToBase);
      return next;
    });
  }, [saveLocal, returnToBase]);

  const ensureSaved = useCallback(async () => ({ id: routeId }), [routeId]);

  const compareLeg = useCallback(async (legIdx) => {
    const leg = routes[selectedRoute]?.legs[legIdx];
    if (!leg) return;
    setLegCompare({ legIdx, routes: [], selected: 0, loading: true });
    try {
      const { data } = await api.post("/routes/compute-route", { origin: leg.start, destination: leg.end, intermediates: [], alternatives: true });
      setLegCompare({ legIdx, routes: data.routes, selected: 0, loading: false });
    } catch (e) {
      setLegCompare(null);
      toast.error(apiError(e));
    }
  }, [routes, selectedRoute]);

  const noop = useCallback(async () => [], []);
  return {
    stops, returnToBase, name: routeName, setName: () => {}, itinerary: { id: routeId }, routes, selectedRoute, setSelectedRoute,
    loading: loading || preparing, error, stale, saved: [], savedLoading: false, legCompare, setLegCompare, refreshSaved: noop,
    compute, addStop, removeStop, reorder, toggleReturn, setStopStatus, ensureSaved, load: () => {}, reset: () => {}, removeSaved: noop, compareLeg,
  };
}
