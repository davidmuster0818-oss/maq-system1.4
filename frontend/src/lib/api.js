import axios from "axios";

// Cliente do mapa RotaFlow: endpoints em /api/rf, com o token de login do sistema.
export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api/rf`, timeout: 20000 });
export const sysApi = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`, timeout: 20000 });

[api, sysApi].forEach((c) => c.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
}));

export function apiError(e) {
  if (!e?.response) return "Sem conexão com o servidor. Verifique sua internet.";
  const d = e.response.data?.detail;
  if (d == null) return "Algo deu errado. Tente novamente.";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  return d.msg || String(d);
}
