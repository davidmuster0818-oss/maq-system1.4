import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { api, apiError } from "@/lib/api";
import { buildPath, decodePolyline, fmtDist } from "@/lib/geo";
import { useGpsSource } from "@/hooks/useGpsSource";
import { useNavigator } from "@/hooks/useNavigator";

const REROUTE_COOLDOWN_MS = 2000;

function speak(text) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "pt-BR";
  window.speechSynthesis.speak(u);
}

function useVoice(enabled, nav, active) {
  const spoken = useRef({});
  useEffect(() => {
    if (!enabled || !active || !nav?.nextStep) return;
    const key = `${nav.stepIdx}`;
    const s = spoken.current;
    if (!s[key]) {
      s[key] = "start";
      speak(`${nav.distToNext > 300 ? `Em ${fmtDist(nav.distToNext)}, ` : ""}${nav.nextStep.instruction}`);
    } else if (s[key] === "start" && nav.distToNext < 150 && nav.distToNext > 20) {
      s[key] = "near";
      speak(`Em ${fmtDist(nav.distToNext)}, ${nav.nextStep.instruction}`);
    }
  }, [enabled, nav, active]);
  useEffect(() => { spoken.current = {}; }, [active]);
}

function useWakeLock(active) {
  useEffect(() => {
    if (!active || !navigator.wakeLock) return undefined;
    let lock = null;
    navigator.wakeLock.request("screen").then((l) => { lock = l; }).catch(() => {});
    return () => { lock?.release().catch(() => {}); };
  }, [active]);
}

export function useNavigationSession({ base, stops, returnToBase, ensureSaved, completeStop }) {
  const [active, setActive] = useState(false);
  const [paused, setPaused] = useState(false);
  const [gpsMode, setGpsMode] = useState("device");
  const [simSpeed, setSimSpeed] = useState(1);
  const [targetKey, setTargetKey] = useState(null);
  const [arrived, setArrived] = useState(null);
  const [leg, setLeg] = useState(null);
  const [phase, setPhase] = useState("idle");
  const [notice, setNotice] = useState(null);
  const [voice, setVoice] = useState(true);
  const legRef = useRef(null);
  legRef.current = leg;
  const lastPos = useRef(null);
  const lastReroute = useRef(0);
  const busy = useRef(false);

  const targets = useMemo(() => {
    const t = stops.filter((s) => s.status !== "concluida").map((s) => ({ key: s.id, label: s.label, address: s.address, lat: s.lat, lng: s.lng }));
    if (returnToBase && base) t.push({ key: "base", label: "Base operacional", address: base.address, lat: base.lat, lng: base.lng });
    return t;
  }, [stops, returnToBase, base]);
  const target = targets.find((t) => t.key === targetKey) || arrived || null;

  const legPath = useMemo(() => (leg ? buildPath(decodePolyline(leg.polyline)) : null), [leg]);
  const gps = useGpsSource({ mode: gpsMode, running: active && !paused, simPath: gpsMode === "sim" ? legPath : null, simSpeed });
  const nav = useNavigator(legPath, leg, active ? gps.fix : null);
  useVoice(voice, nav, active);
  useWakeLock(active);

  useEffect(() => {
    if (nav?.display) lastPos.current = { ...nav.display, heading: nav.heading };
  }, [nav]);

  const requestLeg = useCallback(async (from, tgt, reason) => {
    if (busy.current) return;
    busy.current = true;
    setPhase(reason === "reroute" ? "rerouting" : "routing");
    try {
      const heading = from.heading != null ? Math.round(from.heading) % 360 : undefined;
      const { data } = await api.post("/routes/nav-leg", { origin: { lat: from.lat, lng: from.lng }, heading, destination: { lat: tgt.lat, lng: tgt.lng } });
      const l = data.route.legs[0];
      setLeg({ ...l, polyline: l.polyline || data.route.polyline, traffic: l.traffic?.length ? l.traffic : data.route.traffic });
      setNotice(null);
      setPhase("guiding");
      if (reason === "reroute") toast.success("Rota recalculada");
    } catch (e) {
      setNotice(legRef.current ? `${apiError(e)} Mantendo a rota atual.` : apiError(e));
      setPhase(legRef.current ? "guiding" : "error");
    } finally {
      busy.current = false;
    }
  }, []);

  const start = useCallback(async (key, mode = gpsMode) => {
    const first = key ? targets.find((t) => t.key === key) : targets[0];
    if (!first) {
      toast.error("Não há paradas pendentes para navegar.");
      return;
    }
    const it = await ensureSaved();
    if (!it) return;
    gps.reset();
    setGpsMode(mode);
    setTargetKey(first.key);
    setArrived(null);
    setLeg(null);
    setNotice(null);
    setPaused(false);
    setActive(true);
    lastReroute.current = 0;
    if (mode === "sim") requestLeg(lastPos.current || { lat: base.lat, lng: base.lng }, first, "start");
    else setPhase("locating");
  }, [targets, ensureSaved, gps, gpsMode, base, requestLeg]);

  useEffect(() => {
    if (active && phase === "locating" && gps.fix && target) requestLeg(gps.fix, target, "start");
  }, [active, phase, gps.fix, target, requestLeg]);

  useEffect(() => {
    if (!active || phase !== "guiding" || !nav || !target) return;
    if (nav.arrived) {
      setArrived(target);
      setPhase("arrived");
      return;
    }
    if (nav.offRoute && Date.now() - lastReroute.current > REROUTE_COOLDOWN_MS && navigator.onLine && gps.fix) {
      lastReroute.current = Date.now();
      requestLeg(gps.fix, target, "reroute");
    }
  }, [nav, active, phase, target, gps.fix, requestLeg]);

  useEffect(() => {
    if (!active) return undefined;
    const offline = () => setNotice("Sem conexão. Seguindo com a rota já carregada.");
    const online = () => setNotice(null);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
    };
  }, [active]);

  const proceed = useCallback(async (complete) => {
    const cur = arrived || target;
    const idx = targets.findIndex((t) => t.key === cur?.key);
    const next = idx >= 0 ? targets[idx + 1] : targets[0];
    if (complete && cur && cur.key !== "base") await completeStop(cur.key);
    setArrived(null);
    if (!next) {
      setTargetKey(null);
      setPhase("finished");
      return;
    }
    setTargetKey(next.key);
    setLeg(null);
    lastReroute.current = 0;
    if (gpsMode === "device" && gps.fix) requestLeg(gps.fix, next, "start");
    else if (gpsMode === "sim") requestLeg(lastPos.current || cur, next, "start");
    else setPhase("locating");
  }, [arrived, target, targets, completeStop, gpsMode, gps.fix, requestLeg]);

  const stop = useCallback(() => {
    window.speechSynthesis?.cancel();
    setActive(false);
    setPaused(false);
    setLeg(null);
    setTargetKey(null);
    setArrived(null);
    setPhase("idle");
    setNotice(null);
  }, []);

  const retry = useCallback(() => {
    if (!target) return;
    if (gpsMode === "sim") requestLeg(lastPos.current || { lat: base.lat, lng: base.lng }, target, "start");
    else if (gps.fix) requestLeg(gps.fix, target, "start");
    else setPhase("locating");
  }, [target, gpsMode, gps.fix, base, requestLeg]);

  return {
    active, paused, gpsMode, setGpsMode, simSpeed, setSimSpeed, voice, setVoice,
    target, targetKey, arrived, leg, legPath, phase, notice, nav, gpsError: gps.error,
    remainingTargets: targets, start, stop, proceed, retry,
    togglePause: () => setPaused((p) => !p), deviate: gps.deviate,
  };
}
