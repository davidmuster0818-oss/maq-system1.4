import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Box, Compass, Layers, LocateFixed, Minus, Plus, TrafficCone, Satellite, Map as MapIcon } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { flyTo } from "@/lib/camera";

function Ctl({ testid, onClick, active, label, children }) {
  return (
    <button data-testid={testid} onClick={onClick} aria-label={label} title={label}
      className={`rf-ctl ${active ? "rf-ctl-active" : ""}`}>
      {children}
    </button>
  );
}

export function MapControls({ map, satellite, setSatellite, traffic, setTraffic, onRecenter, following, className = "" }) {
  const [heading, setHeading] = useState(0);
  const [tilt, setTilt] = useState(0);

  useEffect(() => {
    if (!map) return undefined;
    const l1 = map.addListener("heading_changed", () => setHeading(map.getHeading() || 0));
    const l2 = map.addListener("tilt_changed", () => setTilt(map.getTilt() || 0));
    return () => {
      l1.remove();
      l2.remove();
    };
  }, [map]);

  if (!map) return null;
  const zoom = (d) => flyTo(map, { zoom: map.getZoom() + d }, 320);
  const toggle3d = () => flyTo(map, tilt > 10 ? { tilt: 0, heading: 0 } : { tilt: 60, zoom: Math.max(map.getZoom(), 16.5), heading: (map.getHeading() || 0) + 25 }, 1100);

  return (
    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }}
      className={`flex flex-col gap-2 ${className}`} data-testid="map-controls">
      <Popover>
        <PopoverTrigger asChild>
          <button data-testid="map-layers-button" className="rf-ctl" aria-label="Camadas"><Layers className="h-5 w-5" /></button>
        </PopoverTrigger>
        <PopoverContent side="left" className="w-56 rf-glass border-white/10 text-slate-100 p-2 rounded-2xl">
          <p className="px-2 pt-1 pb-2 text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Tipo de mapa</p>
          <div className="grid grid-cols-2 gap-2">
            <button data-testid="map-mode-roadmap" onClick={() => setSatellite(false)} className={`rf-layer ${!satellite ? "rf-layer-on" : ""}`}><MapIcon className="h-4 w-4" />Mapa</button>
            <button data-testid="map-mode-satellite" onClick={() => setSatellite(true)} className={`rf-layer ${satellite ? "rf-layer-on" : ""}`}><Satellite className="h-4 w-4" />Satélite</button>
          </div>
          <button data-testid="map-traffic-toggle" onClick={() => setTraffic(!traffic)} className={`rf-layer w-full mt-2 ${traffic ? "rf-layer-on" : ""}`}>
            <TrafficCone className="h-4 w-4" />Trânsito ao vivo
          </button>
        </PopoverContent>
      </Popover>
      <Ctl testid="map-mode-3d-tilt" onClick={toggle3d} active={tilt > 10} label="Visão 3D"><Box className="h-5 w-5" /></Ctl>
      <Ctl testid="map-compass-button" onClick={() => flyTo(map, { heading: 0 }, 600)} label="Apontar para o norte">
        <Compass className="h-5 w-5 transition-transform" style={{ transform: `rotate(${-heading - 45}deg)` }} />
      </Ctl>
      <div className="rf-ctl-group">
        <button data-testid="map-zoom-in" onClick={() => zoom(1)} aria-label="Aproximar"><Plus className="h-5 w-5" /></button>
        <button data-testid="map-zoom-out" onClick={() => zoom(-1)} aria-label="Afastar"><Minus className="h-5 w-5" /></button>
      </div>
      <Ctl testid="recenter-gps-button" onClick={onRecenter} active={following} label="Minha localização"><LocateFixed className="h-5 w-5" /></Ctl>
    </motion.div>
  );
}
