import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

// Suppress ResizeObserver loop error (benign browser quirk)
const origError = window.addEventListener;
window.addEventListener('error', (e) => {
  if (e.message?.includes('ResizeObserver loop')) {
    e.stopImmediatePropagation();
  }
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Register service worker for PWA with auto-update (production only)
if ('serviceWorker' in navigator && window.location.hostname !== 'localhost'
    && !window.location.hostname.includes('preview.emergentagent.com')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').then((registration) => {
      setInterval(() => { try { registration.update(); } catch (_) {} }, 60 * 1000);
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        if (newWorker) {
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              newWorker.postMessage({ type: 'SKIP_WAITING' });
            }
          });
        }
      });
    }).catch(() => {});
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!refreshing) { refreshing = true; window.location.reload(); }
    });
  });
} else if ('serviceWorker' in navigator) {
  // In dev/preview, unregister any stale SW
  navigator.serviceWorker.getRegistrations().then(regs => regs.forEach(r => r.unregister()));
}
