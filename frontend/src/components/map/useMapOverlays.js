import { useEffect, useRef } from "react";
import { decodePolyline, lerpAngle, offsetPoint } from "@/lib/geo";
import { isFlying } from "@/lib/camera";

const ease = (t) => 1 - Math.pow(1 - t, 3);
const TRAFFIC = { SLOW: "#F59E0B", TRAFFIC_JAM: "#EF4444" };
const HOME_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>';
const CHECK_SVG = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17l9-10"/></svg>';

function trafficPolylines(g, map, pts, traffic, weight) {
  return (traffic || [])
    .filter((s) => TRAFFIC[s.speed] && s.end > s.start)
    .map((s) => new g.Polyline({ map, path: pts.slice(s.start, s.end + 1), strokeColor: TRAFFIC[s.speed], strokeWeight: weight, strokeOpacity: 1, zIndex: 4 }));
}

export function useRouteOverlays(map, routes, selectedIdx, onSelect, hidden) {
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  useEffect(() => {
    if (!map || hidden || !routes?.length) return undefined;
    const g = window.google.maps;
    const objs = [];
    let raf;
    routes.forEach((r, i) => {
      if (i === selectedIdx) return;
      const pl = new g.Polyline({ map, path: decodePolyline(r.polyline), strokeColor: "#64748B", strokeOpacity: 0.9, strokeWeight: 7, zIndex: 1 });
      pl.addListener("click", () => onSelectRef.current?.(i));
      objs.push(pl);
    });
    const sel = routes[selectedIdx] || routes[0];
    const pts = decodePolyline(sel.polyline);
    const outline = new g.Polyline({ map, path: [], strokeColor: "#1E3A8A", strokeWeight: 11, strokeOpacity: 1, zIndex: 2 });
    const main = new g.Polyline({ map, path: [], strokeColor: "#3B82F6", strokeWeight: 7, strokeOpacity: 1, zIndex: 3 });
    objs.push(outline, main);
    const t0 = performance.now();
    const tick = (now) => {
      const k = Math.min(1, (now - t0) / 1000);
      const sub = pts.slice(0, Math.max(2, Math.ceil(pts.length * ease(k))));
      outline.setPath(sub);
      main.setPath(sub);
      if (k < 1) raf = requestAnimationFrame(tick);
      else objs.push(...trafficPolylines(g, map, pts, sel.traffic, 7));
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      objs.forEach((o) => o.setMap(null));
    };
  }, [map, routes, selectedIdx, hidden]);
}

export function useNavLegOverlay(map, legPath, leg, seg, position) {
  const refs = useRef(null);
  useEffect(() => {
    if (!map || !legPath || !leg) return undefined;
    const g = window.google.maps;
    const outline = new g.Polyline({ map, path: legPath.points, strokeColor: "#1E3A8A", strokeWeight: 15, zIndex: 2 });
    const main = new g.Polyline({ map, path: legPath.points, strokeColor: "#3B82F6", strokeWeight: 10, zIndex: 3 });
    const traffic = trafficPolylines(g, map, legPath.points, leg.traffic, 10);
    refs.current = { outline, main };
    return () => {
      [outline, main, ...traffic].forEach((p) => p.setMap(null));
      refs.current = null;
    };
  }, [map, legPath, leg]);
  useEffect(() => {
    if (!refs.current || !legPath || seg == null) return;
    const rest = legPath.points.slice(seg + 1);
    if (position) rest.unshift(position);
    refs.current.main.setPath(rest);
    refs.current.outline.setPath(rest);
  }, [seg, legPath, position]);
}

function renderPin(el, w) {
  const cls = ["rf-pin"];
  if (w.kind === "base") cls.push("rf-pin-base");
  if (w.done) cls.push("rf-pin-done");
  if (w.selected) cls.push("rf-pin-selected");
  if (w.target) cls.push("rf-pin-target");
  const html = w.kind === "base" ? HOME_SVG : w.done ? CHECK_SVG : `<span>${Number(w.label)}</span>`;
  const sig = cls.join(" ") + html;
  if (el.dataset.sig === sig) return;
  el.dataset.sig = sig;
  el.className = cls.join(" ");
  el.innerHTML = `<div class="rf-pin-body">${html}</div><div class="rf-pin-tail"></div>`;
}

export function useStopMarkers(map, base, stops, selectedId, targetKey, onSelect) {
  const markers = useRef(new Map());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  useEffect(() => {
    if (!map) return;
    const { AdvancedMarkerElement } = window.google.maps.marker;
    const want = new Map();
    if (base) want.set("base", { kind: "base", pos: { lat: base.lat, lng: base.lng } });
    stops.forEach((s, i) => want.set(s.id, { kind: "stop", pos: { lat: s.lat, lng: s.lng }, label: i + 1, done: s.status === "concluida" }));
    for (const [k, m] of markers.current) {
      if (!want.has(k)) {
        m.map = null;
        markers.current.delete(k);
      }
    }
    for (const [k, w] of want) {
      let m = markers.current.get(k);
      if (!m) {
        const el = document.createElement("div");
        el.setAttribute("data-testid", `map-marker-${k}`);
        m = new AdvancedMarkerElement({ map, position: w.pos, content: el, gmpClickable: true });
        m.addListener("click", () => onSelectRef.current?.(k));
        markers.current.set(k, m);
      }
      m.position = w.pos;
      m.zIndex = k === selectedId || k === targetKey ? 1000 : w.kind === "base" ? 500 : 100;
      renderPin(m.content, { ...w, selected: k === selectedId, target: k === targetKey });
    }
  }, [map, base, stops, selectedId, targetKey]);
  useEffect(() => () => {
    markers.current.forEach((m) => { m.map = null; });
    markers.current.clear();
  }, [map]);
}

export function useVehicleMarker(map, target, follow) {
  const marker = useRef(null);
  const cur = useRef(null);
  const raf = useRef(0);
  const followRef = useRef(follow);
  followRef.current = follow;

  useEffect(() => {
    if (!map) return;
    if (!target) {
      if (marker.current) marker.current.map = null;
      marker.current = null;
      cur.current = null;
      return;
    }
    if (!marker.current) {
      const el = document.createElement("div");
      el.className = "rf-vehicle";
      el.setAttribute("data-testid", "vehicle-marker");
      el.innerHTML = '<div class="rf-vehicle-halo"></div><svg class="rf-vehicle-arrow" viewBox="0 0 40 40"><path d="M20 4 L33 34 L20 27 L7 34 Z"/></svg>';
      marker.current = new window.google.maps.marker.AdvancedMarkerElement({ map, position: target, content: el, zIndex: 2000 });
      cur.current = { lat: target.lat, lng: target.lng, heading: target.heading || 0 };
    }
    const from = { ...cur.current };
    const t0 = performance.now();
    cancelAnimationFrame(raf.current);
    const arrow = marker.current.content.querySelector("svg");
    const step = (now) => {
      if (!marker.current) return;
      const k = Math.min(1, (now - t0) / 950);
      const p = { lat: from.lat + (target.lat - from.lat) * k, lng: from.lng + (target.lng - from.lng) * k, heading: lerpAngle(from.heading, target.heading ?? from.heading, k) };
      cur.current = p;
      marker.current.position = { lat: p.lat, lng: p.lng };
      if (followRef.current && !isFlying(map)) map.moveCamera({ center: offsetPoint(p, p.heading, 55), heading: p.heading });
      arrow.style.transform = `rotate(${p.heading - (map.getHeading() || 0)}deg)`;
      if (k < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  }, [map, target]);

  useEffect(() => () => {
    cancelAnimationFrame(raf.current);
    if (marker.current) marker.current.map = null;
    marker.current = null;
  }, [map]);
}
