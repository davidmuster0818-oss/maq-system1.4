const rad = (d) => (d * Math.PI) / 180;
const deg = (r) => (r * 180) / Math.PI;
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const active = new WeakMap();

export function isFlying(map) {
  return active.has(map);
}

export function cancelFly(map) {
  const c = active.get(map);
  if (c) c();
}

export function flyTo(map, target, duration = 1200) {
  cancelFly(map);
  const c = map.getCenter();
  const from = { lat: c.lat(), lng: c.lng(), zoom: map.getZoom(), tilt: map.getTilt() || 0, heading: map.getHeading() || 0 };
  const to = {
    lat: target.center?.lat ?? from.lat,
    lng: target.center?.lng ?? from.lng,
    zoom: target.zoom ?? from.zoom,
    tilt: target.tilt ?? from.tilt,
    heading: target.heading ?? from.heading,
  };
  const dh = ((to.heading - from.heading + 540) % 360) - 180;
  const start = performance.now();
  return new Promise((resolve) => {
    let raf;
    const stop = (done) => {
      cancelAnimationFrame(raf);
      active.delete(map);
      resolve(done);
    };
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration), k = ease(t);
      map.moveCamera({
        center: { lat: from.lat + (to.lat - from.lat) * k, lng: from.lng + (to.lng - from.lng) * k },
        zoom: from.zoom + (to.zoom - from.zoom) * k,
        tilt: from.tilt + (to.tilt - from.tilt) * k,
        heading: (from.heading + dh * k + 360) % 360,
      });
      if (t < 1) raf = requestAnimationFrame(step);
      else stop(true);
    };
    active.set(map, () => stop(false));
    raf = requestAnimationFrame(step);
  });
}

const merc = (p) => ({
  x: (p.lng + 180) / 360,
  y: (1 - Math.log(Math.tan(rad(p.lat)) + 1 / Math.cos(rad(p.lat))) / Math.PI) / 2,
});

export function cameraForPoints(map, pts, pad = { top: 80, right: 80, bottom: 80, left: 80 }) {
  const div = map.getDiv();
  const W = Math.max(100, div.clientWidth - pad.left - pad.right);
  const H = Math.max(100, div.clientHeight - pad.top - pad.bottom);
  const m = pts.map(merc);
  const xs = m.map((p) => p.x), ys = m.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const zoom = Math.min(17, Math.log2(W / 256 / Math.max(maxX - minX, 1e-9)), Math.log2(H / 256 / Math.max(maxY - minY, 1e-9)));
  const scale = 256 * 2 ** zoom;
  const cx = (minX + maxX) / 2 - (pad.left - pad.right) / 2 / scale;
  const cy = (minY + maxY) / 2 - (pad.top - pad.bottom) / 2 / scale;
  return {
    center: { lat: deg(Math.atan(Math.sinh(Math.PI * (1 - 2 * cy)))), lng: cx * 360 - 180 },
    zoom,
    tilt: 0,
    heading: 0,
  };
}
