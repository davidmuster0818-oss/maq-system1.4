export const MOTO_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="48" height="48">
  <circle cx="32" cy="32" r="30" fill="#1a1a2e" stroke="#3b82f6" stroke-width="2"/>
  <g transform="translate(32,32) rotate(0)">
    <path d="M-6,-14 L0,-18 L6,-14 L4,-4 L6,10 L2,16 L-2,16 L-6,10 L-4,-4 Z" fill="#3b82f6"/>
    <circle cx="0" cy="-16" r="3" fill="#60a5fa"/>
    <path d="M-8,-6 L-12,-2 L-8,0 Z" fill="#60a5fa" opacity="0.7"/>
    <path d="M8,-6 L12,-2 L8,0 Z" fill="#60a5fa" opacity="0.7"/>
    <circle cx="-2" cy="14" r="2" fill="#f59e0b"/>
    <circle cx="2" cy="14" r="2" fill="#f59e0b"/>
  </g>
</svg>`;

export const createMotoIcon = (heading = 0) => {
  const svg = MOTO_SVG.replace('rotate(0)', `rotate(${heading})`);
  const encoded = encodeURIComponent(svg);
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encoded}`,
    scaledSize: { width: 48, height: 48 },
    anchor: { x: 24, y: 24 },
  };
};

export const STOP_COLORS = {
  next: { bg: '#3b82f6', border: '#1d4ed8', text: '#ffffff' },
  pending: { bg: '#f8fafc', border: '#94a3b8', text: '#334155' },
  completed: { bg: '#d1d5db', border: '#9ca3af', text: '#6b7280' },
};

export const createStopIcon = (number, status = 'pending') => {
  const colors = STOP_COLORS[status] || STOP_COLORS.pending;
  const pulse = status === 'next' ? `<animate attributeName="r" values="18;22;18" dur="1.5s" repeatCount="indefinite"/>` : '';
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="40" height="40">
  <circle cx="24" cy="24" r="18" fill="${colors.bg}" stroke="${colors.border}" stroke-width="3">${pulse}</circle>
  <text x="24" y="24" text-anchor="middle" dominant-baseline="central" font-family="Arial,sans-serif" font-size="16" font-weight="bold" fill="${colors.text}">${number}</text>
</svg>`;
  const encoded = encodeURIComponent(svg);
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encoded}`,
    scaledSize: { width: 40, height: 40 },
    anchor: { x: 20, y: 20 },
  };
};

export const MAP_STYLE = [
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi.park', stylers: [{ visibility: 'on' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#e0e0e0' }] },
  { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#f0f0f0' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#c9d6df' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#f5f5f5' }] },
];

export const ROUTE_POLYLINE_STYLES = [
  { strokeColor: '#ffffff', strokeOpacity: 1, strokeWeight: 10, zIndex: 1 },
  { strokeColor: '#93c5fd', strokeOpacity: 0.8, strokeWeight: 7, zIndex: 2 },
  { strokeColor: '#2563eb', strokeOpacity: 1, strokeWeight: 4, zIndex: 3 },
];
