import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { AlertTriangle, Clock, MapPin } from 'lucide-react';
import { supabase } from '@/lib/supabase';
import { cameraForPoints, flyTo } from '@/lib/camera';
import { fmtDist, haversine } from '@/lib/geo';
import { MapCanvas } from '@/components/map/MapCanvas';
import { useStopMarkers, useVehicleMarker } from '@/components/map/useMapOverlays';
import '../rotaflow.css';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const noop = () => {};

// Restante pela rota real: do ponto da rota mais próximo do técnico até o fim; tempo proporcional ao trecho.
function remaining(live, path) {
  if (!live || !path || live.lat == null) return null;
  const v = { lat: Number(live.lat), lng: Number(live.lng) };
  let near = 0, best = Infinity;
  path.forEach((p, i) => { const d = haversine(v, p); if (d < best) { best = d; near = i; } });
  let rest = 0, total = 0;
  for (let i = 1; i < path.length; i++) { const d = haversine(path[i - 1], path[i]); total += d; if (i > near) rest += d; }
  const dur = live.nav_duration_in_traffic_seconds || live.nav_duration_seconds;
  return { meters: rest, seconds: dur && total ? dur * (rest / total) : null };
}

function EtaBadge({ os, live, path }) {
  const r = remaining(live, path);
  const addr = [os?.address?.trim(), os?.neighborhood, os?.city].filter(Boolean).join(', ');
  const at = r?.seconds != null ? new Date(Date.now() + r.seconds * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : null;
  return (
    <div className="absolute left-3 right-3 bottom-4 z-10 rf-glass rounded-2xl px-4 py-3 sm:left-5 sm:right-auto sm:max-w-sm" data-testid="public-eta-badge">
      {r ? (
        <div className="flex items-baseline gap-3">
          <Clock className="h-4 w-4 text-blue-500 self-center" />
          <p className="font-mono text-xl font-bold text-white leading-none" data-testid="public-eta-time">{at || '--:--'}</p>
          <p className="text-xs text-slate-400 font-mono" data-testid="public-eta-distance">
            {r.seconds != null ? `${Math.max(1, Math.round(r.seconds / 60))} min · ` : ''}{fmtDist(r.meters)}
          </p>
        </div>
      ) : <p className="text-sm font-semibold text-white" data-testid="public-eta-waiting">Aguardando o técnico iniciar o deslocamento</p>}
      <p className="mt-1.5 text-xs text-slate-400 flex items-start gap-1.5" data-testid="public-eta-address"><MapPin className="h-3.5 w-3.5 shrink-0 mt-0.5" />{addr}</p>
    </div>
  );
}

// Link do consumidor: mesmo mapa RotaFlow do técnico, só a rota ao vivo até a OS (sem badges/botões/pop-ups).
function useLegLine(map, path) {
  const refs = useRef(null);
  useEffect(() => {
    if (!map) return;
    if (!path) { refs.current?.forEach((l) => l.setMap(null)); refs.current = null; return; }
    const g = window.google.maps;
    if (!refs.current) {
      refs.current = [
        new g.Polyline({ map, strokeColor: '#1E3A8A', strokeWeight: 15, zIndex: 2, clickable: false }),
        new g.Polyline({ map, strokeColor: '#3B82F6', strokeWeight: 10, zIndex: 3, clickable: false }),
      ];
    }
    refs.current.forEach((l) => l.setPath(path));
  }, [map, path]);
  useEffect(() => () => refs.current?.forEach((l) => l.setMap(null)), []);
}

function TrackMap({ data, live }) {
  const [map, setMap] = useState(null);
  const fitted = useRef(false);
  const dest = data.os?.lat != null ? { id: 'dest', lat: data.os.lat, lng: data.os.lng, status: 'pendente' } : null;
  const config = useMemo(() => ({ ...data.map, base: dest || { lat: -19.9167, lng: -43.9345 }, dark: false }), []); // eslint-disable-line react-hooks/exhaustive-deps
  const stops = useMemo(() => (dest ? [dest] : []), [dest?.lat, dest?.lng]); // eslint-disable-line react-hooks/exhaustive-deps
  const sameOs = live && (!live.active_os || String(live.active_os) === String(data.os?.os_number));
  const path = sameOs && live.nav_path?.length > 1 ? live.nav_path : null;
  const vehicle = live?.lat != null ? { lat: Number(live.lat), lng: Number(live.lng), heading: live.heading || 0 } : null;
  useLegLine(map, path);
  useVehicleMarker(map, vehicle, false);
  useStopMarkers(map, null, stops, null, 'dest', noop);
  useEffect(() => {
    if (!map || fitted.current || !dest) return;
    const pts = path || (vehicle ? [vehicle, dest] : null);
    if (!pts) { map.setCenter(dest); map.setZoom(15); return; }
    fitted.current = true;
    flyTo(map, cameraForPoints(map, pts, { top: 60, right: 40, bottom: 60, left: 40 }), 1200);
  }, [map, path, vehicle, dest]);
  return (
    <>
      <MapCanvas config={config} onReady={setMap} />
      <EtaBadge os={data.os} live={sameOs ? live : null} path={path} />
    </>
  );
}

export default function PublicTrackingPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [live, setLive] = useState(null);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/tracking/public/${token}`);
      setData(res.data);
      setLive(res.data.live);
      setError(null);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 410) setError('Este link expirou.');
      else if (status === 401) setError('Link inválido.');
      else if (status === 404) setError('OS não encontrada.');
      else setError('Não foi possível carregar a localização.');
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    const i = setInterval(fetchData, 3000);
    return () => clearInterval(i);
  }, [fetchData]);

  const routeId = data?.route_id;
  useEffect(() => {
    if (!supabase || !routeId) return undefined;
    const ch = supabase.channel(`tracking-${routeId}`)
      .on('broadcast', { event: 'gps' }, ({ payload }) => setLive((p) => ({ ...(p || {}), ...payload })))
      .on('broadcast', { event: 'nav' }, ({ payload }) => setLive((p) => ({ ...(p || {}), ...payload })))
      .on('broadcast', { event: 'end' }, () => setLive(null))
      .subscribe();
    return () => { supabase.removeChannel(ch); };
  }, [routeId]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md text-center" data-testid="public-tracking-error">
          <AlertTriangle className="h-12 w-12 text-amber-500 mx-auto mb-3" />
          <h1 className="text-lg font-semibold text-gray-900">{error}</h1>
        </div>
      </div>
    );
  }

  return (
    <div className="rf-root rf-light relative h-[100dvh] w-screen overflow-hidden rf-surface" data-testid="public-tracking-page">
      {data ? <TrackMap data={data} live={live} /> : <div className="h-full grid place-items-center"><div className="rf-spinner" /></div>}
    </div>
  );
}
