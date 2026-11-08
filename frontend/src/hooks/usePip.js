import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { haversine } from "@/lib/geo";

// Janela flutuante (PiP) da navegação: canvas -> vídeo. Fundo = imagem do mapa; rota + seta centralizada, sem badges.
const W = 300;
const Z = 16;
const IMG = 640;
const proj = (p) => {
  const s = 256 * 2 ** Z;
  const sin = Math.sin((p.lat * Math.PI) / 180);
  return { x: ((p.lng + 180) / 360) * s, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * s };
};

export const pipSupported = () => typeof document !== "undefined"
  && (document.pictureInPictureEnabled || typeof HTMLVideoElement.prototype.webkitSetPresentationMode === "function");

export function usePip(session) {
  const canvas = useRef(null);
  const video = useRef(null);
  const bg = useRef(null);
  const loading = useRef(false);
  const state = useRef(session);
  state.current = session;
  const [inPip, setInPip] = useState(false);

  const loadBg = useCallback(async (c) => {
    if (loading.current) return;
    loading.current = true;
    try {
      const { data } = await api.get("/static-map", { params: { lat: c.lat, lng: c.lng, zoom: Z }, responseType: "blob" });
      const img = await createImageBitmap(data);
      bg.current = { img, c };
    } catch { bg.current = bg.current || { img: null, c }; } finally { loading.current = false; }
  }, []);

  const draw = useCallback(() => {
    const ctx = canvas.current?.getContext("2d");
    const s = state.current;
    const v = s.nav?.display;
    if (!ctx) return;
    ctx.fillStyle = "#e5e7eb";
    ctx.fillRect(0, 0, W, W);
    if (!v) return;
    if (!bg.current || (bg.current.img && haversine(bg.current.c, v) > 120)) loadBg(v);
    const vp = proj(v);
    ctx.save();
    ctx.translate(W / 2, W / 2);
    ctx.rotate((-(s.nav.heading || 0) * Math.PI) / 180);
    if (bg.current?.img) {
      const bp = proj(bg.current.c);
      ctx.drawImage(bg.current.img, bp.x - vp.x - IMG / 2, bp.y - vp.y - IMG / 2);
    }
    const pts = s.legPath?.points?.slice(Math.max(0, (s.nav.seg ?? 0) + 1)) || [];
    if (pts.length) {
      ctx.lineJoin = "round"; ctx.lineCap = "round";
      [["#1E3A8A", 13], ["#3B82F6", 8]].forEach(([c, w]) => {
        ctx.strokeStyle = c; ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(0, 0);
        pts.forEach((p) => { const q = proj(p); ctx.lineTo(q.x - vp.x, q.y - vp.y); });
        ctx.stroke();
      });
    }
    ctx.restore();
    ctx.translate(W / 2, W / 2);
    ctx.fillStyle = "#1d4ed8"; ctx.strokeStyle = "#fff"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(0, -16); ctx.lineTo(12, 14); ctx.lineTo(0, 8); ctx.lineTo(-12, 14); ctx.closePath();
    ctx.fill(); ctx.stroke();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }, [loadBg]);

  useEffect(() => {
    if (!session.active || !pipSupported()) return undefined;
    const c = document.createElement("canvas");
    c.width = W; c.height = W;
    const vd = document.createElement("video");
    vd.muted = true; vd.playsInline = true; vd.autoplay = true;
    vd.setAttribute("data-testid", "pip-video");
    vd.style.cssText = "position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;bottom:0;left:0";
    document.body.appendChild(vd);
    canvas.current = c; video.current = vd;
    draw();
    vd.srcObject = c.captureStream(5);
    vd.play().catch(() => {});
    const t = setInterval(draw, 250);
    const onEnter = () => setInPip(true);
    const onLeave = () => setInPip(false);
    vd.addEventListener("enterpictureinpicture", onEnter);
    vd.addEventListener("leavepictureinpicture", onLeave);
    return () => {
      clearInterval(t);
      if (document.pictureInPictureElement === vd) document.exitPictureInPicture().catch(() => {});
      vd.srcObject?.getTracks().forEach((k) => k.stop());
      vd.remove();
      canvas.current = null; video.current = null; bg.current = null;
      setInPip(false);
    };
  }, [session.active, draw]);

  const enter = useCallback(async () => {
    const vd = video.current;
    if (!vd) return false;
    try {
      await vd.play().catch(() => {});
      if (vd.requestPictureInPicture) await vd.requestPictureInPicture();
      else vd.webkitSetPresentationMode("picture-in-picture");
      return true;
    } catch { return false; }
  }, []);

  // Ao sair do app com a navegação ativa, tenta abrir a janela sozinha.
  useEffect(() => {
    if (!session.active) return undefined;
    const ms = navigator.mediaSession;
    try { ms?.setActionHandler("enterpictureinpicture", enter); } catch { /* sem suporte */ }
    const onHide = () => { if (document.visibilityState === "hidden" && !document.pictureInPictureElement) enter(); };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      try { ms?.setActionHandler("enterpictureinpicture", null); } catch { /* sem suporte */ }
    };
  }, [session.active, enter]);

  return { enter, inPip, supported: pipSupported() };
}
