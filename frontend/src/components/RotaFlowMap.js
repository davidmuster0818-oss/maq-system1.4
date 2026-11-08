import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Clock, Eye, Map as MapIcon, Moon, Navigation, Send, Share2, Sun, X } from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/lib/supabase";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { api, apiError, sysApi } from "@/lib/api";
import { cameraForPoints, flyTo } from "@/lib/camera";
import { decodePolyline, fmtDist, fmtDur, offsetPoint } from "@/lib/geo";
import { MapCanvas } from "@/components/map/MapCanvas";
import { MapControls } from "@/components/map/MapControls";
import { useNavLegOverlay, useRouteOverlays, useStopMarkers, useVehicleMarker } from "@/components/map/useMapOverlays";
import { PlannerPanel } from "@/components/planner/PlannerPanel";
import { MobileSheet, sheetHeight } from "@/components/layout/MobileSheet";
import { NavigationHUD } from "@/components/nav/NavigationHUD";
import { usePlanner } from "@/hooks/usePlanner";
import { useNavigationSession } from "@/hooks/useNavigationSession";
import { usePip } from "@/hooks/usePip";
import "@/rotaflow.css";

// Mapa do roteiro = RotaFlow (Mapaflow) + recursos do sistema (Ver OS, Maps/Waze, Enviar Maps, compartilhar local, rastreio do admin).
function useMedia(query) {
  const [m, setM] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const fn = () => setM(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, [query]);
  return m;
}

const pt = (s) => (s.lat != null ? `${s.lat},${s.lng}` : s.address);
const gmapsDir = (base, stops, rtb) => {
  const list = stops.filter((s) => s.status !== "concluida");
  if (!list.length) return null;
  const dest = rtb ? `${base.lat},${base.lng}` : pt(list[list.length - 1]);
  const wps = (rtb ? list : list.slice(0, -1)).map(pt).join("|");
  return `https://www.google.com/maps/dir/?api=1&origin=${base.lat},${base.lng}&destination=${encodeURIComponent(dest)}&travelmode=driving${wps ? `&waypoints=${encodeURIComponent(wps)}` : ""}`;
};
const wazeUrl = (s) => (s.lat != null ? `https://waze.com/ul?ll=${s.lat},${s.lng}&navigate=yes` : `https://waze.com/ul?q=${encodeURIComponent(s.address)}&navigate=yes`);
const mapsUrl = (s) => `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(pt(s))}&travelmode=driving`;

function Header({ name, dark, setDark, onClose }) {
  return (
    <div className="flex items-center justify-between gap-2" data-testid="rf-header">
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="h-9 w-9 rounded-xl rf-brand grid place-items-center shrink-0"><Navigation className="h-4 w-4 text-white" fill="white" /></div>
        <div className="leading-tight min-w-0">
          <p className="font-extrabold text-white tracking-tight truncate">{name}</p>
          <p className="text-[11px] text-slate-400">Mastermaq · Roteiro e navegação</p>
        </div>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <button onClick={() => setDark(!dark)} className="rf-mini-btn" aria-label="Tema" data-testid="rf-theme-toggle">{dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}</button>
        <button onClick={onClose} className="rf-mini-btn" aria-label="Fechar" data-testid="rf-close-button"><X className="h-4 w-4" /></button>
      </div>
    </div>
  );
}

function Peek({ planner, onStart }) {
  const r = planner.stale ? null : planner.routes[planner.selectedRoute];
  return (
    <div className="flex items-center gap-3" data-testid="sheet-peek">
      <div className="min-w-0 flex-1">
        {r ? (
          <>
            <p className="font-mono text-xl font-bold text-white leading-none">{fmtDur(r.duration_s)}</p>
            <p className="text-xs text-slate-400 mt-1 font-mono">{fmtDist(r.distance_m)} · {planner.stops.length} paradas</p>
          </>
        ) : <p className="font-bold text-white truncate">{planner.loading ? "Calculando rota..." : `${planner.stops.length} paradas · calcule a rota`}</p>}
      </div>
      {r && onStart && (
        <button onClick={(e) => { e.stopPropagation(); onStart(); }} className="rf-btn-go h-11 px-5 rounded-2xl text-sm" data-testid="sheet-start-navigation-button">
          <Navigation className="h-4 w-4" fill="currentColor" />Iniciar
        </button>
      )}
    </div>
  );
}

function useAdminMirror(session, routeId, userName, stops) {
  const last = useRef(0);
  const was = useRef(false);
  const sentLeg = useRef(null);
  const chan = useRef(null);
  useEffect(() => {
    if (!supabase || !routeId) return undefined;
    chan.current = supabase.channel(`tracking-${routeId}`).subscribe();
    return () => { supabase.removeChannel(chan.current); chan.current = null; };
  }, [routeId]);
  useEffect(() => {
    if (session.active && !was.current) sysApi.post("/tracking/session/start", { route_id: routeId, technician_name: userName || "" }).catch(() => {});
    if (!session.active && was.current) {
      sysApi.post("/tracking/session/stop", { route_id: routeId }).catch(() => {});
      chan.current?.send({ type: "broadcast", event: "end", payload: {} });
    }
    was.current = session.active;
  }, [session.active, routeId, userName]);
  useEffect(() => {
    const d = session.nav?.display;
    if (!session.active || !d) return;
    const os = stops.find((s) => s.id === session.targetKey)?.os_number || null;
    const live = { route_id: routeId, lat: d.lat, lng: d.lng, heading: session.nav.heading || 0, speed: 0, technician: userName || "", active_os: os, active_status: "in_transit" };
    chan.current?.send({ type: "broadcast", event: "gps", payload: live });
    const newLeg = session.leg && sentLeg.current !== session.leg;
    if (!newLeg && Date.now() - last.current < 5000) return;
    last.current = Date.now();
    const body = { ...live };
    if (newLeg) {
      sentLeg.current = session.leg;
      const pts = session.legPath?.points || [];
      const step = Math.max(1, Math.ceil(pts.length / 300));
      body.nav_path = pts.filter((_, i) => i % step === 0 || i === pts.length - 1).map((p) => ({ lat: p.lat, lng: p.lng }));
      body.nav_distance_meters = Math.round(session.leg.distance_m || 0);
      body.nav_duration_in_traffic_seconds = Math.round(session.leg.duration_s || 0);
      body.nav_destination_lat = session.target?.lat;
      body.nav_destination_lng = session.target?.lng;
      chan.current?.send({ type: "broadcast", event: "nav", payload: body });
    }
    sysApi.post("/tracking/gps", body).catch(() => {});
  }, [session.active, session.nav, session.leg, session.legPath, session.target, session.targetKey, routeId, userName, stops]);
}

// Admin: só acompanha o técnico (posição + trajeto atual) em tempo real.
function useLiveTech(map, routeId, enabled) {
  const [live, setLive] = useState(null);
  const line = useRef(null);
  useEffect(() => {
    if (!enabled) return undefined;
    const apply = (p) => setLive((prev) => (p?.active === false ? null : { ...(prev || {}), ...p }));
    const poll = () => sysApi.get(`/tracking/live/${routeId}`).then((r) => r.data && apply(r.data)).catch(() => {});
    poll();
    const t = setInterval(poll, 10000);
    const ch = supabase?.channel(`tracking-${routeId}`)
      .on("broadcast", { event: "gps" }, ({ payload }) => apply({ ...payload, active: true }))
      .on("broadcast", { event: "nav" }, ({ payload }) => apply(payload))
      .on("broadcast", { event: "end" }, () => apply({ active: false }))
      .subscribe();
    return () => { clearInterval(t); if (ch) supabase.removeChannel(ch); };
  }, [routeId, enabled]);
  useEffect(() => {
    if (!map || !enabled) return;
    const path = live?.nav_path?.length > 1 ? live.nav_path : null;
    if (!path) { line.current?.setMap(null); line.current = null; return; }
    if (!line.current) line.current = new window.google.maps.Polyline({ map, strokeColor: "#3B82F6", strokeWeight: 7, strokeOpacity: 0.95, zIndex: 3 });
    line.current.setPath(path);
  }, [map, live?.nav_path, enabled]);
  useEffect(() => () => line.current?.setMap(null), []);
  return live && live.lat != null ? { lat: Number(live.lat), lng: Number(live.lng), heading: live.heading || 0 } : null;
}

const etaMsg = (o, technician, seconds) => {
  const t = new Date(Date.now() + seconds * 1000);
  const hhmm = `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
  const addr = `${o.address || ""} ${o.number || ""}, ${o.neighborhood || ""} - ${o.city || ""}`.trim();
  return `Olá, *Mastermaq Assistência Técnica Serviço Autorizado*, informa que o técnico *${technician || ""}* chegará ao destino às *${hhmm}*.\n\nOS ${o.os_number} - ${o.customer_name || ""}\n${addr}\n${o.phone1 || ""} *Caso o seu produto se enquadre em uma das seguintes categorias — ar-condicionado, geladeira, frigobar, cervejeira, freezer ou máquina de gelo —, favor mantê-lo ligado até a chegada do técnico.*`;
};
const sendEta = (stop, technician, seconds) => {
  const o = { ...(stop.order || {}), ...stop };
  const phone = String(o.phone1 || "").replace(/\D/g, "");
  if (!phone) { toast.error(`OS ${o.os_number} sem telefone`); return; }
  if (!seconds) { toast.error("Sem previsão: calcule a rota primeiro."); return; }
  window.open(`https://wa.me/${phone.startsWith("55") ? phone : `55${phone}`}?text=${encodeURIComponent(etaMsg(o, technician, seconds))}`, "_blank");
};

function Workspace({ config, routeId, routeName, orders, onPersistOrders, onViewOS, onClose, userName, technician, isAdmin, dark, setDark }) {
  const base = config.base;
  const isDesktop = useMedia("(min-width: 1024px)");
  const [map, setMap] = useState(null);
  const planner0 = usePlanner(base, { routeId, routeName, orders, onPersistOrders: isAdmin ? null : onPersistOrders, readOnly: isAdmin });
  const { setStopStatus: setStatus0, stops: stops0 } = planner0;
  const setStopStatusSynced = useCallback((id, done) => {
    setStatus0(id, done);
    const s = stops0.find((x) => x.id === id);
    if (s?.os_number) sysApi.post("/tracking/stop-status", { route_id: routeId, os_number: String(s.os_number), status: done ? "completed" : "pending" }).catch(() => {});
  }, [setStatus0, stops0, routeId]);
  const planner = isAdmin ? { ...planner0, reorder: () => {}, removeStop: () => {}, addStop: () => false, toggleReturn: () => {} } : { ...planner0, setStopStatus: setStopStatusSynced };
  const { setStopStatus } = planner;
  const completeStop = useCallback((id) => setStopStatus(id, true), [setStopStatus]);
  const session = useNavigationSession({ base, stops: planner.stops.filter((s) => s.lat != null), returnToBase: planner.returnToBase, ensureSaved: planner.ensureSaved, completeStop });
  const [selectedId, setSelectedId] = useState(null);
  const [satellite, setSatellite] = useState(false);
  const [traffic, setTraffic] = useState(false);
  const [follow, setFollow] = useState(false);
  const [myLoc, setMyLoc] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [snap, setSnap] = useState("peek");
  const trafficLayer = useRef(null);
  const navStarted = useRef(false);
  useAdminMirror(session, routeId, userName, planner.stops);
  const pip = usePip(session);
  const liveTech = useLiveTech(map, routeId, isAdmin);
  // ETA (s) até cada parada pela rota calculada: soma dos trechos.
  const etaById = useMemo(() => {
    const r = !planner.stale && planner.routes[planner.selectedRoute];
    if (!r) return {};
    let acc = 0;
    const out = {};
    planner.stops.filter((s) => s.lat != null).forEach((s, i) => { acc += r.legs[i]?.duration_s || 0; out[s.id] = acc; });
    return out;
  }, [planner.routes, planner.selectedRoute, planner.stale, planner.stops]);

  useEffect(() => {
    const st = Object.fromEntries(planner.stops.filter((s) => s.os_number).map((s) => [s.os_number, s.status === "concluida" ? "completed" : "pending"]));
    if (!isAdmin && Object.keys(st).length) sysApi.post("/tracking/session/stop-statuses", { route_id: routeId, stop_statuses: st }).catch(() => {});
  }, [planner.stops, routeId, isAdmin]);

  const pad = useCallback(() => (isDesktop
    ? { top: 80, right: 110, bottom: 80, left: sidebarOpen ? 470 : 90 }
    : { top: 80, right: 70, bottom: sheetHeight(snap) + 30, left: 30 }), [isDesktop, sidebarOpen, snap]);

  const overview = useCallback(() => {
    if (!map) return;
    const lc = planner.legCompare?.routes?.[planner.legCompare.selected];
    const r = lc || (!planner.stale && planner.routes[planner.selectedRoute]);
    const pts = r ? decodePolyline(r.polyline) : [base, ...planner.stops.filter((s) => s.lat != null)];
    flyTo(map, cameraForPoints(map, pts, pad()), 1400);
  }, [map, planner.routes, planner.selectedRoute, planner.stale, planner.stops, planner.legCompare, base, pad]);

  useEffect(() => {
    if (map && planner.routes.length && !session.active) overview();
  }, [map, planner.routes, planner.legCompare?.routes]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map || !selectedId || session.active) return;
    const s = planner.stops.find((x) => x.id === selectedId);
    if (s?.lat != null) flyTo(map, { center: { lat: s.lat, lng: s.lng }, zoom: 16.5, tilt: 45 }, 1100);
    if (!isDesktop) setSnap("half");
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (map) map.setMapTypeId(satellite ? "hybrid" : "roadmap"); }, [map, satellite]);
  useEffect(() => {
    if (!map) return;
    if (!trafficLayer.current) trafficLayer.current = new window.google.maps.TrafficLayer();
    trafficLayer.current.setMap(traffic ? map : null);
  }, [map, traffic]);
  useEffect(() => {
    if (!map) return undefined;
    const l = map.addListener("dragstart", () => setFollow(false));
    return () => l.remove();
  }, [map]);

  useEffect(() => {
    if (!session.active) {
      if (navStarted.current) { navStarted.current = false; setFollow(false); overview(); }
      return;
    }
    const d = session.nav?.display;
    if (!navStarted.current && d && map) {
      navStarted.current = true;
      flyTo(map, { center: offsetPoint(d, session.nav.heading, 55), zoom: 18.3, tilt: 62, heading: session.nav.heading }, 1600).then((ok) => ok && setFollow(true));
    }
  }, [session.active, session.nav, map, overview]);

  const vehicle = useMemo(() => {
    if (session.active) return session.nav ? { ...session.nav.display, heading: session.nav.heading } : null;
    return isAdmin ? liveTech : myLoc;
  }, [session.active, session.nav, myLoc, isAdmin, liveTech]);

  const located = useMemo(() => planner.stops.filter((s) => s.lat != null), [planner.stops]);
  const lc = planner.legCompare;
  const shownRoutes = lc?.routes?.length ? lc.routes : planner.stale ? [] : planner.routes;
  const onSelectRoute = lc?.routes?.length ? (i) => planner.setLegCompare({ ...lc, selected: i }) : planner.setSelectedRoute;
  useRouteOverlays(map, shownRoutes, lc?.routes?.length ? lc.selected : planner.selectedRoute, onSelectRoute, session.active);
  useNavLegOverlay(map, session.legPath, session.leg, session.nav?.seg, session.nav?.display);
  useVehicleMarker(map, vehicle, follow && session.active);
  useStopMarkers(map, base, located, selectedId, session.active ? session.targetKey : null, (k) => {
    if (k === "base") flyTo(map, { center: { lat: base.lat, lng: base.lng }, zoom: 16.5 }, 900);
    else { setSelectedId(k); setSidebarOpen(true); }
  });

  const recenter = () => {
    if (session.active && session.nav) {
      const d = session.nav.display;
      flyTo(map, { center: offsetPoint(d, session.nav.heading, 55), zoom: 18.3, tilt: 62, heading: session.nav.heading }, 900).then((ok) => ok && setFollow(true));
      return undefined;
    }
    if (!navigator.geolocation) return toast.error("GPS indisponível neste navegador.");
    navigator.geolocation.getCurrentPosition(
      (p) => { const loc = { lat: p.coords.latitude, lng: p.coords.longitude, heading: p.coords.heading || 0 }; setMyLoc(loc); flyTo(map, { center: loc, zoom: 16.5 }, 1100); },
      (e) => toast.error(e.code === 1 ? "Permissão de localização negada." : "Não foi possível obter sua localização."),
      { enableHighAccuracy: true, timeout: 15000 }
    );
    return undefined;
  };

  const navOverview = () => {
    setFollow(false);
    const pts = session.legPath ? [...session.legPath.points] : [base];
    if (session.nav) pts.push(session.nav.display);
    flyTo(map, cameraForPoints(map, pts, { top: 200, right: 80, bottom: 230, left: 80 }), 1300);
  };

  const startNav = (key) => { setSelectedId(null); setSnap("peek"); session.start(key); };

  // Sem OS: o backend escolhe a próxima OS não concluída do roteiro.
  const share = async (s) => {
    try {
      const { data } = await sysApi.post("/tracking/share-token", { route_id: routeId, os_number: s?.os_number ? String(s.os_number) : null });
      const url = `${window.location.origin}/track/${data.token}`;
      const phone = String(data.phone || "").replace(/\D/g, "");
      const text = `Olá${data.customer_name ? `, ${data.customer_name}` : ""}! A *Mastermaq Assistência Técnica* informa que o técnico está a caminho (OS ${data.os_number}). Acompanhe o trajeto em tempo real: ${url}`;
      window.open(`https://wa.me/${phone ? (phone.startsWith("55") ? phone : `55${phone}`) : ""}?text=${encodeURIComponent(text)}`, "_blank");
      navigator.clipboard?.writeText(url).catch(() => {});
      toast.success(`Link da OS ${data.os_number} copiado e WhatsApp aberto`);
    } catch (e) { toast.error(apiError(e)); }
  };

  const missing = planner.stops.filter((s) => s.lat == null || s.precision === "approximate");
  const dirUrl = gmapsDir(base, planner.stops, planner.returnToBase);
  const extra = (
    <div className="space-y-2">
      {missing.length > 0 && (
        <p className="text-xs text-amber-300 rf-card !p-3" data-testid="rf-missing-coords">
          Sem ponto exato: {missing.map((s) => `OS ${s.os_number || s.label}${s.lat == null ? " (fora do mapa)" : ""}`).join(", ")} — confira número, bairro e cidade.
        </p>
      )}
      <a href={dirUrl || "#"} target="_blank" rel="noreferrer" onClick={(e) => !dirUrl && e.preventDefault()}
        className="rf-btn-ghost w-full h-11 rounded-xl text-sm" data-testid="rf-send-maps-button"><Send className="h-4 w-4" />Enviar roteiro para o Google Maps</a>
      {isAdmin && (
        <>
          <button onClick={() => share()}
            className="rf-btn-primary w-full h-11 rounded-xl text-sm" data-testid="rf-share-route-button"><Share2 className="h-4 w-4" />Compartilhar rota</button>
          <p className="text-xs text-slate-400 text-center" data-testid="rf-live-status">{liveTech ? "Técnico em deslocamento — posição ao vivo no mapa" : "Aguardando o técnico iniciar a navegação"}</p>
        </>
      )}
    </div>
  );
  const stopExtra = (s) => (
    <div className="grid grid-cols-2 gap-2 mt-2">
      {s.os_number && <button onClick={() => onViewOS?.(s.os_number)} className="rf-btn-ghost h-10 rounded-xl text-xs" data-testid="stop-view-os-button"><Eye className="h-4 w-4" />Ver OS</button>}
      {s.os_number && <button onClick={() => sendEta(s, technician, etaById[s.id])} className="rf-btn-ghost h-10 rounded-xl text-xs" data-testid="stop-send-eta-button"><Clock className="h-4 w-4" />Enviar previsão</button>}
      {s.os_number && !isAdmin && <button onClick={() => share(s)} className="rf-btn-ghost h-10 rounded-xl text-xs" data-testid="stop-share-location-button"><Share2 className="h-4 w-4" />Compartilhar local</button>}
      <a href={mapsUrl(s)} target="_blank" rel="noreferrer" className="rf-btn-ghost h-10 rounded-xl text-xs" data-testid="stop-gmaps-button"><MapIcon className="h-4 w-4" />Google Maps</a>
      <a href={wazeUrl(s)} target="_blank" rel="noreferrer" className="rf-btn-ghost h-10 rounded-xl text-xs" data-testid="stop-waze-button"><Navigation className="h-4 w-4" />Waze</a>
    </div>
  );

  const header = <Header name={routeName} dark={dark} setDark={setDark} onClose={onClose} />;
  const panel = (
    <PlannerPanel planner={{ ...planner, hideSaved: true }} base={base} selectedId={selectedId} setSelectedId={setSelectedId}
      onStartNav={isAdmin ? () => toast.error("Só o técnico inicia a navegação.") : startNav} gpsMode={session.gpsMode} setGpsMode={session.setGpsMode} header={isDesktop ? header : null} extra={extra} stopExtra={stopExtra} />
  );

  return (
    <div className={`relative h-full w-full overflow-hidden rf-surface ${isAdmin ? "rf-readonly" : ""}`} data-testid="map-workspace">
      <MapCanvas config={{ ...config, dark }} onReady={setMap} />
      <AnimatePresence>
        {!session.active && isDesktop && sidebarOpen && (
          <motion.aside key="sb" initial={{ x: -440, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -440, opacity: 0 }}
            transition={{ type: "spring", damping: 26, stiffness: 220 }}
            className="absolute left-4 top-4 bottom-4 w-[420px] z-20 rf-glass rounded-3xl overflow-y-auto p-5 rf-scroll" data-testid="desktop-sidebar">
            {panel}
          </motion.aside>
        )}
      </AnimatePresence>
      {!session.active && isDesktop && (
        <button onClick={() => setSidebarOpen(!sidebarOpen)} data-testid="sidebar-toggle-button"
          className="absolute top-8 z-20 rf-ctl transition-[left] duration-300" style={{ left: sidebarOpen ? 448 : 16 }} aria-label="Painel">
          {sidebarOpen ? <ChevronLeft className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </button>
      )}
      {!session.active && !isDesktop && (
        <>
          <div className="absolute top-3 left-3 right-16 z-20 rf-glass rounded-2xl px-3 py-2">{header}</div>
          <MobileSheet snap={snap} setSnap={setSnap} peek={<Peek planner={planner} onStart={isAdmin ? null : () => startNav()} />}>{panel}</MobileSheet>
        </>
      )}
      <MapControls map={map} satellite={satellite} setSatellite={setSatellite} traffic={traffic} setTraffic={setTraffic}
        onRecenter={recenter} following={follow && session.active}
        className={`absolute z-20 ${session.active ? "right-3 sm:right-5 top-[38%]" : isDesktop ? "right-5 bottom-8" : "right-3 top-3"}`} />
      <AnimatePresence>
        {session.active && <NavigationHUD session={session} following={follow} onOverview={navOverview} onRecenter={recenter}
          onPip={pip.supported ? async () => { if (!(await pip.enter())) toast.error("Não foi possível abrir a janela flutuante neste aparelho."); } : null}
          onSendEta={() => {
            const s = planner.stops.find((x) => x.id === session.targetKey);
            if (!s?.os_number) { toast.error("Esta parada não é uma OS."); return; }
            sendEta(s, technician || userName, session.nav?.remainingS);
          }} />}
      </AnimatePresence>
    </div>
  );
}

export function RotaFlowMap({ open, onClose, routeId, routeName, orders, onPersistOrders, onViewOS, userName, userRole, technician }) {
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(null);
  const [dark, setDark] = useState(() => localStorage.getItem("rf-theme") === "dark");
  useEffect(() => { localStorage.setItem("rf-theme", dark ? "dark" : "light"); }, [dark]);
  useEffect(() => {
    if (open && !config) api.get("/config").then((r) => setConfig(r.data)).catch((e) => setError(apiError(e)));
  }, [open, config]);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className={`rf-root ${dark ? "rf-dark" : "rf-light"} max-w-none w-screen h-[100dvh] p-0 border-0 rounded-none left-0 top-0 translate-x-0 translate-y-0 [&>button]:hidden`} data-testid="route-map-dialog">
        <DialogTitle className="sr-only">Mapa do roteiro</DialogTitle>
        {error ? <div className="h-full grid place-items-center text-sm text-slate-400 rf-surface">{error}</div>
          : !config ? <div className="h-full grid place-items-center rf-surface"><div className="rf-spinner" /></div>
            : <Workspace key={dark ? "d" : "l"} config={config} routeId={routeId} routeName={routeName} orders={orders} onPersistOrders={onPersistOrders}
              onViewOS={onViewOS} onClose={onClose} userName={userName} technician={technician} isAdmin={userRole !== "technician"} dark={dark} setDark={setDark} />}
      </DialogContent>
    </Dialog>
  );
}
