const brlFmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export const brl = (v) => brlFmt.format(Number(v || 0));

export const fmtDate = (s) => {
  if (!s) return "-";
  const [y, m, d] = s.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};

const iso = (d) => {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
};

export const todayIso = () => iso(new Date());

export const PERIODS = [
  { value: "hoje", label: "Hoje" },
  { value: "semana", label: "Esta semana" },
  { value: "mes", label: "Este mês" },
  { value: "mes_anterior", label: "Mês anterior" },
  { value: "30d", label: "Últimos 30 dias" },
  { value: "ano", label: "Este ano" },
  { value: "custom", label: "Personalizado" },
];

export const periodRange = (preset) => {
  const now = new Date();
  if (preset === "hoje") return { start: iso(now), end: iso(now) };
  if (preset === "semana") {
    const s = new Date(now);
    s.setDate(now.getDate() - ((now.getDay() + 6) % 7));
    const e = new Date(s);
    e.setDate(s.getDate() + 6);
    return { start: iso(s), end: iso(e) };
  }
  if (preset === "mes_anterior") {
    return { start: iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)), end: iso(new Date(now.getFullYear(), now.getMonth(), 0)) };
  }
  if (preset === "30d") {
    const s = new Date(now);
    s.setDate(now.getDate() - 29);
    return { start: iso(s), end: iso(now) };
  }
  if (preset === "ano") return { start: `${now.getFullYear()}-01-01`, end: `${now.getFullYear()}-12-31` };
  return { start: iso(new Date(now.getFullYear(), now.getMonth(), 1)), end: iso(new Date(now.getFullYear(), now.getMonth() + 1, 0)) };
};

export const groupKey = (dateStr, mode) => {
  if (mode === "mes") return dateStr.slice(0, 7);
  if (mode === "semana") {
    const d = new Date(`${dateStr}T12:00:00`);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    return iso(d);
  }
  return dateStr;
};

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

export const groupLabel = (key, mode) => {
  if (mode === "mes") {
    const [y, m] = key.split("-");
    return `${MONTHS[Number(m) - 1]} de ${y}`;
  }
  if (mode === "semana") return `Semana de ${fmtDate(key)}`;
  return fmtDate(key);
};

export const change = (cur, prev) => {
  if (!prev) return cur ? null : 0;
  return ((cur - prev) / Math.abs(prev)) * 100;
};

export const METHODS = { cartao: "Cartão", pix: "Pix", dinheiro: "Dinheiro" };
export const STATUSES = { previsto: "Previsto", pago: "Pago", atrasado: "Em atraso" };
export const GROUPS = {
  entrada: { servico: "Serviço", peca: "Peça", taxa: "Taxa", outros: "Outros" },
  saida: { fixa: "Fixas", variavel: "Variáveis", outra: "Outras" },
};
