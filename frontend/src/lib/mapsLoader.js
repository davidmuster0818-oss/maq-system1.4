let promise = null;

export function loadGoogleMaps(key) {
  if (window.google?.maps?.Map) return Promise.resolve(window.google.maps);
  if (promise) return promise;
  promise = new Promise((resolve, reject) => {
    window.__rfMapsReady = () => resolve(window.google.maps);
    window.gm_authFailure = () => window.dispatchEvent(new Event("gmaps:authfail"));
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&loading=async&language=pt-BR&region=BR&libraries=marker,geometry&callback=__rfMapsReady`;
    s.async = true;
    s.onerror = () => {
      promise = null;
      s.remove();
      reject(new Error("Não foi possível carregar o Google Maps. Verifique a conexão."));
    };
    document.head.appendChild(s);
  });
  return promise;
}
