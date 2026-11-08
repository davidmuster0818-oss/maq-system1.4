import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { loadGoogleMaps } from "@/lib/mapsLoader";

export function MapCanvas({ config, onReady }) {
  const el = useRef(null);
  const created = useRef(false);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    if (created.current) return undefined;
    created.current = true;
    const onAuth = () => {
      setState("error");
      setError("A chave do Google Maps foi recusada. Confirme que a Maps JavaScript API está ativada e que este domínio está autorizado na chave.");
    };
    window.addEventListener("gmaps:authfail", onAuth);
    loadGoogleMaps(config.maps_api_key)
      .then(async (g) => {
        const { Map, RenderingType } = await g.importLibrary("maps");
        await g.importLibrary("marker");
        const core = await g.importLibrary("core");
        const map = new Map(el.current, {
          center: { lat: config.base.lat, lng: config.base.lng },
          zoom: 14,
          mapId: config.map_id,
          renderingType: RenderingType?.VECTOR,
          colorScheme: config.dark ? core.ColorScheme?.DARK : core.ColorScheme?.LIGHT,
          disableDefaultUI: true,
          gestureHandling: "greedy",
          clickableIcons: false,
          isFractionalZoomEnabled: true,
          tiltInteractionEnabled: true,
          headingInteractionEnabled: true,
        });
        g.event.addListenerOnce(map, "tilesloaded", () => setState((s) => (s === "error" ? s : "ready")));
        onReady(map);
      })
      .catch((e) => {
        setState("error");
        setError(e.message);
      });
    return () => window.removeEventListener("gmaps:authfail", onAuth);
  }, [config, onReady]);

  return (
    <div className="absolute inset-0" data-testid="map-canvas">
      <motion.div ref={el} className="absolute inset-0" initial={{ opacity: 0, scale: 1.04 }}
        animate={{ opacity: state === "ready" ? 1 : 0, scale: state === "ready" ? 1 : 1.04 }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
      <AnimatePresence>
        {state === "loading" && (
          <motion.div key="sk" exit={{ opacity: 0 }} className="absolute inset-0 rf-map-skeleton" data-testid="map-loading">
            <div className="rf-map-skeleton-grid" />
          </motion.div>
        )}
      </AnimatePresence>
      {state === "error" && (
        <div className="absolute inset-0 grid place-items-center p-6 rf-surface" data-testid="map-error">
          <div className="max-w-md rf-glass rounded-3xl p-6 text-center">
            <AlertTriangle className="h-8 w-8 text-amber-400 mx-auto" />
            <p className="mt-3 font-bold text-white">Mapa indisponível</p>
            <p className="mt-2 text-sm text-slate-400">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}
