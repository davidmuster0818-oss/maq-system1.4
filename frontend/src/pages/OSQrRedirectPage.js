import { useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';

/**
 * Route hit by the QR code printed on OS stickers (`/os/:osNumber`).
 *
 * Behaviour (in order of priority):
 *  1. If `?t=<signed_token>` is present → /os-view/:osNumber?t=... (token-based public)
 *  2. If a session is active (localStorage token) → /service-orders?open=...
 *     (logged-in staff get the full editing modal)
 *  3. Otherwise → /os-view/:osNumber (UNSIGNED public view, NO login required)
 *
 * Rationale: the QR is printed once on a thermal label and is meant to be
 * scanned by the customer. We never want a public scan to land on /login —
 * the page must always show the OS, period. Sensitive fields are masked by
 * the backend (GET /api/os/public/by-number/{os_number}).
 */
export default function OSQrRedirectPage() {
  const { osNumber } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const t = params.get('t');
    const sessionToken = localStorage.getItem('token');

    if (t) {
      navigate(`/os-view/${osNumber}?t=${encodeURIComponent(t)}`, { replace: true });
      return;
    }
    if (sessionToken) {
      navigate(`/service-orders?open=${encodeURIComponent(osNumber || '')}`, { replace: true });
      return;
    }
    // Public scan — no login required, no token needed.
    navigate(`/os-view/${osNumber || ''}`, { replace: true });
  }, [osNumber, navigate, location.search]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <p className="text-sm text-gray-500" data-testid="os-qr-redirect-loading">Abrindo OS {osNumber}…</p>
    </div>
  );
}
