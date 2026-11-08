const R = 6371000;
const rad = (d) => (d * Math.PI) / 180;
const deg = (r) => (r * 180) / Math.PI;

export function decodePolyline(str) {
  const pts = [];
  if (!str) return pts;
  let i = 0, lat = 0, lng = 0;
  while (i < str.length) {
    for (let k = 0; k < 2; k++) {
      let b, shift = 0, result = 0;
      do {
        b = str.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      const v = result & 1 ? ~(result >> 1) : result >> 1;
      if (k === 0) lat += v; else lng += v;
    }
    pts.push({ lat: lat / 1e5, lng: lng / 1e5 });
  }
  return pts;
}

export function haversine(a, b) {
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function bearing(a, b) {
  const y = Math.sin(rad(b.lng - a.lng)) * Math.cos(rad(b.lat));
  const x = Math.cos(rad(a.lat)) * Math.sin(rad(b.lat)) - Math.sin(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(rad(b.lng - a.lng));
  return (deg(Math.atan2(y, x)) + 360) % 360;
}

export function offsetPoint(p, headingDeg, meters) {
  const h = rad(headingDeg);
  return {
    lat: p.lat + deg((meters * Math.cos(h)) / R),
    lng: p.lng + deg((meters * Math.sin(h)) / (R * Math.cos(rad(p.lat)))),
  };
}

export function buildPath(points) {
  const cum = [0];
  for (let i = 1; i < points.length; i++) cum.push(cum[i - 1] + haversine(points[i - 1], points[i]));
  return { points, cum, total: cum[cum.length - 1] || 0 };
}

function projectSeg(p, a, b) {
  const kx = (Math.cos(rad(p.lat)) * R * Math.PI) / 180, ky = (R * Math.PI) / 180;
  const ax = (a.lng - p.lng) * kx, ay = (a.lat - p.lat) * ky;
  const dx = (b.lng - p.lng) * kx - ax, dy = (b.lat - p.lat) * ky - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0;
  return { t, dist: Math.hypot(ax + dx * t, ay + dy * t) };
}

export function projectOnPath(path, p, hint = 0) {
  const { points, cum } = path;
  if (points.length < 2) return null;
  let best = null;
  const search = (s, e) => {
    for (let i = s; i < e; i++) {
      const r = projectSeg(p, points[i], points[i + 1]);
      if (!best || r.dist < best.dist) best = { ...r, seg: i };
    }
  };
  search(Math.max(0, hint - 20), Math.min(points.length - 1, hint + 250));
  if (best.dist > 60) search(0, points.length - 1);
  const a = points[best.seg], b = points[best.seg + 1];
  return {
    point: { lat: a.lat + (b.lat - a.lat) * best.t, lng: a.lng + (b.lng - a.lng) * best.t },
    offset: best.dist,
    seg: best.seg,
    along: cum[best.seg] + (cum[best.seg + 1] - cum[best.seg]) * best.t,
    heading: bearing(a, b),
  };
}

export function pointAt(path, along) {
  const { points, cum, total } = path;
  if (points.length < 2) return { ...points[0], heading: 0 };
  const d = Math.max(0, Math.min(total, along));
  let i = 0;
  while (i < cum.length - 2 && cum[i + 1] < d) i++;
  const a = points[i], b = points[i + 1];
  const seg = cum[i + 1] - cum[i] || 1;
  const t = (d - cum[i]) / seg;
  return { lat: a.lat + (b.lat - a.lat) * t, lng: a.lng + (b.lng - a.lng) * t, heading: bearing(a, b) };
}

export function lerpAngle(a, b, t) {
  const d = ((b - a + 540) % 360) - 180;
  return (a + d * t + 360) % 360;
}

export function fmtDist(m) {
  if (m == null) return "--";
  if (m < 1000) return `${Math.max(0, Math.round(m / 10) * 10)} m`;
  return `${(m / 1000).toLocaleString("pt-BR", { maximumFractionDigits: m < 10000 ? 1 : 0 })} km`;
}

export function fmtDur(s) {
  if (s == null) return "--";
  const min = Math.max(1, Math.round(s / 60));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), r = min % 60;
  return r ? `${h} h ${r} min` : `${h} h`;
}

export function fmtClock(date) {
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function fmtMoney(prices) {
  if (!prices?.length) return null;
  return prices.map((p) => p.amount.toLocaleString("pt-BR", { style: "currency", currency: p.currency })).join(" + ");
}
