import { useCallback, useEffect, useRef, useState } from "react";
import { bearing, haversine, offsetPoint, pointAt } from "@/lib/geo";

const SIM_SPEED_MS = 12;

function geoErrorMessage(err) {
  if (err.code === 1) return "Permissão de localização negada. Ative a localização nas configurações do navegador.";
  if (err.code === 3) return "Sinal de GPS fraco. Procurando sua posição...";
  return "Localização indisponível no momento.";
}

export function useGpsSource({ mode, running, simPath, simSpeed }) {
  const [fix, setFix] = useState(null);
  const [error, setError] = useState(null);
  const smooth = useRef(null);
  const along = useRef(0);
  const offsetUntil = useRef(0);

  useEffect(() => {
    if (!running || mode !== "device") return undefined;
    if (!("geolocation" in navigator)) {
      setError("Este navegador não oferece acesso ao GPS.");
      return undefined;
    }
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const c = pos.coords;
        if (c.accuracy > 150 && smooth.current) return;
        const raw = { lat: c.latitude, lng: c.longitude };
        const prev = smooth.current;
        let next = raw;
        if (prev) {
          const a = c.accuracy <= 15 ? 0.65 : c.accuracy <= 40 ? 0.4 : 0.2;
          next = { lat: prev.lat + (raw.lat - prev.lat) * a, lng: prev.lng + (raw.lng - prev.lng) * a };
        }
        let heading = prev?.heading ?? null;
        if (c.heading != null && !Number.isNaN(c.heading) && (c.speed || 0) > 1.5) heading = c.heading;
        else if (prev && haversine(prev, next) > 3) heading = bearing(prev, next);
        smooth.current = { ...next, heading };
        setError(null);
        setFix({ ...next, heading, speed: c.speed, accuracy: c.accuracy, ts: pos.timestamp });
      },
      (err) => setError(geoErrorMessage(err)),
      { enableHighAccuracy: true, maximumAge: 1000, timeout: 20000 }
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [running, mode]);

  useEffect(() => {
    along.current = 0;
    offsetUntil.current = 0;
  }, [simPath]);

  useEffect(() => {
    if (!running || mode !== "sim" || !simPath) return undefined;
    const tick = () => {
      along.current = Math.min(simPath.total, along.current + SIM_SPEED_MS * simSpeed);
      let p = pointAt(simPath, along.current);
      if (Date.now() < offsetUntil.current) p = { ...offsetPoint(p, (p.heading + 90) % 360, 85), heading: p.heading };
      setFix({ lat: p.lat, lng: p.lng, heading: p.heading, speed: SIM_SPEED_MS * simSpeed, accuracy: 5, ts: Date.now() });
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [running, mode, simPath, simSpeed]);

  const deviate = useCallback(() => {
    offsetUntil.current = Date.now() + 15000;
  }, []);

  const reset = useCallback(() => {
    smooth.current = null;
    setFix(null);
    setError(null);
  }, []);

  return { fix, error, deviate, reset };
}
