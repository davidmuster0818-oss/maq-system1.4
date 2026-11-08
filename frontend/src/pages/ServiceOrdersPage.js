import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import DashboardLayout from '../components/DashboardLayout';
import LaudoModal from '../components/LaudoModal';
import SignatureModal from '../components/SignatureModal';
import SignatureViewModal from '../components/SignatureViewModal';
import { buildCopyHtml as buildCopyHtmlUtil, printOS as printOSUtil, sendWhatsAppCopy as sendWhatsAppCopyUtil } from '../utils/printUtils';
import { printOSLabel, printStoreLabel } from '../utils/printingService';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '../components/ui/dropdown-menu';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { ScrollArea } from '../components/ui/scroll-area';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { 
  Plus, 
  Search, 
  CalendarIcon, 
  MapPin, 
  Phone, 
  RefreshCw,
  ExternalLink,
  Loader2,
  Filter,
  X,
  Printer,
  FileText,
  Camera,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  PenTool,
  Eye,
  Trash2,
  Images,
  QrCode,
  Send,
  Check,
  ChevronDown,
  AlertTriangle,
  Tags
} from 'lucide-react';

// In production, use relative URLs (same origin)
// In development, use REACT_APP_BACKEND_URL
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Logo URLs
const MASTERMAQ_LOGO = '/assets/mastermaq-logo.png';
const TELECONTROL_LOGO = '/assets/telecontrol-logo.png';
const WHATSAPP_LOGO = '/assets/whatsapp-logo.png';
const MAPS_LOGO = '/assets/maps-logo.png';

// Source filter options
const SOURCE_OPTIONS = [
  { value: 'all', label: 'Todas as Fontes' },
  { value: 'mastermaq', label: 'Mastermaq' },
  { value: 'telecontrol', label: 'Telecontrol (Todos)' },
  { value: 'telecontrol_hisense', label: 'Hisense' },
  { value: 'telecontrol_hq', label: 'HQ' },
  { value: 'invisacook', label: 'Invisacook' }
];

// Brand configuration with logo paths
const BRAND_LIST = [
  { value: 'HQ', label: 'HQ', logo: '/assets/hq-logo.png' },
  { value: 'Invisacook', label: 'Invisacook', logo: '/assets/invisacook-logo.webp' },
  { value: 'Brastemp', label: 'Brastemp', logo: '/assets/brastemp-logo.png' },
  { value: 'Panasonic', label: 'Panasonic', logo: '/assets/panasonic-logo.png' },
  { value: 'Electrolux', label: 'Electrolux', logo: '/assets/electrolux-logo.png', aliases: ['eletrolux'] },
  { value: 'Samsung', label: 'Samsung', logo: '/assets/samsung-logo.png', aliases: ['samsumg'] },
  { value: 'Hisense', label: 'Hisense', logo: '/assets/hisense-logo.png' },
  { value: 'Viking', label: 'Viking', logo: '/assets/viking-logo.png' },
  { value: 'Franke', label: 'Franke', logo: '/assets/franke-logo.png' },
  { value: 'Consul', label: 'Consul', logo: '/assets/consul-logo.png' },
  { value: 'Gorenje', label: 'Gorenje', logo: '/assets/gorenje-logo.png' },
  { value: 'Liebherr', label: 'Liebherr', logo: '/assets/liebherr-logo.png' },
  { value: 'Tecno', label: 'Tecno', logo: '/assets/tecno-logo.png' },
  { value: 'Lofra', label: 'Lofra', logo: '/assets/lofra-logo.png' },
  { value: 'Bertazzoni', label: 'Bertazzoni', logo: '/assets/bertazzoni-logo.png' },
];

const getBrandLogo = (brandName) => {
  if (!brandName) return null;
  const key = brandName.trim().toLowerCase();
  const found = BRAND_LIST.find(b =>
    b.value.toLowerCase() === key || b.aliases?.some(a => a === key)
  );
  return found ? found.logo : null;
};

const BrandLogo = ({ brand, size = 'sm' }) => {
  const logo = getBrandLogo(brand);
  if (!logo) return null;
  const sizeClass = size === 'sm' ? 'h-6 max-w-[48px]' : 'h-8 max-w-[64px]';
  return (
    <img
      src={logo}
      alt={brand}
      className={`${sizeClass} object-contain flex-shrink-0`}
      data-testid={`brand-logo-${brand}`}
      onError={(e) => { e.target.style.display = 'none'; }}
    />
  );
};

const OS_STATUSES = [
  "Aguardando Peças",
  "Aguardando Conserto",
  "Aguardando Retirada",
  "Finalizada",
  "Aguard. Abastecimento Estoque",
  "Em transito",
  "Em auditoria",
  "Aguardando Analise A.T",
  "Aberta Call-Center",
  "Aguardando Confirmação Cliente",
  "Aguardando Produto",
  "OS Cancelada",
  "Aguardando Pagamento",
  "Visita Realizada"
];

const STATUS_COLORS = {
  "Visita Realizada": { bg: "#CCFBF1", text: "#0F766E" },
  "Aguardando Pagamento": { bg: "#FFF7ED", text: "#C2410C" },
  "Aguardando Peças": { bg: "#FEF3C7", text: "#92400E" },
  "Aguardando Conserto": { bg: "#F3E8FF", text: "#7C3AED" },
  "Aguardando Retirada": { bg: "#EDE9FE", text: "#6D28D9" },
  "Finalizada": { bg: "#D1FAE5", text: "#065F46" },
  "Aguard. Abastecimento Estoque": { bg: "#DBEAFE", text: "#1E40AF" },
  "Em transito": { bg: "#F3F4F6", text: "#4B5563" },
  "Em auditoria": { bg: "#FEE2E2", text: "#991B1B" },
  "Aguardando Analise A.T": { bg: "#FECACA", text: "#B91C1C" },
  "Aberta Call-Center": { bg: "#F9FAFB", text: "#6B7280" },
  "Aguardando Confirmação Cliente": { bg: "#E0F2FE", text: "#0369A1" },
  "Aguardando Produto": { bg: "#FFEDD5", text: "#C2410C" },
  "OS Cancelada": { bg: "#FEE2E2", text: "#7F1D1D" },
  "AGUARDANDO ANÁLISE": { bg: "#FEF3C7", text: "#92400E" },
  "Acordo": { bg: "#D1FAE5", text: "#065F46" },
  "F/Up com posto - conclusão OS": { bg: "#DBEAFE", text: "#1E40AF" },
  "F/Up com posto - data de visita de avaliação": { bg: "#E0F2FE", text: "#0369A1" },
  "F/Up com cliente - avaliar o produto": { bg: "#FEF3C7", text: "#92400E" },
  "F/Up com Sup. Técnico Hisense": { bg: "#F3E8FF", text: "#7C3AED" },
};

const SERVICE_TYPES = [
  "Garantia",
  "Fora de Garantia",
  "Orçamento"
];

const GARANTIA_SUBTYPES = [
  "Garantia Loja",
  "Garantia Hisense",
  "Garantia HQ",
  "Garantia Franke",
  "Garantia IGS",
  "Garantia Invisacook",
  "Garantia Elettromec"
];

const ORCAMENTO_STATUS = ["Execução", "Aguardando"];
const ORCAMENTO_CONCLUSAO = ["Pgto Feito", "Pgto Não Feito", "Pendente", "Finalizado", "Perca de Garantia Loja/Finalizada"];

// Normalizes display of service_type so older records saved as "orcamento", "ORCAMENTO",
// "instalação", etc. always render with the correct canonical label.
export const normalizeServiceType = (v) => {
  if (!v) return '';
  const t = String(v).trim();
  const lc = t.toLowerCase();
  if (lc === 'orcamento' || lc === 'orçamento') return 'Orçamento';
  if (lc === 'instalação' || lc === 'instalacao') return 'Orçamento';
  if (lc === 'cortesia') return 'Cortesia'; // legacy, still rendered correctly
  if (lc === 'fora de garantia') return 'Fora de Garantia';
  if (lc === 'garantia') return 'Garantia';
  if (lc === 'garantia loja') return 'Garantia Loja';
  if (lc === 'garantia hisense') return 'Garantia Hisense';
  if (lc === 'garantia hq') return 'Garantia HQ';
  if (lc === 'garantia franke') return 'Garantia Franke';
  // Fallback: capitalize first letter of each word
  return t.split(/\s+/).map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
};

const ServiceOrdersPage = () => {
  const { getAuthHeader, isInvisacook } = useAuth();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState('history');
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [laudoModalOpen, setLaudoModalOpen] = useState(false);
  const [laudoOrder, setLaudoOrder] = useState(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [availableStatuses, setAvailableStatuses] = useState([]);
  const [showGarantiaPopup, setShowGarantiaPopup] = useState(false);
  const [showOrcamentoPopup, setShowOrcamentoPopup] = useState(false);
  const [showOrcamentoConclusaoPopup, setShowOrcamentoConclusaoPopup] = useState(false);
    // Guia "OSs Atrasadas"
  const [overdueOrders, setOverdueOrders] = useState([]);
  const [overdueCount, setOverdueCount] = useState(0);
  const [overdueLoading, setOverdueLoading] = useState(false);
  const [overdueSearch, setOverdueSearch] = useState('');
  const [overdueStatusFilter, setOverdueStatusFilter] = useState('all');

  
  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState([]);
  // Invisacook role always sees only Invisacook OSs — the backend also
  // enforces this, but we set it here so the UI reflects the filter state.
  const [sourceFilter, setSourceFilter] = useState(() => isInvisacook ? ['invisacook'] : []);
  const [brandFilter, setBrandFilter] = useState([]);
  const [priorityFilter, setPriorityFilter] = useState(false);
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [showFilters, setShowFilters] = useState(false);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [totalItems, setTotalItems] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  // Search refs
  const searchTimerRef = useRef(null);
  const isComposingRef = useRef(false);
  const searchInputRef = useRef(null);
  const abortControllerRef = useRef(null);
  const activeSearchRef = useRef(''); // tracks the current active search term

  // Form state
  const [formData, setFormData] = useState({
    os_number: '',
    customer_name: '',
    registration_date: format(new Date(), 'yyyy-MM-dd'),
    attendance_date: '',
    cep: '',
    address: '',
    number: '',
    neighborhood: '',
    city: '',
    state: '',
    complement: '',
    phone1: '',
    phone2: '',
    landline: '',
    email: '',
    visit_fee: '',
    reference_point: '',
    service_type: '',
    product: '',
    brand: '',
    model: '',
    serial_number: '',
    batch: '',
    reported_defect: '',
    observations: '',
    status: 'Aguardando Analise A.T',
  });
  const [formLoading, setFormLoading] = useState(false);
  const [cepLoading, setCepLoading] = useState(false);

  // Client search for auto-fill
  const [clientResults, setClientResults] = useState([]);
  const [showClientResults, setShowClientResults] = useState(false);
  const clientSearchTimer = useRef(null);
  const clientSearchRef = useRef(null);

  const searchClients = (query) => {
    if (clientSearchTimer.current) clearTimeout(clientSearchTimer.current);
    if (!query || query.length < 2) { setClientResults([]); setShowClientResults(false); return; }
    clientSearchTimer.current = setTimeout(async () => {
      try {
        const res = await axios.get(`${API}/service-orders/search-clients?q=${encodeURIComponent(query)}`, getAuthHeader());
        setClientResults(res.data.clients || []);
        setShowClientResults(true);
      } catch { setClientResults([]); }
    }, 300);
  };

  const linkClient = (client) => {
    setFormData(prev => ({
      ...prev,
      customer_name: client.customer_name || prev.customer_name,
      phone1: client.phone1 || prev.phone1,
      phone2: client.phone2 || prev.phone2,
      landline: client.landline || prev.landline,
      email: client.email || prev.email,
      address: client.address || prev.address,
      number: client.number || prev.number,
      complement: client.complement || prev.complement,
      neighborhood: client.neighborhood || prev.neighborhood,
      city: client.city || prev.city,
      state: client.state || prev.state,
      cep: client.cep || prev.cep,
      reference_point: client.reference_point || prev.reference_point,
    }));
    setShowClientResults(false);
    toast.success('Cliente vinculado!');
  };

  // Close client dropdown on click outside
  useEffect(() => {
    const handleClick = (e) => {
      if (clientSearchRef.current && !clientSearchRef.current.contains(e.target)) {
        setShowClientResults(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  // Fetch available statuses from database
  const fetchStatuses = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/service-orders/statuses`, getAuthHeader());
      setAvailableStatuses((response.data.statuses || []).filter(s => s !== 'Orçamento' && s.toUpperCase() !== 'AGUARDANDO ANÁLISE'));
    } catch (error) {
      console.error('Error fetching statuses:', error);
    } 
  }, [getAuthHeader]);

  // Track latest fetch ID to prevent stale results
  const fetchIdRef = useRef(0);
  
const fetchOrders = useCallback(async () => {
  const myFetchId = ++fetchIdRef.current;

  try {
    const params = new URLSearchParams();
    if (statusFilter.length > 0) params.append('status', statusFilter.join(','));
    if (sourceFilter.length > 0) params.append('source', sourceFilter.join(','));
    if (brandFilter.length > 0) params.append('brand', brandFilter.join(','));
    if (startDate) params.append('start_date', format(startDate, 'yyyy-MM-dd'));
    if (endDate) params.append('end_date', format(endDate, 'yyyy-MM-dd'));
    if (activeSearchRef.current) params.append('search', activeSearchRef.current);
    if (priorityFilter) params.append('priority', 'true');
    params.append('page', currentPage);
    params.append('limit', itemsPerPage);
    params.append('order_by', 'created_at');  // ← ADICIONAR
    params.append('sort', 'desc');             // ← ADICIONAR

      const authHeaders = getAuthHeader();
      const response = await axios.get(`${API}/service-orders?${params.toString()}`, {
        headers: authHeaders.headers,
      });
      
      // Only update state if this is still the latest fetch
      if (myFetchId === fetchIdRef.current) {
        setOrders(response.data.orders || []);
        setTotalItems(response.data.total || 0);
        setTotalPages(response.data.total_pages || 0);
        setLoading(false);
      }
    } catch (error) {
      if (myFetchId === fetchIdRef.current) {
        toast.error('Erro ao carregar ordens de serviço');
        setLoading(false);
      }
    }
  }, [getAuthHeader, statusFilter, sourceFilter, brandFilter, startDate, endDate, currentPage, itemsPerPage, priorityFilter]);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/notifications/unread-count`, getAuthHeader());
      setUnreadCount(response.data.count);
    } catch (error) {
      console.error('Error fetching unread count:', error);
    }
  }, [getAuthHeader]);

  // O backend já devolve só os 3 status em aberto com mais de 10 dias.
  // Ao mudar o status (ex.: Finalizada) a OS some daqui automaticamente
  // e continua aparecendo apenas no "Histórico de OSs".
  const fetchOverdue = useCallback(async () => {
    setOverdueLoading(true);
    try {
      const response = await axios.get(`${API}/service-orders/overdue-at`, getAuthHeader());
      setOverdueOrders(response.data.orders || []);
      setOverdueCount(response.data.count || 0);
    } catch (error) {
      console.error('Error fetching overdue orders:', error);
      setOverdueOrders([]);
      setOverdueCount(0);
    } finally {
      setOverdueLoading(false);
    }
  }, [getAuthHeader]);

  useEffect(() => {
    fetchStatuses();
    fetchOrders();
    fetchUnreadCount();
    fetchOverdue();
  }, [fetchOrders, fetchUnreadCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch when tab becomes visible (mobile back-to-foreground) so users
  // never see stale data after switching apps.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') fetchOrders();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [fetchOrders]);

  // Debounce search: update ref and trigger fetch after 300ms
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      if (activeSearchRef.current !== searchTerm) {
        activeSearchRef.current = searchTerm;
        setCurrentPage(1);
        fetchOrders();
      }
    }, 300);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [searchTerm, fetchOrders]);

  // Auto-open OS from URL query param (?os=XXXXX or ?open=XXXXX — both are accepted
  // for backward-compat; the QR-code sticker route /os/:osNumber redirects here with ?open=)
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const osNum = params.get('os') || params.get('open');
    if (osNum) {
      axios.get(`${API}/service-orders/${encodeURIComponent(osNum)}?include_photos=1`, getAuthHeader())
        .then(res => {
          if (res.data) {
            setSelectedOrder(res.data);
            setModalOpen(true);
            window.history.replaceState({}, '', window.location.pathname);
          }
        })
        .catch(() => toast.error(`OS ${osNum} não encontrada`));
    }
  }, [location.search]);

  // Fetch next OSE number when switching to create tab
  useEffect(() => {
    if (activeTab === 'create' && !formData.os_number) {
      fetchNextOseNumber();
    }
    if (activeTab === 'overdue') {
      fetchOverdue();
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCEPLookup = async (cep) => {
    if (cep.length < 8) return;
    const cleanCep = cep.replace(/\D/g, '');
    if (cleanCep.length !== 8) return;

    setCepLoading(true);
    try {
      const response = await axios.get(`${API}/cep/${cleanCep}`, getAuthHeader());
      setFormData(prev => ({
        ...prev,
        address: response.data.logradouro,
        neighborhood: response.data.bairro,
        city: response.data.localidade,
        state: response.data.uf
      }));
      toast.success('Endereço encontrado!');
    } catch (error) {
      toast.error('CEP não encontrado');
    } finally {
      setCepLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validation
    const required = ['os_number', 'customer_name', 'registration_date', 'cep', 'address', 'number', 'neighborhood', 'city', 'state', 'phone1', 'product', 'brand', 'model', 'reported_defect'];
    const missing = required.filter(field => !formData[field]);
    
    if (missing.length > 0) {
      toast.error('Preencha todos os campos obrigatórios');
      return;
    }

    setFormLoading(true);
    try {
      const data = {
        ...formData,
        visit_fee: formData.visit_fee ? parseFloat(formData.visit_fee) : null
      };
      
      await axios.post(`${API}/service-orders`, data, getAuthHeader());
      toast.success('Ordem de Serviço cadastrada com sucesso!');
      setFormData({
        os_number: '',
        customer_name: '',
        registration_date: format(new Date(), 'yyyy-MM-dd'),
        attendance_date: '',
        cep: '',
        address: '',
        number: '',
        neighborhood: '',
        city: '',
        state: '',
        complement: '',
        phone1: '',
        phone2: '',
        landline: '',
        email: '',
        visit_fee: '',
        reference_point: '',
        service_type: '',
        product: '',
        brand: '',
        model: '',
        reported_defect: '',
        observations: '',
        status: 'Aguardando Analise A.T',
      });
      setActiveTab('history');
      fetchOrders();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao cadastrar OS');
    } finally {
      setFormLoading(false);
    }
  };

  const [syncDays, setSyncDays] = useState(30);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await axios.post(`${API}/telecontrol/sync?days=${syncDays}`, {}, getAuthHeader());
      toast.success(`Sincronização iniciada (últimos ${syncDays} dias)`);
      setTimeout(() => {
        fetchOrders();
        setSyncing(false);
      }, 2000);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao sincronizar');
      setSyncing(false);
    }
  };

  const handleOrderClick = async (order) => {
    // Open immediately with cached snapshot so UI is responsive…
    setSelectedOrder(order);
    setModalOpen(true);
    // …then refresh from backend so any field updated elsewhere (incl. via
    // LaudoModal, webhook, scraper, another session) is visible. This is the
    // single source of truth: always trust the backend on modal open.
    try {
      const res = await axios.get(`${API}/service-orders/${encodeURIComponent(order.os_number)}?include_photos=1`, getAuthHeader());
      if (res?.data) {
        setSelectedOrder(res.data);
        setOrders((prev) => prev.map((o) => (o.os_number === order.os_number ? { ...o, ...res.data } : o)));
      }
    } catch (_) { /* keep cached snapshot if refresh fails */ }
  };

  const handleOpenLaudo = async (order) => {
    setLaudoOrder(order);
    setLaudoModalOpen(true);
    // Same fresh-on-open semantics as OrderDetailModal.
    try {
      const res = await axios.get(`${API}/service-orders/${encodeURIComponent(order.os_number)}?include_photos=1`, getAuthHeader());
      if (res?.data) {
        setLaudoOrder(res.data);
        setSelectedOrder((prev) => (prev && prev.os_number === order.os_number ? res.data : prev));
        setOrders((prev) => prev.map((o) => (o.os_number === order.os_number ? { ...o, ...res.data } : o)));
      }
    } catch (_) {}
  };

  // Single mutation reducer used by BOTH modals' callbacks. Whenever a modal
  // persists fields, it calls this to mirror the change into the parent's
  // state — keeping list, selectedOrder and laudoOrder always in sync.
  const applyOrderUpdates = (osNumber, patch) => {
    if (!osNumber || !patch) return;
    setSelectedOrder((prev) => (prev && prev.os_number === osNumber ? { ...prev, ...patch } : prev));
    setLaudoOrder((prev) => (prev && prev.os_number === osNumber ? { ...prev, ...patch } : prev));
    setOrders((prev) => prev.map((o) => (o.os_number === osNumber ? { ...o, ...patch } : o)));
  };

  const handleUpdateOrder = async (updatedData) => {
    try {
      await axios.put(`${API}/service-orders/${encodeURIComponent(selectedOrder.os_number)}`, updatedData, getAuthHeader());
      toast.success('OS atualizada com sucesso!');
      fetchOrders();
      fetchOverdue();
      fetchUnreadCount();
      setModalOpen(false);
    } catch (error) {
      toast.error('Erro ao atualizar OS');
    }
  };

  const openWhatsApp = (phone) => {
    const cleanPhone = phone.replace(/\D/g, '');
    const fullPhone = cleanPhone.length === 11 ? `55${cleanPhone}` : `5511${cleanPhone}`;
    window.open(`https://wa.me/${fullPhone}`, '_blank');
  };

  const openMaps = (order) => {
  const parts = [
    `${order.address || ''} ${order.number || ''}`.trim(),
    order.neighborhood,
    order.city,
    order.state,
    order.cep
  ].filter(Boolean);

  const address = parts.join(', ');

  window.open(
    `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(address)}`,
    '_blank'
  );
};

  const openTelecontrol = (osNumber) => {
    window.open(`https://posvenda.telecontrol.com.br/assist/os_press.php?os=${osNumber}`, '_blank');
  };

  const clearFilters = () => {
    setSearchTerm('');
    activeSearchRef.current = '';
    setStatusFilter([]);
    setSourceFilter([]);
    setBrandFilter([]);
    setPriorityFilter(false);
    setStartDate(null);
    setEndDate(null);
    setCurrentPage(1);
  };

  // Fetch next OSE number for manual orders.
  // Invisacook users use their OWN independent sequence (INV-#####) so there
  // is no chance of numbering collision with Mastermaq's 5-digit OSE numbers.
  const fetchNextOseNumber = async () => {
    try {
      if (isInvisacook) {
        const response = await axios.get(`${API}/service-orders/next-invisacook-number`, getAuthHeader());
        setFormData(prev => ({ ...prev, os_number: response.data.next_invisacook_number, source: 'invisacook' }));
      } else {
        const response = await axios.get(`${API}/service-orders/next-ose-number`, getAuthHeader());
        setFormData(prev => ({ ...prev, os_number: response.data.next_ose_number }));
      }
    } catch (error) {
      console.error('Error fetching next OS number:', error);
    }
  };

  // Shared: Generate single copy HTML for print/PDF (delegated to utility)
  const buildCopyHtml = buildCopyHtmlUtil;

  // Print OS function - A5 size copies (half of A4)
  const printOS = printOSUtil;

  // Send single copy to client via WhatsApp as PDF
  const sendWhatsAppCopy = async (order, sigData = null) => {
    await sendWhatsAppCopyUtil(order, sigData, toast);
  };

  // ─── Status Quick Action ─────────────────────────────────────────
  // Substitui o badge estático por um select-dropdown clicável + 2 botões
  // (Finalizar / Cancelar) que mudam o status inline SEM abrir o modal.
  // Persiste via PUT /service-orders/{os_number} (o backend faz merge dos
  // campos e não sobrescreve o resto), propaga pra lista via
  // applyOrderUpdates e refaz o count da guia de OSs atrasadas.
  const StatusQuickAction = ({ order }) => {
    const [saving, setSaving] = useState(false);
    const colors = STATUS_COLORS[order.status] || { bg: '#F3F4F6', text: '#4B5563' };

    const patch = async (newStatus) => {
      if (saving || newStatus === order.status) return;
      // Guarda contra os_number ausente — sem isso, a URL vira
      // `/service-orders/` e o servidor devolve 405 (Method Not Allowed).
      if (!order?.os_number) {
        console.warn('StatusQuickAction: os_number ausente', order);
        toast.error('OS sem número — não é possível alterar status');
        return;
      }
      setSaving(true);
      try {
        // Envia APENAS o campo `status` (payload mínimo). O backend faz merge
        // com o documento existente — evita reenviar campos stale (fotos, etc).
        const resp = await axios.put(
          `${API}/service-orders/${encodeURIComponent(order.os_number)}`,
          { status: newStatus },
          getAuthHeader()
        );
        applyOrderUpdates(order.os_number, resp.data || { status: newStatus });
        fetchOverdue();
        toast.success(`OS #${order.os_number}: ${newStatus}`);
      } catch (e) {
        toast.error('Erro ao mudar status: ' + (e?.response?.data?.detail || e.message));
      } finally {
        setSaving(false);
      }
    };

    return (
      <div className="flex items-center gap-1 flex-wrap" onClick={(e) => e.stopPropagation()}>
        <Select value={order.status || ''} onValueChange={patch} disabled={saving}>
          <SelectTrigger
            className="h-6 text-[11px] font-semibold rounded-full px-2.5 py-0 border w-auto min-w-[130px] focus:ring-2 focus:ring-offset-1"
            style={{ backgroundColor: colors.bg, color: colors.text, borderColor: colors.text + '33' }}
            data-testid={`card-status-select-${order.os_number}`}
            title="Clique para mudar o status"
          >
            <SelectValue placeholder="Selecionar status" />
          </SelectTrigger>
          {/* Content é BRANCO com texto PRETO — design clean/limpo (a cor do
              status só aparece no trigger, quando um valor está selecionado). */}
          <SelectContent className="bg-white text-gray-900">
            {OS_STATUSES.map(s => (
              <SelectItem key={s} value={s} className="text-gray-900 text-xs">
                {s}
              </SelectItem>
            ))}
            {!OS_STATUSES.includes(order.status) && order.status && (
              <SelectItem value={order.status} className="text-gray-900 text-xs">
                {order.status}
              </SelectItem>
            )}
          </SelectContent>
        </Select>
        <button
          type="button"
          onClick={() => patch('Finalizada')}
          disabled={saving || order.status === 'Finalizada'}
          className="text-[10px] px-2 py-0.5 rounded border border-gray-300 text-gray-600 bg-white hover:bg-emerald-100 hover:border-emerald-500 hover:text-emerald-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          data-testid={`card-finalize-${order.os_number}`}
          title="Finalizar Ordem"
        >
          Finalizar
        </button>
        <button
          type="button"
          onClick={() => patch('OS Cancelada')}
          disabled={saving || order.status === 'OS Cancelada'}
          className="text-[10px] px-2 py-0.5 rounded border border-gray-300 text-gray-600 bg-white hover:bg-red-100 hover:border-red-500 hover:text-red-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          data-testid={`card-cancel-${order.os_number}`}
          title="Cancelar Ordem"
        >
          Cancelar
        </button>
      </div>
    );
  };

  const getStatusBadge = (status) => {
    const colors = STATUS_COLORS[status] || { bg: '#F3F4F6', text: '#4B5563' };
    return (
      <span 
        className="status-badge"
        style={{ backgroundColor: colors.bg, color: colors.text }}
      >
        {status}
      </span>
    );
  };

  return (
    <DashboardLayout unreadCount={unreadCount}>
      <div className="space-y-6" data-testid="service-orders-page">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
            <TabsList className="bg-gray-100 w-full sm:w-auto justify-start overflow-x-auto overflow-y-hidden" data-testid="os-tabs-list">
              <TabsTrigger value="history" className="shrink-0" data-testid="tab-history">
                Histórico de OSs {totalItems > 0 && <span className="ml-1.5 bg-blue-100 text-blue-700 text-xs px-1.5 py-0.5 rounded-full font-medium">{totalItems}</span>}
              </TabsTrigger>
              <TabsTrigger value="overdue" data-testid="tab-overdue">
                <AlertTriangle size={16} className="mr-1 text-red-600" />
                OSs Atrasadas
                {overdueCount > 0 && (
                  <span className="ml-1.5 bg-red-100 text-red-700 text-xs px-1.5 py-0.5 rounded-full font-medium">
                    {overdueCount}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="create" data-testid="tab-create">
                <Plus size={16} className="mr-1" />
                Cadastrar OS
              </TabsTrigger>
            </TabsList>
            
            {activeTab === 'history' && (
              <div className="flex items-center gap-2 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap" data-testid="sync-area">
                  <select 
                    value={syncDays} 
                    onChange={e => setSyncDays(Number(e.target.value))}
                    className="border rounded-md px-2 py-1.5 text-sm bg-white"
                    disabled={syncing}
                    data-testid="sync-days-select"
                  >
                    <option value={30}>30 dias</option>
                    <option value={60}>60 dias</option>
                    <option value={90}>90 dias</option>
                    <option value={180}>6 meses</option>
                    <option value={365}>1 ano</option>
                  </select>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        className="border-gray-300"
                        title="Imprimir adesivo da loja (50×30mm) — escolha a quantidade"
                        data-testid="print-store-label-button"
                      >
                        <Tags size={16} className="mr-2" />
                        Imprimir Adesivo
                        <ChevronDown size={14} className="ml-1" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                      <div className="px-2 py-1.5 text-xs text-gray-500 font-medium">Quantidade</div>
                      {[1, 5, 10, 20, 50, 100].map(n => (
                        <DropdownMenuItem
                          key={n}
                          onClick={() => printStoreLabel({ size: '50x30', copies: n })}
                          data-testid={`print-store-${n}`}
                        >
                          {n} {n === 1 ? 'adesivo' : 'adesivos'}
                        </DropdownMenuItem>
                      ))}
                      <DropdownMenuItem
                        onClick={() => {
                          const n = parseInt(window.prompt('Quantidade personalizada (1-500):', '10'), 10);
                          if (n && n > 0 && n <= 500) printStoreLabel({ size: '50x30', copies: n });
                        }}
                      >
                        Personalizado…
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleSync}
                    disabled={syncing}
                    className={`border-gray-300 ${isInvisacook ? 'hidden' : ''}`}
                    data-testid="sync-button"
                  >
                    <RefreshCw size={16} className={`mr-2 ${syncing ? 'animate-spin' : ''}`} />
                    Sincronizar
                  </Button>
                </div>
              </div>
            )}
          </div>

          <TabsContent value="history" className="mt-0">
            {/* Source filter chips - circular buttons with logos.
                Hidden for Invisacook role since they only see one source. */}
            {!isInvisacook && (
            <div className="flex flex-wrap items-center gap-2 mb-4 px-1" data-testid="source-filter-chips">
              {[
                { value: 'external_site', label: 'OS Site', logo: '/assets/mi-ia.webp', big: true },
                { value: 'mastermaq', label: 'Mastermaq', logo: '/assets/mastermaq-logo.png', },
                { value: 'telecontrol', label: 'Telecontrol (todas)', logo: '/assets/telecontrol-logo.png', },
                { value: 'telecontrol_hisense', label: 'Hisense', logo: '/assets/hisense-logo.png', },
                { value: 'telecontrol_hq', label: 'HQ', logo: '/assets/hq-logo.png', },
                { value: 'invisacook', label: 'Invisacook', logo: '/assets/invisacook-logo.webp', big: true },
              ].map(opt => {
                const active = sourceFilter.includes(opt.value);
                const sizePx = opt.big ? 'h-12 w-12' : 'h-9 w-9';
                const imgSize = opt.big ? 'h-12 w-12 object-cover rounded-full' : 'h-7 w-7 object-contain';
                return (
                  <button
                    key={opt.value}
                    type="button"
                    title={opt.label}
                    aria-label={`Filtrar por ${opt.label}`}
                    onClick={() => {
                      setSourceFilter(prev => prev.includes(opt.value) ? prev.filter(x => x !== opt.value) : [...prev, opt.value]);
                      setCurrentPage(1);
                    }}
                    className={`relative ${sizePx} rounded-full bg-white flex items-center justify-center overflow-hidden transition-all duration-200 ${active ? 'scale-110 shadow-lg shadow-gray-400/30' : 'shadow-sm hover:scale-105 hover:shadow-md'}`}
                    data-testid={`source-chip-${opt.value}`}
                  >
                    <img
                      src={opt.logo}
                      alt={opt.label}
                      className={imgSize}
                      onError={(e) => { e.target.style.display = 'none'; }}
                    />
                    {active && (
                      <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-green-500 border-2 border-white" />
                    )}
                  </button>
                );
              })}
              {sourceFilter.length > 0 && (
                <button
                  type="button"
                  onClick={() => { setSourceFilter([]); setCurrentPage(1); }}
                  className="ml-1 text-xs text-gray-500 hover:text-red-600 underline"
                  data-testid="source-chip-clear"
                >
                  Limpar
                </button>
              )}
            </div>
            )}

            {/* Filters */}
            <Card className="mb-6 border-gray-200">
              <CardContent className="pt-6">
                <div className="flex flex-col lg:flex-row gap-4">
                  <div className="flex-1">
                    <div className="relative">
                      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                      <Input
                        ref={searchInputRef}
                        type="search"
                        inputMode="search"
                        autoComplete="off"
                        autoCorrect="off"
                        spellCheck={false}
                        placeholder="Buscar por OS, cliente, produto, endereço..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        onInput={(e) => setSearchTerm(e.target.value)}
                        onCompositionEnd={(e) => setSearchTerm(e.target.value)}
                        className="pl-9 border-gray-300"
                        data-testid="search-input"
                      />
                    </div>
                  </div>
                  
                  <div className="flex flex-wrap gap-2">
                    {/* Multi-select Status Filter */}
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button variant="outline" className="w-full sm:w-48 border-gray-300 justify-between" data-testid="status-filter">
                          <span className="truncate text-sm">
                            {statusFilter.length === 0 ? 'Todos os Status' : `${statusFilter.length} status`}
                          </span>
                          <ChevronDown size={14} className="ml-1 shrink-0 opacity-50" />
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-64 p-2 max-h-60 overflow-y-auto" align="start">
                        {/* Merge canonical OS_STATUSES with statuses fetched
                            from the server so that stable options like
                            "OS Cancelada" are ALWAYS available even when no
                            OS currently has that status in the database. */}
                        {(() => {
                          const merged = [];
                          const seen = new Set();
                          for (const s of [...OS_STATUSES, ...availableStatuses]) {
                            if (s && !seen.has(s)) { seen.add(s); merged.push(s); }
                          }
                          return merged;
                        })().map(s => (
                          <div
                            key={s}
                            onClick={() => { setStatusFilter(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]); setCurrentPage(1); }}
                            className="flex items-center gap-2 px-2 py-1.5 hover:bg-gray-50 rounded cursor-pointer text-sm"
                          >
                            <div className={`h-4 w-4 border rounded flex items-center justify-center shrink-0 ${statusFilter.includes(s) ? 'bg-blue-600 border-blue-600' : 'border-gray-300'}`}>
                              {statusFilter.includes(s) && <Check size={12} className="text-white" />}
                            </div>
                            {s}
                          </div>
                        ))}
                      </PopoverContent>
                    </Popover>

                    <Popover>
                      <PopoverTrigger asChild>
                        <Button variant="outline" className="border-gray-300" data-testid="date-filter-start">
                          <CalendarIcon size={16} className="mr-2" />
                          {startDate ? format(startDate, 'dd/MM/yyyy', { locale: ptBR }) : 'Data Inicial'}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0">
                        <Calendar
                          mode="single"
                          selected={startDate}
                          onSelect={setStartDate}
                          locale={ptBR}
                        />
                      </PopoverContent>
                    </Popover>

                    <Popover>
                      <PopoverTrigger asChild>
                        <Button variant="outline" className="border-gray-300" data-testid="date-filter-end">
                          <CalendarIcon size={16} className="mr-2" />
                          {endDate ? format(endDate, 'dd/MM/yyyy', { locale: ptBR }) : 'Data Final'}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0">
                        <Calendar
                          mode="single"
                          selected={endDate}
                          onSelect={setEndDate}
                          locale={ptBR}
                        />
                      </PopoverContent>
                    </Popover>

                    {/* Multi-select Brand Filter — hidden for Invisacook role */}
                    {!isInvisacook && (
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button variant="outline" className="w-full sm:w-[180px] border-gray-300 justify-between" data-testid="brand-filter">
                          <span className="truncate text-sm">
                            {brandFilter.length === 0 ? 'Todas as Marcas' : `${brandFilter.length} marca(s)`}
                          </span>
                          <ChevronDown size={14} className="ml-1 shrink-0 opacity-50" />
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-56 p-2 max-h-60 overflow-y-auto" align="start">
                        {BRAND_LIST.map(b => (
                          <div key={b.value} onClick={() => {
                            setBrandFilter(prev => prev.includes(b.value) ? prev.filter(x => x !== b.value) : [...prev, b.value]);
                            setCurrentPage(1);
                          }} className="flex items-center gap-2 px-2 py-1.5 hover:bg-gray-50 rounded cursor-pointer text-sm">
                            <div className={`h-4 w-4 border rounded flex items-center justify-center ${brandFilter.includes(b.value) ? 'bg-blue-600 border-blue-600' : 'border-gray-300'}`}>
                              {brandFilter.includes(b.value) && <Check size={12} className="text-white" />}
                            </div>
                            <img src={b.logo} alt="" className="h-4 w-auto max-w-[32px] object-contain" onError={(e) => { e.target.style.display = 'none'; }} />
                            {b.label}
                          </div>
                        ))}
                      </PopoverContent>
                    </Popover>
                    )}

                    {/* Priority Filter */}
                    <Button
                      variant={priorityFilter ? "default" : "outline"}
                      className={`w-auto border-gray-300 ${priorityFilter ? 'bg-red-600 hover:bg-red-700 text-white border-red-600' : ''}`}
                      onClick={() => { setPriorityFilter(p => !p); setCurrentPage(1); }}
                      data-testid="priority-filter"
                    >
                      <AlertTriangle size={14} className="mr-1" />
                      Prioridade
                    </Button>

                    {(searchTerm || statusFilter.length > 0 || sourceFilter.length > 0 || brandFilter.length > 0 || priorityFilter || startDate || endDate) && (
                      <Button 
                        variant="ghost" 
                        size="icon"
                        onClick={clearFilters}
                        className="text-gray-500"
                        data-testid="clear-filters"
                      >
                        <X size={16} />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Orders List */}
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
              </div>
            ) : orders.length === 0 ? (
              <Card className="border-gray-200">
                <CardContent className="py-12 text-center">
                  <p className="text-gray-500">Nenhuma ordem de serviço encontrada</p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4" data-testid="orders-list">
                {orders.map((order) => (
                  <Card 
                    key={order.id} 
                    className="border-gray-200 hover:shadow-md transition-shadow cursor-pointer"
                    onClick={() => handleOrderClick(order)}
                    data-testid={`order-card-${order.os_number}`}
                  >
                    <CardContent className="p-4">
                      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-2">
                            {/* Source Logo — Telecontrol / Invisacook / Mastermaq */}
                            {(() => {
                              const isTelec = order.source === 'telecontrol_hq' || order.source === 'telecontrol_hisense' || order.source === 'telecontrol';
                              const isInvisa = order.source === 'invisacook';
                              const logoSrc = isTelec ? TELECONTROL_LOGO : (isInvisa ? '/assets/invisacook-logo.webp' : MASTERMAQ_LOGO);
                              const logoAlt = isTelec ? 'Telecontrol' : (isInvisa ? 'Invisacook' : 'Mastermaq');
                              return (
                                <img
                                  src={logoSrc}
                                  alt={logoAlt}
                                  className="h-6 w-auto object-contain flex-shrink-0"
                                  onError={(e) => { e.target.style.display = 'none'; }}
                                />
                              );
                            })()}
                            <span className="text-base sm:text-lg font-semibold text-gray-900 flex-shrink-0">
                              OS #{order.os_number}
                            </span>
                            <StatusQuickAction order={order} />
                            {order.service_type && (
                              <Badge variant="outline" className="text-xs border-purple-300 text-purple-600">
                                {normalizeServiceType(order.service_type)}
                              </Badge>
                            )}
                            {order.priority && (
                              <Badge className="text-xs bg-red-600 text-white border-red-600" data-testid={`priority-badge-${order.os_number}`}>
                                <AlertTriangle className="h-3 w-3 mr-0.5" />
                                Prioridade
                              </Badge>
                            )}
                            {!String(order.source || '').startsWith('telecontrol') && (
                              <select
                                value={order.visit_fee_paid ? 'paid' : 'unpaid'}
                                onClick={e => e.stopPropagation()}
                                onChange={async (e) => {
                                  e.stopPropagation();
                                  const paid = e.target.value === 'paid';
                                  try {
                                    await axios.put(`${API}/service-orders/${order.os_number}`, { visit_fee_paid: paid }, getAuthHeader());
                                    setOrders(prev => prev.map(o => o.os_number === order.os_number ? { ...o, visit_fee_paid: paid } : o));
                                  } catch { toast.error('Erro ao salvar taxa'); }
                                }}
                                className={`text-xs rounded-md px-1.5 py-0.5 border font-medium cursor-pointer ${order.visit_fee_paid ? 'bg-green-600 text-white border-green-600' : 'bg-white text-gray-600 border-gray-300'}`}
                                data-testid={`taxa-select-${order.os_number}`}
                              >
                                <option value="paid">Taxa Paga</option>
                                <option value="unpaid">Taxa não paga</option>
                              </select>
                            )}
                            {(order.source === 'telecontrol_hisense' || order.source === 'telecontrol') && (
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-blue-300 text-blue-600 font-medium" data-testid={`badge-hisense-${order.os_number}`}>
                                Telecontrol Hisense
                              </Badge>
                            )}
                            {order.source === 'telecontrol_hq' && (
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-orange-300 text-orange-600 font-medium" data-testid={`badge-hq-${order.os_number}`}>
                                Telecontrol HQ
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 mb-1">
                            <span className="font-medium">{order.customer_name}</span>
                          </p>
                          <p className="text-sm text-gray-500">
                            {order.product} - {order.brand} {order.model}
                          </p>
                          <p className="text-xs text-gray-400 mt-1">
                            Registrado em {order.registration_date}
                          </p>
                          {(order.status_orcamento || order.conclusao_orcamento) && (
                            <div className="flex items-center gap-2 mt-1 flex-wrap">
                              {order.status_orcamento && (
                                <span className="text-[11px] text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded" data-testid={`card-status-orc-${order.os_number}`}>
                                  Orç: {order.status_orcamento}
                                </span>
                              )}
                              {order.conclusao_orcamento && (
                                <span className="text-[11px] text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded" data-testid={`card-conclusao-orc-${order.os_number}`}>
                                  {order.conclusao_orcamento}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        
                        <div className="flex flex-col items-end gap-2" onClick={(e) => e.stopPropagation()}>
                          <BrandLogo brand={order.brand} size="sm" />
                          <div className="flex items-center gap-2 flex-wrap">
                          {order.phone1 && (
                            <button
                              onClick={() => openWhatsApp(order.phone1)}
                              className="p-1 hover:opacity-80 transition-opacity"
                              title="WhatsApp"
                              data-testid={`whatsapp-${order.os_number}`}
                            >
                              <img src={WHATSAPP_LOGO} alt="WhatsApp" className="h-7 w-7 object-contain" />
                            </button>
                          )}
                          {/* Maps with logo */}
                          <button
                            onClick={() => openMaps(order)}
                            className="p-1 hover:opacity-80 transition-opacity"
                            title="Google Maps"
                            data-testid={`maps-${order.os_number}`}
                          >
                            <img src={MAPS_LOGO} alt="Maps" className="h-7 w-7 object-contain" />
                          </button>
                          {/* Telecontrol link */}
                          {(order.source === 'telecontrol' || order.source === 'telecontrol_hisense' || order.source === 'telecontrol_hq') && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openTelecontrol(order.os_number)}
                              className="border-gray-300 text-gray-600 hover:bg-gray-50"
                              data-testid={`telecontrol-${order.os_number}`}
                            >
                              <ExternalLink size={14} className="mr-1" />
                              Telecontrol
                            </Button>
                          )}
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {/* Pagination Controls */}
            {!loading && totalItems > 0 && (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mt-6 px-1" data-testid="pagination-controls">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <span>Exibir</span>
                  <Select value={String(itemsPerPage)} onValueChange={(v) => { setItemsPerPage(Number(v)); setCurrentPage(1); }}>
                    <SelectTrigger className="w-20 h-8 border-gray-300" data-testid="items-per-page">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="10">10</SelectItem>
                      <SelectItem value="30">30</SelectItem>
                      <SelectItem value="50">50</SelectItem>
                      <SelectItem value="100">100</SelectItem>
                    </SelectContent>
                  </Select>
                  <span>por pagina</span>
                  <span className="mx-2 text-gray-400">|</span>
                  <span>{totalItems} registros</span>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(1)}
                    disabled={currentPage <= 1}
                    className="h-8 px-2 border-gray-300"
                    data-testid="pagination-first"
                  >
                    <ChevronsLeft size={14} />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage <= 1}
                    className="h-8 px-2 border-gray-300"
                    data-testid="pagination-prev"
                  >
                    <ChevronLeft size={14} />
                  </Button>
                  <span className="text-sm text-gray-600 mx-2">
                    Pagina {currentPage} de {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    className="h-8 px-2 border-gray-300"
                    data-testid="pagination-next"
                  >
                    <ChevronRight size={14} />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(totalPages)}
                    disabled={currentPage >= totalPages}
                    className="h-8 px-2 border-gray-300"
                    data-testid="pagination-last"
                  >
                    <ChevronsRight size={14} />
                  </Button>
                                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="overdue" className="mt-0">
            {/* Filtros: busca + status */}
            <div className="flex flex-col sm:flex-row gap-3 mb-4">
              <Input
                placeholder="Buscar por OS, cliente, produto…"
                value={overdueSearch}
                onChange={(e) => setOverdueSearch(e.target.value)}
                className="max-w-md border-gray-300"
                data-testid="overdue-search"
              />
              <div className="flex gap-1 flex-wrap">
                {['all', 'Aguardando Analise A.T', 'Aguardando Peças', 'Aguardando Conserto'].map(s => (
                  <Button
                    key={s}
                    size="sm"
                    variant={overdueStatusFilter === s ? 'default' : 'outline'}
                    onClick={() => setOverdueStatusFilter(s)}
                    className="text-xs"
                    data-testid={`overdue-filter-${s.replace(/\s+/g, '-')}`}
                  >
                    {s === 'all' ? 'Todos' : s}
                  </Button>
                ))}
              </div>
            </div>

            {overdueLoading ? (
              <div className="flex items-center justify-center py-12" data-testid="overdue-loading">
                <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
              </div>
            ) : (() => {
              const q = overdueSearch.trim().toLowerCase();
              const filtered = overdueOrders.filter(o => {
                if (overdueStatusFilter !== 'all' && o.status !== overdueStatusFilter) return false;
                if (!q) return true;
                return (
                  String(o.os_number || '').toLowerCase().includes(q) ||
                  String(o.customer_name || '').toLowerCase().includes(q) ||
                  String(o.product || '').toLowerCase().includes(q) ||
                  String(o.brand || '').toLowerCase().includes(q) ||
                  String(o.model || '').toLowerCase().includes(q)
                );
              });
              if (filtered.length === 0) {
                return (
                  <Card className="border-gray-200">
                    <CardContent className="py-12 text-center">
                      <AlertTriangle className="h-8 w-8 text-gray-300 mx-auto mb-2" />
                      <p className="text-gray-500">Nenhuma OS atrasada &gt; 10 dias 🎉</p>
                    </CardContent>
                  </Card>
                );
              }
              return (
                <div className="grid gap-4" data-testid="overdue-list">
                  {filtered.map((order) => (
                    <Card
                      key={order.os_number}
                      className="border-red-100 hover:shadow-md transition-shadow cursor-pointer bg-red-50/30"
                      onClick={() => handleOrderClick(order)}
                      data-testid={`overdue-card-${order.os_number}`}
                    >
                      <CardContent className="p-4">
                        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-2">
                              <span className="text-base sm:text-lg font-semibold text-gray-900">
                                OS #{order.os_number}
                              </span>
                              <StatusQuickAction order={order} />
                              <Badge className="text-xs bg-red-600 text-white border-red-600" data-testid={`overdue-days-${order.os_number}`}>
                                <AlertTriangle className="h-3 w-3 mr-0.5" />
                                {order.days_waiting} dias
                              </Badge>
                            </div>
                            <p className="text-sm text-gray-600 mb-1">
                              <span className="font-medium">{order.customer_name}</span>
                            </p>
                            <p className="text-sm text-gray-500">
                              {order.product} {order.brand ? `- ${order.brand}` : ''} {order.model || ''}
                            </p>
                            <p className="text-xs text-gray-400 mt-1">
                              {order.city && order.neighborhood ? `${order.neighborhood}, ${order.city} • ` : ''}
                              Registrado em {order.registration_date || '—'}
                            </p>
                          </div>
                          {order.phone1 && (
                            <a
                              href={`https://wa.me/55${String(order.phone1).replace(/\D/g, '')}`}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-xs text-green-700 hover:underline flex-shrink-0"
                              data-testid={`overdue-whatsapp-${order.os_number}`}
                            >
                              WhatsApp: {order.phone1}
                            </a>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              );
            })()}
          </TabsContent>

          <TabsContent value="create" className="mt-0">
            <Card className="border-gray-200">
              <CardHeader className="border-b border-gray-100">
                <h3 className="text-lg font-semibold text-gray-900" style={{ fontFamily: 'Manrope, sans-serif' }}>
                  Cadastrar Nova Ordem de Serviço
                </h3>
              </CardHeader>
              <CardContent className="pt-6">
                <form onSubmit={handleSubmit} className="space-y-6">
                  {/* OS Info */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="os_number">Nº de OSE *</Label>
                      <Input
                        id="os_number"
                        value={formData.os_number}
                        onChange={(e) => setFormData({ ...formData, os_number: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-os-number"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="registration_date">Data Registro *</Label>
                      <Input
                        id="registration_date"
                        type="date"
                        value={formData.registration_date}
                        onChange={(e) => setFormData({ ...formData, registration_date: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-registration-date"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="attendance_date">Data Atend.</Label>
                      <Input
                        id="attendance_date"
                        type="date"
                        value={formData.attendance_date}
                        onChange={(e) => setFormData({ ...formData, attendance_date: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-attendance-date"
                      />
                    </div>
                  </div>

                  {/* Customer Info */}
                  <div className="space-y-2 relative" ref={clientSearchRef}>
                    <Label htmlFor="customer_name">Nome Completo *</Label>
                    <Input
                      id="customer_name"
                      value={formData.customer_name}
                      onChange={(e) => {
                        setFormData({ ...formData, customer_name: e.target.value });
                        searchClients(e.target.value);
                      }}
                      className="border-gray-300"
                      placeholder="Digite para buscar clientes existentes..."
                      data-testid="input-customer-name"
                      autoComplete="off"
                    />
                    {showClientResults && clientResults.length > 0 && (
                      <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto" data-testid="client-search-results">
                        <div className="px-3 py-2 text-xs text-gray-500 bg-gray-50 border-b">Clientes encontrados</div>
                        {clientResults.map((client, idx) => (
                          <div
                            key={idx}
                            className="px-3 py-2 hover:bg-blue-50 cursor-pointer border-b border-gray-100 last:border-0"
                            onClick={() => linkClient(client)}
                            data-testid={`client-result-${idx}`}
                          >
                            <div className="font-medium text-sm text-gray-900">{client.customer_name}</div>
                            <div className="text-xs text-gray-500 mt-0.5">
                              {client.phone1 && <span className="mr-3">{client.phone1}</span>}
                              {client.address && <span className="mr-3">{client.address}{client.number ? `, ${client.number}` : ''}</span>}
                              {client.neighborhood && <span className="mr-3">{client.neighborhood}</span>}
                              {client.city && <span>{client.city}</span>}
                            </div>
                            <div className="text-xs text-blue-600 mt-0.5">{client.os_count} OS(s) cadastrada(s)</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Address */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="cep">CEP *</Label>
                      <div className="relative">
                        <Input
                          id="cep"
                          value={formData.cep}
                          onChange={(e) => {
                            setFormData({ ...formData, cep: e.target.value });
                            if (e.target.value.replace(/\D/g, '').length === 8) {
                              handleCEPLookup(e.target.value);
                            }
                          }}
                          placeholder="00000-000"
                          className="border-gray-300"
                          data-testid="input-cep"
                        />
                        {cepLoading && (
                          <Loader2 size={16} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-gray-400" />
                        )}
                      </div>
                    </div>
                    <div className="md:col-span-2 space-y-2">
                      <Label htmlFor="address">Endereço *</Label>
                      <Input
                        id="address"
                        value={formData.address}
                        onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-address"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="number">Número *</Label>
                      <Input
                        id="number"
                        value={formData.number}
                        onChange={(e) => setFormData({ ...formData, number: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-number"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="neighborhood">Bairro *</Label>
                      <Input
                        id="neighborhood"
                        value={formData.neighborhood}
                        onChange={(e) => setFormData({ ...formData, neighborhood: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-neighborhood"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="city">Cidade *</Label>
                      <Input
                        id="city"
                        value={formData.city}
                        onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-city"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="state">UF *</Label>
                      <Input
                        id="state"
                        value={formData.state}
                        onChange={(e) => setFormData({ ...formData, state: e.target.value })}
                        maxLength={2}
                        className="border-gray-300"
                        data-testid="input-state"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="complement">Complemento</Label>
                      <Input
                        id="complement"
                        value={formData.complement}
                        onChange={(e) => setFormData({ ...formData, complement: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-complement"
                      />
                    </div>
                  </div>

                  {/* Contact */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="phone1">Celular 1 *</Label>
                      <div className="flex gap-2">
                        <Input
                          id="phone1"
                          value={formData.phone1}
                          onChange={(e) => setFormData({ ...formData, phone1: e.target.value })}
                          placeholder="(11) 99999-9999"
                          className="border-gray-300 flex-1"
                          data-testid="input-phone1"
                        />
                        {formData.phone1 && (
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            onClick={() => openWhatsApp(formData.phone1)}
                            className="border-green-300 text-green-600 hover:bg-green-50 shrink-0"
                            data-testid="whatsapp-phone1"
                          >
                            <Phone size={16} />
                          </Button>
                        )}
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="phone2">Celular 2</Label>
                      <div className="flex gap-2">
                        <Input
                          id="phone2"
                          value={formData.phone2}
                          onChange={(e) => setFormData({ ...formData, phone2: e.target.value })}
                          placeholder="(11) 99999-9999"
                          className="border-gray-300 flex-1"
                          data-testid="input-phone2"
                        />
                        {formData.phone2 && (
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            onClick={() => openWhatsApp(formData.phone2)}
                            className="border-green-300 text-green-600 hover:bg-green-50 shrink-0"
                            data-testid="whatsapp-phone2"
                          >
                            <Phone size={16} />
                          </Button>
                        )}
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="landline">Fixo</Label>
                      <Input
                        id="landline"
                        value={formData.landline}
                        onChange={(e) => setFormData({ ...formData, landline: e.target.value })}
                        placeholder="(11) 3333-3333"
                        className="border-gray-300"
                        data-testid="input-landline"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        type="email"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-email"
                      />
                    </div>
                  </div>

                  {/* Additional Info */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="visit_fee">Taxa de Visita</Label>
                      <Input
                        id="visit_fee"
                        type="number"
                        step="0.01"
                        value={formData.visit_fee}
                        onChange={(e) => setFormData({ ...formData, visit_fee: e.target.value })}
                        placeholder="0.00"
                        className="border-gray-300"
                        data-testid="input-visit-fee"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="reference_point">Ponto de Referência</Label>
                      <Input
                        id="reference_point"
                        value={formData.reference_point}
                        onChange={(e) => setFormData({ ...formData, reference_point: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-reference-point"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="service_type">Tipo de Atendimento</Label>
                      <Select 
                        value={formData.service_type} 
                        onValueChange={(value) => {
                          if (value === 'Garantia') {
                            setFormData(prev => ({ ...prev, service_type: value }));
                            setShowGarantiaPopup(true);
                          } else if (value === 'Orçamento') {
                            setFormData(prev => ({ ...prev, service_type: value }));
                            setShowOrcamentoPopup(true);
                          } else {
                            setFormData(prev => ({ ...prev, service_type: value }));
                          }
                        }}
                      >
                        <SelectTrigger className="border-gray-300" data-testid="select-service-type">
                          <SelectValue placeholder="Selecione..." />
                        </SelectTrigger>
                        <SelectContent>
                          {SERVICE_TYPES.map(type => (
                            <SelectItem key={type} value={type}>{type}</SelectItem>
                          ))}
                          {GARANTIA_SUBTYPES.map(type => (
                            <SelectItem key={type} value={type}>{type}</SelectItem>
                          ))}
                          {formData.service_type && !SERVICE_TYPES.includes(formData.service_type) && !GARANTIA_SUBTYPES.includes(formData.service_type) && (
                            <SelectItem key={formData.service_type} value={formData.service_type}>{formData.service_type}</SelectItem>
                          )}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* Product Info */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="product">Produto *</Label>
                      <Input
                        id="product"
                        value={formData.product}
                        onChange={(e) => setFormData({ ...formData, product: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-product"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="brand">Marca *</Label>
                      <Input
                        id="brand"
                        value={formData.brand}
                        onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-brand"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="model">Modelo *</Label>
                      <Input
                        id="model"
                        value={formData.model}
                        onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                        className="border-gray-300"
                        data-testid="input-model"
                      />
                    </div>
                  </div>

                  {/* Defect */}
                  <div className="space-y-2">
                    <Label htmlFor="reported_defect">Defeito Reclamado *</Label>
                    <Textarea
                      id="reported_defect"
                      value={formData.reported_defect}
                      onChange={(e) => setFormData({ ...formData, reported_defect: e.target.value })}
                      className="border-gray-300 min-h-20"
                      data-testid="input-reported-defect"
                    />
                  </div>

                  {/* Observations */}
                  <div className="space-y-2">
                    <Label htmlFor="observations">Observações</Label>
                    <Textarea
                      id="observations"
                      value={formData.observations}
                      onChange={(e) => setFormData({ ...formData, observations: e.target.value })}
                      className="border-gray-300 min-h-20"
                      data-testid="input-observations"
                    />
                  </div>

                  {/* Status display */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label>Status</Label>
                      <div className="h-9 flex items-center px-3 border rounded text-sm bg-blue-50 text-blue-700 font-medium">
                        {formData.status || '-'}
                      </div>
                    </div>
                    {formData.service_type === 'Orçamento' && (
                      <>
                        <div className="space-y-2">
                          <Label>Status Orcamento</Label>
                          <div className="h-9 flex items-center px-3 border rounded text-sm bg-gray-50 cursor-pointer hover:bg-gray-100"
                               onClick={() => setShowOrcamentoPopup(true)} data-testid="cadastro-orcamento-status">
                            {formData.status_orcamento || '-'}
                          </div>
                        </div>
                        {formData.status_orcamento === 'Execução' && (
                          <div className="space-y-2">
                            <Label>Conclusao Orcamento</Label>
                            <div className="h-9 flex items-center px-3 border rounded text-sm bg-gray-50 cursor-pointer hover:bg-gray-100"
                                 onClick={() => setShowOrcamentoConclusaoPopup(true)} data-testid="cadastro-orcamento-conclusao">
                              {formData.conclusao_orcamento || '-'}
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  <div className="flex justify-end gap-3 pt-4">
                    <Button
                      type="button"
                      variant="outline"
                      className="border-gray-300 px-6"
                      onClick={() => printOS(formData)}
                      data-testid="print-form-button"
                    >
                      <Printer className="mr-2 h-4 w-4" />
                      Imprimir
                    </Button>
                    <Button
                      type="submit"
                      className="bg-gray-900 hover:bg-gray-800 text-white px-8"
                      disabled={formLoading}
                      data-testid="submit-os-button"
                    >
                      {formLoading ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Salvando...
                        </>
                      ) : (
                        'Cadastrar OS'
                      )}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Garantia Subtype Popup */}
        <Dialog open={showGarantiaPopup} onOpenChange={setShowGarantiaPopup}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader><DialogTitle>Selecione o tipo de Garantia</DialogTitle></DialogHeader>
            <div className="flex flex-col gap-3 py-4">
              {GARANTIA_SUBTYPES.map(s => (
                <Button key={s} variant="outline"
                  className="w-full justify-start text-left h-12 text-base"
                  data-testid={`garantia-btn-${s.toLowerCase().replace(/ /g, '-')}`}
                  onClick={() => {
                    setFormData(prev => ({ ...prev, service_type: s }));
                    setShowGarantiaPopup(false);
                  }}
                >{s}</Button>
              ))}
              <Button variant="ghost" className="mt-2 text-gray-500" onClick={() => setShowGarantiaPopup(false)}>
                Cancelar
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Orçamento Status Popup */}
        <Dialog open={showOrcamentoPopup} onOpenChange={setShowOrcamentoPopup}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader><DialogTitle>Status Orcamento</DialogTitle></DialogHeader>
            <div className="flex flex-col gap-3 py-4">
              {ORCAMENTO_STATUS.map(s => (
                <Button key={s} variant="outline"
                  className="w-full justify-start text-left h-12 text-base"
                  data-testid={`orcamento-status-btn-${s.toLowerCase().replace(/ /g, '-')}`}
                  onClick={() => {
                    if (s === 'Execução') {
                      setFormData(prev => ({ ...prev, status_orcamento: s }));
                      setShowOrcamentoPopup(false);
                      setShowOrcamentoConclusaoPopup(true);
                    } else {
                      setFormData(prev => ({ ...prev, status_orcamento: s, conclusao_orcamento: '' }));
                      setShowOrcamentoPopup(false);
                    }
                  }}
                >{s}</Button>
              ))}
              <Button variant="ghost" className="mt-2 text-gray-500" onClick={() => setShowOrcamentoPopup(false)}>Cancelar</Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Orçamento Conclusão Popup */}
        <Dialog open={showOrcamentoConclusaoPopup} onOpenChange={setShowOrcamentoConclusaoPopup}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader><DialogTitle>Conclusao Orcamento</DialogTitle></DialogHeader>
            <div className="flex flex-col gap-3 py-4">
              {ORCAMENTO_CONCLUSAO.map(s => (
                <Button key={s} variant="outline"
                  className="w-full justify-start text-left h-12 text-base"
                  data-testid={`orcamento-conclusao-btn-${s.toLowerCase().replace(/ /g, '-')}`}
                  onClick={() => {
                    setFormData(prev => ({ ...prev, conclusao_orcamento: s }));
                    setShowOrcamentoConclusaoPopup(false);
                  }}
                >{s}</Button>
              ))}
              <Button variant="ghost" className="mt-2 text-gray-500" onClick={() => setShowOrcamentoConclusaoPopup(false)}>Cancelar</Button>
            </div>
          </DialogContent>
        </Dialog>

                {/* Order Detail Modal */}
        <OrderDetailModal
          open={modalOpen}
          onClose={() => { setModalOpen(false); fetchOverdue(); }}
          order={selectedOrder}
          onUpdate={handleUpdateOrder}
          onWhatsApp={openWhatsApp}
          onMaps={openMaps}
          onTelecontrol={openTelecontrol}
          onPrint={printOS}
          onSendWhatsAppCopy={sendWhatsAppCopy}
          onOpenLaudo={handleOpenLaudo}
          onAutosaved={(merged) => applyOrderUpdates(merged?.os_number, merged)}
          onSignatureCompleted={(merged) => applyOrderUpdates(merged?.os_number, merged)}
        />

        {/* Laudo Modal */}
        <LaudoModal
          open={laudoModalOpen}
          onClose={() => setLaudoModalOpen(false)}
          order={laudoOrder}
          getAuthHeader={getAuthHeader}
          onUpdated={(osNumber, patch) => applyOrderUpdates(osNumber, patch)}
        />
      </div>
    </DashboardLayout>
  );
};

// Order Detail Modal Component
const OrderDetailModal = ({ open, onClose, order, onUpdate, onWhatsApp, onMaps, onTelecontrol, onPrint, onSendWhatsAppCopy, onOpenLaudo, onAutosaved, isOverlay = false }) => {
  // Read user role from token (read-only, no need for useAuth here)
  let _role = 'admin';
  try {
    const t = localStorage.getItem('token');
    if (t) _role = JSON.parse(atob(t.split('.')[1]))?.role || 'admin';
  } catch (_) {}
  const isTechnician = _role === 'technician';
  const { getAuthHeader, isInvisacook } = useAuth();
  const [editedOrder, setEditedOrder] = useState(null);
  const [feePaid, setFeePaid] = useState(null);
  useEffect(() => { setFeePaid(null); }, [order?.os_number]);
  const [saving, setSaving] = useState(false);
  const [autoSaving, setAutoSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  const [showGarantiaPopup, setShowGarantiaPopup] = useState(false);
  const [customerHistory, setCustomerHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [signModalOpen, setSignModalOpen] = useState(false);
  const [sigData, setSigData] = useState(null);
  const [showQrPopup, setShowQrPopup] = useState(false);
  const [showOrcamentoPopup, setShowOrcamentoPopup] = useState(false);
  const [showOrcamentoConclusaoPopup, setShowOrcamentoConclusaoPopup] = useState(false);
  const [deletingSig, setDeletingSig] = useState(false);
  const autoSaveTimerRef = useRef(null);
  const initialOrderRef = useRef(null);
  const [printCount, setPrintCount] = useState(0);

  useEffect(() => {
    if (order) {
      setEditedOrder({ ...order });
      // Use non-photo snapshot for autosave comparison so photo changes are
      // handled separately (immediate PUT) and don't trigger this autosave.
      initialOrderRef.current = JSON.stringify((() => {
        const o = {};
        for (const k of Object.keys(order)) {
          if (!k.startsWith('photo_')) o[k] = order[k];
        }
        return o;
      })());
      setLastSaved(null);
      // Fetch customer history
      setHistoryLoading(true);
      axios.get(`${API}/service-orders/${encodeURIComponent(order.os_number)}/customer-history`, getAuthHeader())
        .then(res => setCustomerHistory(res.data.history || []))
        .catch(() => setCustomerHistory([]))
        .finally(() => setHistoryLoading(false));
      // Fetch signature data
      axios.get(`${API}/service-orders/${encodeURIComponent(order.os_number)}/signatures`, getAuthHeader())
        .then(res => setSigData(res.data))
        .catch(() => setSigData(null));
      // Fetch print count
      setPrintCount(order.print_count || 0);
    }
    return () => { if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current); };
    // IMPORTANT: depend on order?.os_number, NOT the whole `order` object.
    // Parent (ServiceOrdersPage.applyOrderUpdates) merges autosave patches
    // back into `selectedOrder`, which changes the object identity but not
    // the OS being viewed. If we depend on `order` we would reset
    // editedOrder mid-typing — overwriting characters the user just typed
    // (reported bug: "campos apagando durante digitação").
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order?.os_number, getAuthHeader]);

  // MERGE-ONLY sync from parent: quando parent atualiza `order` com fresh
  // data, preencher SÓ campos vazios em editedOrder sem sobrescrever edits.
  //
  // BUG FIX (photos "sumindo" ao reabrir OS):
  // Antes esse merge pulava explicitamente qualquer photo_* (linha `if
  // (k.startsWith('photo_')) continue`). A intenção original era não
  // sobrescrever uma foto que o usuário acabou de subir mas o backend
  // ainda não confirmou. Só que o guard já é feito pelo `isPrevEmpty` —
  // pular photo_* incondicionalmente também bloqueava o caso legítimo:
  // handleOrderClick abre o modal com o snapshot da lista (SEM fotos,
  // pra não pesar) e dispara um GET ?include_photos=1 em paralelo; quando
  // esse GET volta, este effect deveria hidratar as fotos no editedOrder.
  // Como estava pulando photo_*, as fotos JAMAIS eram copiadas — parecia
  // que "sumiram", mesmo intactas no banco.
  // Agora photo_* segue o mesmo caminho dos outros campos: se local está
  // vazio E chegou algo do backend, preenche. Se local já tem dataURL
  // (upload em progresso), NÃO sobrescreve porque isPrevEmpty === false.
  useEffect(() => {
    if (!order || !editedOrder) return;
    if (order.os_number !== editedOrder.os_number) return;
    setEditedOrder(prev => {
      if (!prev) return prev;
      const next = { ...prev };
      let changed = false;
      for (const k of Object.keys(order)) {
        const prevVal = prev[k];
        const isPrevEmpty = prevVal === undefined || prevVal === null || prevVal === '';
        if (isPrevEmpty && order[k] !== undefined && order[k] !== null && order[k] !== '') {
          next[k] = order[k];
          changed = true;
        }
      }
      if (!changed) return prev;
      const snap = {};
      for (const kk of Object.keys(next)) {
        if (!kk.startsWith('photo_')) snap[kk] = next[kk];
      }
      initialOrderRef.current = JSON.stringify(snap);
      return next;
    });
  }, [order, editedOrder?.os_number]); // eslint-disable-line react-hooks/exhaustive-deps

  // Compute a snapshot of NON-photo fields. Photos are large (base64) and are
  // saved through a separate immediate-PUT path so we don't include them in
  // this comparison — otherwise JSON.stringify on every keystroke is slow
  // and can cause input lag on mobile.
  const nonPhotoSnapshot = (obj) => {
    if (!obj) return '';
    const o = {};
    for (const k of Object.keys(obj)) {
      if (!k.startsWith('photo_')) o[k] = obj[k];
    }
    return JSON.stringify(o);
  };

  // Save a single photo field immediately (no debounce). Used by image
  // upload/remove handlers so photos persist the moment they're added.
  const savePhotoImmediate = useCallback(async (key, value) => {
    if (!order?.os_number) return;
    try {
      await axios.put(`${API}/service-orders/${encodeURIComponent(order.os_number)}`, { [key]: value }, getAuthHeader());
      setLastSaved(new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }));
    } catch (e) {
      console.error(`Save ${key} failed:`, e);
      toast.error(`Falha ao salvar foto ${key.replace('photo_', '')}`);
    }
  }, [order, getAuthHeader]);

  // Autosave NON-photo fields: debounce 800ms after any change
  useEffect(() => {
    if (!editedOrder || !order || !open) return;
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);

    const current = nonPhotoSnapshot(editedOrder);
    if (current === initialOrderRef.current) return;

    autoSaveTimerRef.current = setTimeout(async () => {
      // Guarda: sem os_number, a URL fica `/service-orders/` e o servidor
      // devolve 405. Isso pode acontecer quando o modal está reiniciando
      // (order antigo já limpo, novo ainda não hidratou).
      if (!order?.os_number) return;
      try {
        setAutoSaving(true);
        // Build a payload of ONLY non-photo fields. This keeps the PUT body
        // small and avoids re-saving photos on every keystroke.
        const payload = {};
        for (const k of Object.keys(editedOrder)) {
          if (!k.startsWith('photo_')) payload[k] = editedOrder[k];
        }
        await axios.put(`${API}/service-orders/${encodeURIComponent(order.os_number)}`, payload, getAuthHeader());
        initialOrderRef.current = current;
        setLastSaved(new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }));
        // Propagate to parent so list state / selectedOrder no longer hold a
        // stale snapshot — prevents data loss when LaudoModal opens with the
        // pre-edit order and saves back its own (incomplete) view.
        if (onAutosaved) {
          try { onAutosaved({ ...order, ...payload }); } catch (_) {}
        }
      } catch (e) {
        console.error('Autosave failed:', e);
      } finally {
        setAutoSaving(false);
      }
    }, 800);

    return () => { if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editedOrder, order, open, getAuthHeader]);

  if (!order || !editedOrder) return null;

  // Flush any pending autosave BEFORE closing the dialog. Without this,
  // a user that types in any field and closes within ~800ms (the debounce
  // window) would lose their edit when the cleanup tears the timer down.
  const flushAndClose = async () => {
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    const current = nonPhotoSnapshot(editedOrder);
    if (editedOrder && initialOrderRef.current && current !== initialOrderRef.current) {
      try {
        const payload = {};
        for (const k of Object.keys(editedOrder)) {
          if (!k.startsWith('photo_')) payload[k] = editedOrder[k];
        }
        await axios.put(`${API}/service-orders/${encodeURIComponent(order.os_number)}`, payload, getAuthHeader());
        if (onAutosaved) {
          try { onAutosaved({ ...order, ...payload }); } catch (_) {}
        }
      } catch (e) { console.warn('Flush-on-close failed:', e); }
    }
    onClose();
  };

  // Wraps Dialog onOpenChange so closing via overlay click / Esc also flushes.
  const handleOpenChange = (next) => {
    if (!next) { flushAndClose(); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onUpdate(editedOrder);
    } finally {
      setSaving(false);
    }
  };

  const getStatusBadge = (status) => {
    const colors = STATUS_COLORS[status] || { bg: '#F3F4F6', text: '#4B5563' };
    return (
      <span 
        className="status-badge"
        style={{ backgroundColor: colors.bg, color: colors.text }}
      >
        {status}
      </span>
    );
  };

  return (
    <>
    <Dialog open={open} onOpenChange={handleOpenChange} modal={true}>
      <DialogContent className="max-w-3xl max-h-[90vh] sm:max-h-[90vh] h-[100dvh] sm:h-auto overflow-hidden p-4 sm:p-6" data-testid="order-detail-modal" data-overlay={isOverlay ? "true" : undefined}>
        <DialogHeader className="border-b border-gray-100 pb-4">
          <DialogTitle className="flex items-center justify-between" style={{ fontFamily: 'Manrope, sans-serif' }}>
            <div className="flex items-center gap-3">
              <span>OS #{order.os_number}</span>
              {getStatusBadge(order.status)}
              {order.priority && (
                <Badge className="text-[10px] px-1.5 py-0 bg-red-600 text-white border-red-600" data-testid="modal-priority-badge">
                  <AlertTriangle className="h-3 w-3 mr-0.5" />
                  Prioridade
                </Badge>
              )}
              {(order.source === 'telecontrol_hisense' || order.source === 'telecontrol') && (
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-blue-300 text-blue-600 font-medium" data-testid="modal-badge-hisense">
                  Telecontrol Hisense
                </Badge>
              )}
              {order.source === 'telecontrol_hq' && (
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-orange-300 text-orange-600 font-medium" data-testid="modal-badge-hq">
                  Telecontrol HQ
                </Badge>
              )}
              {!String(order.source || '').startsWith('telecontrol') && (
                <select
                  value={(feePaid ?? !!order.visit_fee_paid) ? 'paid' : 'unpaid'}
                  onChange={async (e) => {
                    const paid = e.target.value === 'paid';
                    try {
                      await axios.put(`${API}/service-orders/${encodeURIComponent(order.os_number)}`, { visit_fee_paid: paid }, getAuthHeader());
                      setFeePaid(paid);
                    } catch { toast.error('Erro ao salvar taxa'); }
                  }}
                  className={`text-xs rounded-md px-1.5 py-0.5 border font-medium cursor-pointer ${(feePaid ?? order.visit_fee_paid) ? 'bg-green-600 text-white border-green-600' : 'bg-white text-gray-600 border-gray-300'}`}
                  data-testid="modal-taxa-select"
                >
                  <option value="paid">Taxa Paga</option>
                  <option value="unpaid">Taxa não paga</option>
                </select>
              )}
            </div>
            <BrandLogo brand={order.brand} size="md" />
          </DialogTitle>
        </DialogHeader>
        
        <ScrollArea className="max-h-[calc(90vh-180px)] pr-4">
          <div className="space-y-6 py-4">
            {/* Quick Actions */}
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  onPrint({ ...order, ...(editedOrder || {}) }, sigData);
                  axios.post(`${API}/service-orders/${encodeURIComponent(order.os_number)}/print-count`, {}, getAuthHeader())
                    .then(res => setPrintCount(res.data.print_count))
                    .catch(() => {});
                }}
                className="border-gray-300 text-gray-600 hover:bg-gray-50"
                data-testid="modal-print"
              >
                <Printer size={14} className="mr-1" />
                Imprimir
                {printCount > 0 && (
                  <span className="ml-1.5 text-[10px] bg-gray-200 text-gray-600 rounded-full px-1.5 py-0">{printCount}x</span>
                )}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => printOSLabel(order, { size: '50x30' })}
                className="border-gray-300 text-gray-600 hover:bg-gray-50"
                title="Imprimir adesivo térmico 50×30mm (com QR code)"
                data-testid="modal-print-label"
                data="testuii"
              >
                <Tags size={14} className="mr-1" />
                Imprimir Adesivo
              </Button>
              {/* Send copy via WhatsApp — hidden for technicians */}
              {!isTechnician && order.phone1 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onSendWhatsAppCopy(order, sigData)}
                  className="text-gray-500 hover:text-red-600 hover:bg-red-50 transition-colors"
                  title="Enviar cópia via WhatsApp"
                  data-testid="modal-send-whatsapp-copy"
                >
                  <Send size={14} className="mr-1" />
                  Enviar cópia
                </Button>
              )}
              {/* WhatsApp with logo — hidden for technicians */}
              {!isTechnician && order.phone1 && (
                <button
                  onClick={() => onWhatsApp(order.phone1)}
                  className="p-1 hover:opacity-80 transition-opacity"
                  title="WhatsApp"
                  data-testid="modal-whatsapp"
                >
                  <img src={WHATSAPP_LOGO} alt="WhatsApp" className="h-8 w-8 object-contain" />
                </button>
              )}
              {/* Notice for technicians */}
              {isTechnician && (
                <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-1 rounded" data-testid="tech-no-whatsapp-notice">
                  Solicite às atendentes o contato com o cliente.
                </div>
              )}
              {/* QR Code Avaliação */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowQrPopup(true)}
                className="border-gray-300 text-gray-600 hover:bg-gray-50"
                data-testid="modal-qr-btn"
              >
                <QrCode size={14} className="mr-1" />
                QR Code
              </Button>
              {/* Maps with logo */}
              <button
                onClick={() => onMaps(order)}
                className="p-1 hover:opacity-80 transition-opacity"
                title="Google Maps"
                data-testid="modal-maps"
              >
                <img src={MAPS_LOGO} alt="Maps" className="h-8 w-8 object-contain" />
              </button>
              {(order.source === 'telecontrol' || order.source === 'telecontrol_hisense' || order.source === 'telecontrol_hq') && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onTelecontrol(order.os_number)}
                  className="border-gray-300 text-gray-600 hover:bg-gray-50"
                  data-testid="modal-telecontrol"
                >
                  <ExternalLink size={14} className="mr-1" />
                  Abrir no Telecontrol
                </Button>
              )}
              {/* Gerar Laudo - hidden for Invisacook role */}
              {!isInvisacook && (
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  // Flush any pending OrderDetailModal autosave BEFORE opening
                  // LaudoModal so the laudo receives fresh data (incl. fields
                  // the user just typed but the 800ms debounce hasn't fired yet).
                  if (autoSaveTimerRef.current) {
                    clearTimeout(autoSaveTimerRef.current);
                    autoSaveTimerRef.current = null;
                  }
                  let mergedOrder = editedOrder || order;
                  const current = nonPhotoSnapshot(editedOrder);
                  if (editedOrder && initialOrderRef.current && current !== initialOrderRef.current) {
                    try {
                      const payload = {};
                      for (const k of Object.keys(editedOrder)) {
                        if (!k.startsWith('photo_')) payload[k] = editedOrder[k];
                      }
                      await axios.put(`${API}/service-orders/${encodeURIComponent(order.os_number)}`, payload, getAuthHeader());
                      mergedOrder = { ...order, ...payload };
                      initialOrderRef.current = current;
                      if (onAutosaved) { try { onAutosaved(mergedOrder); } catch (_) {} }
                    } catch (e) { console.warn('Pre-Laudo flush failed:', e); }
                  }
                  if (!isOverlay) onClose();
                  onOpenLaudo(mergedOrder);
                }}
                className="bg-white border-2 border-blue-900 text-gray-900 hover:bg-blue-900 hover:text-white transition-colors"
                data-testid="modal-laudo"
              >
                <FileText size={14} className="mr-1" />
                Gerar Laudo
              </Button>
              )}
              {/* Signature button */}
              {sigData?.signed ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onPrint({ ...order, ...(editedOrder || {}) }, sigData)}
                    className="bg-green-50 border-2 border-green-600 text-green-700 hover:bg-green-600 hover:text-white transition-colors"
                    data-testid="modal-view-signatures"
                  >
                    <Eye size={14} className="mr-1" />
                    Visualizar assinaturas
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={deletingSig}
                    onClick={async () => {
                      if (!window.confirm('Tem certeza que deseja excluir as assinaturas?')) return;
                      setDeletingSig(true);
                      try {
                        await axios.put(`${API}/service-orders/${encodeURIComponent(order.os_number)}`, {
                          ...editedOrder,
                          signature_technician: null,
                          signature_client: null,
                          signature_client_cpf: null,
                          signature_client_name: null,
                          signature_tech_name: null,
                          signature_date: null,
                          assinafy_document_id: null,
                          assinafy_status: null,
                        }, getAuthHeader());
                        setSigData(null);
                        setEditedOrder(prev => ({
                          ...prev,
                          signature_technician: null, signature_client: null,
                          signature_client_cpf: null, signature_client_name: null,
                          signature_tech_name: null, signature_date: null
                        }));
                        onUpdate({
                          ...editedOrder,
                          signature_technician: null, signature_client: null,
                          signature_client_cpf: null, signature_client_name: null,
                          signature_tech_name: null, signature_date: null
                        });
                        toast.success('Assinaturas excluidas');
                      } catch (e) {
                        toast.error('Erro ao excluir assinaturas');
                      } finally { setDeletingSig(false); }
                    }}
                    className="border-red-300 text-red-500 hover:bg-red-50"
                    data-testid="modal-delete-signatures"
                  >
                    {deletingSig ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  </Button>
                </>
              ) : sigData?.signature_client ? (
                /* Estado parcial: cliente assinou por link, falta o técnico.
                   Botão fica em destaque verde para indicar "quase lá". */
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSignModalOpen(true)}
                  className="bg-emerald-50 border-2 border-emerald-500 text-emerald-700 hover:bg-emerald-500 hover:text-white transition-colors"
                  data-testid="modal-complete-signature"
                >
                  <Check size={14} className="mr-1" />
                  Completar Assinatura
                  <span className="ml-1.5 text-[10px] bg-emerald-600 text-white rounded-full px-1.5 py-0">cliente ✓</span>
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSignModalOpen(true)}
                  className="bg-white border-2 border-orange-500 text-orange-600 hover:bg-orange-500 hover:text-white transition-colors"
                  data-testid="modal-sign-os"
                >
                  <PenTool size={14} className="mr-1" />
                  Assinar OS
                </Button>
              )}
            </div>

            {/* Status + Priority */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Status</Label>
                <Select 
                  value={editedOrder.status} 
                  onValueChange={(value) => setEditedOrder({ ...editedOrder, status: value })}
                >
                  <SelectTrigger className="border-gray-300" data-testid="modal-status-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {OS_STATUSES.map(status => (
                      <SelectItem key={status} value={status}>{status}</SelectItem>
                    ))}
                    {editedOrder.status && !OS_STATUSES.includes(editedOrder.status) && (
                      <SelectItem key={editedOrder.status} value={editedOrder.status}>{editedOrder.status}</SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Prioridade</Label>
                <button
                  type="button"
                  onClick={() => setEditedOrder(prev => ({ ...prev, priority: !prev.priority }))}
                  className={`h-9 w-full flex items-center justify-center gap-2 border rounded text-sm font-medium transition-colors ${
                    editedOrder.priority
                      ? 'bg-red-50 border-red-400 text-red-700 hover:bg-red-100'
                      : 'bg-gray-50 border-gray-300 text-gray-500 hover:bg-gray-100'
                  }`}
                  data-testid="modal-priority-toggle"
                >
                  <AlertTriangle className={`h-4 w-4 ${editedOrder.priority ? 'text-red-600' : 'text-gray-400'}`} />
                  {editedOrder.priority ? 'PRIORITÁRIA' : 'Normal'}
                </button>
              </div>
              {(editedOrder.service_type === 'Orçamento') && (
                <>
                  <div className="space-y-2">
                    <Label>Status Orcamento</Label>
                    <div className="h-9 flex items-center px-3 border rounded text-sm bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
                         onClick={() => setShowOrcamentoPopup(true)} data-testid="modal-orcamento-status">
                      {editedOrder.status_orcamento || '-'}
                    </div>
                  </div>
                  {editedOrder.status_orcamento === 'Execução' && (
                    <div className="space-y-2">
                      <Label>Conclusao Orcamento</Label>
                      <div className="h-9 flex items-center px-3 border rounded text-sm bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
                           onClick={() => setShowOrcamentoConclusaoPopup(true)} data-testid="modal-orcamento-conclusao">
                        {editedOrder.conclusao_orcamento || '-'}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Dates */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Data de Registro</Label>
                <Input
                  value={editedOrder.registration_date || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, registration_date: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-registration-date"
                />
              </div>
              <div className="space-y-2">
                <Label>Data de Atendimento</Label>
                <Input
                  value={editedOrder.attendance_date || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, attendance_date: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-attendance-date"
                />
              </div>
            </div>

            {/* Customer Info */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Nome Completo</Label>
                <Input
                  value={editedOrder.customer_name || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, customer_name: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-customer-name"
                />
              </div>
              <div className="space-y-2">
                <Label>Email</Label>
                <Input
                  value={editedOrder.email || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, email: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-email"
                />
              </div>
            </div>

            {/* Address */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>CEP</Label>
                <Input
                  value={editedOrder.cep || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, cep: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-cep"
                />
              </div>
              <div className="md:col-span-2 space-y-2">
                <Label>Endereço</Label>
                <Input
                  value={editedOrder.address || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, address: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-address"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-2">
                <Label>Número</Label>
                <Input
                  value={editedOrder.number || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, number: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-number"
                />
              </div>
              <div className="space-y-2">
                <Label>Bairro</Label>
                <Input
                  value={editedOrder.neighborhood || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, neighborhood: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-neighborhood"
                />
              </div>
              <div className="space-y-2">
                <Label>Cidade</Label>
                <Input
                  value={editedOrder.city || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, city: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-city"
                />
              </div>
              <div className="space-y-2">
                <Label>UF</Label>
                <Input
                  value={editedOrder.state || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, state: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-state"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Complemento</Label>
                <Input
                  value={editedOrder.complement || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, complement: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-complement"
                />
              </div>
              <div className="space-y-2">
                <Label>Ponto de Referência</Label>
                <Input
                  value={editedOrder.reference_point || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, reference_point: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-reference-point"
                />
              </div>
            </div>

            {/* Contact */}
            {isTechnician ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800" data-testid="tech-contact-blocked">
                <strong>Contato do cliente oculto.</strong> Solicite às atendentes o contato com o cliente.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>Celular 1</Label>
                  <Input
                    value={editedOrder.phone1 || ''}
                    onChange={(e) => setEditedOrder({ ...editedOrder, phone1: e.target.value })}
                    className="border-gray-300"
                    data-testid="modal-phone1"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Celular 2</Label>
                  <Input
                    value={editedOrder.phone2 || ''}
                    onChange={(e) => setEditedOrder({ ...editedOrder, phone2: e.target.value })}
                    className="border-gray-300"
                    data-testid="modal-phone2"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Fixo</Label>
                  <Input
                    value={editedOrder.landline || ''}
                    onChange={(e) => setEditedOrder({ ...editedOrder, landline: e.target.value })}
                    className="border-gray-300"
                    data-testid="modal-landline"
                  />
                </div>
              </div>
            )}

            {/* Service Type & Visit Fee */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo de Atendimento</Label>
                <Select
                  value={editedOrder.service_type || ''}
                  onValueChange={(value) => {
                    if (value === 'Garantia') {
                      setEditedOrder(prev => ({ ...prev, service_type: value }));
                      setShowGarantiaPopup(true);
                    } else if (value === 'Orçamento') {
                      setEditedOrder(prev => ({ ...prev, service_type: value }));
                      setShowOrcamentoPopup(true);
                    } else {
                      setEditedOrder(prev => ({ ...prev, service_type: value }));
                    }
                  }}
                >
                  <SelectTrigger className="border-gray-300" data-testid="modal-service-type">
                    <SelectValue placeholder="Selecione..." />
                  </SelectTrigger>
                  <SelectContent>
                    {SERVICE_TYPES.map(t => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                    {GARANTIA_SUBTYPES.map(t => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                    {editedOrder.service_type && !SERVICE_TYPES.includes(editedOrder.service_type) && !GARANTIA_SUBTYPES.includes(editedOrder.service_type) && (
                      <SelectItem key={editedOrder.service_type} value={editedOrder.service_type}>{editedOrder.service_type}</SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Taxa de Visita</Label>
                <Input
                  value={editedOrder.visit_fee || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, visit_fee: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-visit-fee"
                />
              </div>
            </div>

            {/* Product */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Produto</Label>
                <Input
                  value={editedOrder.product || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, product: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-product"
                />
              </div>
              <div className="space-y-2">
                <Label>Marca</Label>
                <Input
                  value={editedOrder.brand || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, brand: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-brand"
                />
              </div>
              <div className="space-y-2">
                <Label>Modelo</Label>
                <Input
                  value={editedOrder.model || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, model: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-model"
                />
              </div>
            </div>

            {/* Serial Number and Batch */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Número de Série</Label>
                <Input
                  value={editedOrder.serial_number || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, serial_number: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-serial-number"
                />
              </div>
              <div className="space-y-2">
                <Label>Batch (Versão Produto)</Label>
                <Input
                  value={editedOrder.batch || ''}
                  onChange={(e) => setEditedOrder({ ...editedOrder, batch: e.target.value })}
                  className="border-gray-300"
                  data-testid="modal-batch"
                />
              </div>
            </div>

            {/* Defect */}
            <div className="space-y-2">
              <Label>Defeito Reclamado</Label>
              <Textarea
                value={editedOrder.reported_defect || ''}
                onChange={(e) => setEditedOrder({ ...editedOrder, reported_defect: e.target.value })}
                className="border-gray-300 min-h-20"
                data-testid="modal-defect"
              />
            </div>

            {/* Observations */}
            <div className="space-y-2">
              <Label>Observações</Label>
              <Textarea
                value={editedOrder.observations || ''}
                onChange={(e) => setEditedOrder({ ...editedOrder, observations: e.target.value })}
                className="border-gray-300 min-h-20"
                data-testid="modal-observations"
              />
            </div>

            {/* Laudo Fields - Pre-fill section */}
            <div className="border-t border-gray-200 pt-4 mt-2">
              <h4 className="text-sm font-semibold text-gray-700 mb-3">Dados para Laudo</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Diagnóstico Técnico</Label>
                  <Textarea
                    value={editedOrder.technical_diagnosis || ''}
                    onChange={(e) => setEditedOrder({ ...editedOrder, technical_diagnosis: e.target.value })}
                    className="border-gray-300 min-h-16"
                    data-testid="modal-technical-diagnosis"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Peças Necessárias</Label>
                  <Textarea
                    value={editedOrder.required_parts || ''}
                    onChange={(e) => setEditedOrder({ ...editedOrder, required_parts: e.target.value })}
                    className="border-gray-300 min-h-16"
                    data-testid="modal-required-parts"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                <div className="space-y-2">
                  <Label>Instalação Correta?</Label>
                  <Select value={editedOrder.installation_correct || ''} onValueChange={(v) => setEditedOrder({ ...editedOrder, installation_correct: v })}>
                    <SelectTrigger className="border-gray-300" data-testid="modal-installation"><SelectValue placeholder="Selecione..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="SIM">SIM</SelectItem>
                      <SelectItem value="NÃO">NÃO</SelectItem>
                      <SelectItem value="NÃO VERIFICADO">NÃO VERIFICADO</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Técnico</Label>
                  <Input
                    value={editedOrder.technician || ''}
                    onChange={(e) => setEditedOrder({ ...editedOrder, technician: e.target.value })}
                    className="border-gray-300"
                    data-testid="modal-technician"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-3">
                <div className="space-y-2">
                  <Label>Tensão F1+F2</Label>
                  <Input value={editedOrder.voltage_f1f2 || ''} onChange={(e) => setEditedOrder({ ...editedOrder, voltage_f1f2: e.target.value })} className="border-gray-300" data-testid="modal-voltage-f1f2" />
                </div>
                <div className="space-y-2">
                  <Label>Tensão F1+Terra</Label>
                  <Input value={editedOrder.voltage_f1_terra || ''} onChange={(e) => setEditedOrder({ ...editedOrder, voltage_f1_terra: e.target.value })} className="border-gray-300" data-testid="modal-voltage-f1terra" />
                </div>
                <div className="space-y-2">
                  <Label>Tensão F2+Terra</Label>
                  <Input value={editedOrder.voltage_f2_terra || ''} onChange={(e) => setEditedOrder({ ...editedOrder, voltage_f2_terra: e.target.value })} className="border-gray-300" data-testid="modal-voltage-f2terra" />
                </div>
              </div>

              {/* Photos Upload (Laudo - 1 to 8) */}
              <div className="mt-4">
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-sm font-medium">Fotos do Laudo</Label>
                  <label className="cursor-pointer">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="text-xs h-7 gap-1"
                      onClick={(e) => { e.preventDefault(); e.currentTarget.parentElement.querySelector('input').click(); }}
                      data-testid="bulk-photo-upload-btn"
                    >
                      <Images className="h-3.5 w-3.5" />
                      Enviar fotos em massa
                    </Button>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      className="hidden"
                      data-testid="bulk-photo-upload-input"
                      onChange={(e) => {
                        const files = Array.from(e.target.files || []).slice(0, 8);
                        if (files.length === 0) return;

                        const processFile = (file) => new Promise((resolve) => {
                          const reader = new FileReader();
                          reader.onload = (ev) => {
                            const img = new Image();
                            img.onload = () => {
                              const canvas = document.createElement('canvas');
                              const MAX = 800;
                              let w = img.width, h = img.height;
                              if (w > MAX || h > MAX) {
                                if (w > h) { h = h * MAX / w; w = MAX; }
                                else { w = w * MAX / h; h = MAX; }
                              }
                              canvas.width = w;
                              canvas.height = h;
                              canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                              resolve(canvas.toDataURL('image/jpeg', 0.7));
                            };
                            img.src = ev.target.result;
                          };
                          reader.readAsDataURL(file);
                        });

                        Promise.all(files.map(processFile)).then((dataUrls) => {
                          setEditedOrder(prev => {
                            const updated = { ...prev };
                            dataUrls.forEach((url, i) => {
                              updated[`photo_${i + 1}`] = url;
                            });
                            return updated;
                          });
                          // Persist each photo immediately so a flaky
                          // connection / closed modal doesn't lose them.
                          const photoPayload = {};
                          dataUrls.forEach((url, i) => { photoPayload[`photo_${i + 1}`] = url; });
                          axios.put(`${API}/service-orders/${encodeURIComponent(order.os_number)}`, photoPayload, getAuthHeader())
                            .then(() => setLastSaved(new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })))
                            .catch((err) => { console.error('Bulk photo save failed:', err); toast.error('Falha ao salvar fotos'); });
                          toast.success(`${dataUrls.length} foto(s) adicionada(s)`);
                        });
                        e.target.value = '';
                      }}
                    />
                  </label>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {[
                    { id: 1, label: "Instalação do Produto" },
                    { id: 2, label: "Instalação do Produto" },
                    { id: 3, label: "Local onde o Produto está instalado" },
                    { id: 4, label: "Instalação Elétrica" },
                    { id: 5, label: "Nº de Série" },
                    { id: 6, label: "Peça Avariada" },
                    { id: 7, label: "Defeito/Erro Encontrado" },
                    { id: 8, label: "Defeito/Erro Encontrado" }
                  ].map(photo => {

                    const key = `photo_${photo.id}`;
                    const hasPhoto = !!editedOrder[key];

                    const processImageFile = (file) => {
                      if (!file || !file.type.startsWith('image/')) return;
                      const reader = new FileReader();
                      reader.onload = (ev) => {
                        const img = new Image();
                        img.onload = () => {
                          const canvas = document.createElement('canvas');
                          const MAX = 800;
                          let w = img.width, h = img.height;
                          if (w > MAX || h > MAX) {
                            if (w > h) { h = h * MAX / w; w = MAX; }
                            else { w = w * MAX / h; h = MAX; }
                          }
                          canvas.width = w; canvas.height = h;
                          canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                          const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
                          setEditedOrder(prev => ({ ...prev, [key]: dataUrl }));
                          // Persist this single photo immediately — independent
                          // of the text autosave, so closing the modal doesn't
                          // lose the upload.
                          savePhotoImmediate(key, dataUrl);
                        };
                        img.src = ev.target.result;
                      };
                      reader.readAsDataURL(file);
                    };

                    return (
                      <div key={photo.id} className="relative">
                        <div
                          tabIndex={0}
                          className={`flex flex-col items-center justify-center h-24 border-2 border-dashed rounded-lg cursor-pointer transition-colors outline-none focus:ring-2 focus:ring-blue-300 ${
                            hasPhoto ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-gray-400 bg-gray-50'
                          }`}
                          onClick={() => document.getElementById(`photo-input-${photo.id}`)?.click()}
                          onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('border-blue-500', 'bg-blue-50'); }}
                          onDragLeave={(e) => { e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50'); }}
                          onDrop={(e) => {
                            e.preventDefault();
                            e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50');
                            const file = e.dataTransfer.files?.[0];
                            if (file) processImageFile(file);
                          }}
                          onPaste={(e) => {
                            const items = e.clipboardData?.items;
                            if (!items) return;
                            for (const item of items) {
                              if (item.type.startsWith('image/')) {
                                e.preventDefault();
                                processImageFile(item.getAsFile());
                                return;
                              }
                            }
                          }}
                          data-testid={`modal-photo-drop-${photo.id}`}
                        >
                          {hasPhoto ? (
                            <img
                              src={editedOrder[key]}
                              alt={`Foto ${photo.id}`}
                              className="h-full w-full object-cover rounded-lg"
                            />
                          ) : (
                            <div className="text-center px-1">
                              <Camera className="h-5 w-5 mx-auto text-gray-400" />
                              <span className="text-[10px] text-gray-500 mt-1 block">
                                FOTO {photo.id} – {photo.label}
                              </span>
                              <span className="text-[9px] text-gray-400 mt-0.5 block">Clique, arraste ou cole</span>
                            </div>
                          )}

                          <input
                            id={`photo-input-${photo.id}`}
                            type="file"
                            accept="image/*"
                            className="hidden"
                            data-testid={`modal-photo-${photo.id}`}
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) processImageFile(file);
                              e.target.value = '';
                            }}
                          />
                        </div>

                        {hasPhoto && (
                          <button
                            type="button"
                            className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs hover:bg-red-600 z-10"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setEditedOrder(prev => ({ ...prev, [key]: null }));
                              savePhotoImmediate(key, null);
                            }}
                            data-testid={`modal-photo-${photo.id}-remove`}
                          >
                            x
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Photo 9 - OS Assinada (separate from laudo) */}
              <div className="mt-4 border-t border-gray-200 pt-4">
                <Label className="text-sm font-medium mb-2 block">Foto da OS Assinada (nao inclusa no laudo)</Label>
                <div className="w-48">
                  <div className="relative">
                    <div
                      tabIndex={0}
                      className={`flex flex-col items-center justify-center h-24 border-2 border-dashed rounded-lg cursor-pointer transition-colors outline-none focus:ring-2 focus:ring-blue-300 ${editedOrder.photo_9 ? 'border-orange-400 bg-orange-50' : 'border-gray-300 hover:border-gray-400 bg-gray-50'}`}
                      onClick={() => document.getElementById('photo-input-9')?.click()}
                      onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('border-blue-500', 'bg-blue-50'); }}
                      onDragLeave={(e) => { e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50'); }}
                      onDrop={(e) => {
                        e.preventDefault();
                        e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50');
                        const file = e.dataTransfer.files?.[0];
                        if (!file || !file.type.startsWith('image/')) return;
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                          const img = new Image();
                          img.onload = () => {
                            const canvas = document.createElement('canvas');
                            const MAX = 800;
                            let w = img.width, h = img.height;
                            if (w > MAX || h > MAX) { if (w > h) { h = h * MAX / w; w = MAX; } else { w = w * MAX / h; h = MAX; } }
                            canvas.width = w; canvas.height = h;
                            canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                            const url9 = canvas.toDataURL('image/jpeg', 0.7);
                            setEditedOrder(prev => ({ ...prev, photo_9: url9 }));
                            savePhotoImmediate('photo_9', url9);
                          };
                          img.src = ev.target.result;
                        };
                        reader.readAsDataURL(file);
                      }}
                      onPaste={(e) => {
                        const items = e.clipboardData?.items;
                        if (!items) return;
                        for (const item of items) {
                          if (item.type.startsWith('image/')) {
                            e.preventDefault();
                            const file = item.getAsFile();
                            if (!file) return;
                            const reader = new FileReader();
                            reader.onload = (ev) => {
                              const img = new Image();
                              img.onload = () => {
                                const canvas = document.createElement('canvas');
                                const MAX = 800;
                                let w = img.width, h = img.height;
                                if (w > MAX || h > MAX) { if (w > h) { h = h * MAX / w; w = MAX; } else { w = w * MAX / h; h = MAX; } }
                                canvas.width = w; canvas.height = h;
                                canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                                const url9p = canvas.toDataURL('image/jpeg', 0.7);
                                setEditedOrder(prev => ({ ...prev, photo_9: url9p }));
                                savePhotoImmediate('photo_9', url9p);
                              };
                              img.src = ev.target.result;
                            };
                            reader.readAsDataURL(file);
                            return;
                          }
                        }
                      }}
                      data-testid="modal-photo-drop-9"
                    >
                      {editedOrder.photo_9 ? (
                        <img src={editedOrder.photo_9} alt="OS Assinada" className="h-full w-full object-cover rounded-lg" />
                      ) : (
                        <div className="text-center">
                          <Camera className="h-5 w-5 mx-auto text-orange-400" />
                          <span className="text-xs text-orange-600 mt-1 block">OS Assinada</span>
                          <span className="text-[9px] text-gray-400">Clique, arraste ou cole</span>
                        </div>
                      )}
                      <input id="photo-input-9" type="file" accept="image/*" className="hidden" data-testid="modal-photo-9"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          const reader = new FileReader();
                          reader.onload = (ev) => {
                            const img = new Image();
                            img.onload = () => {
                              const canvas = document.createElement('canvas');
                              const MAX = 800;
                              let w = img.width, h = img.height;
                              if (w > MAX || h > MAX) { if (w > h) { h = h * MAX / w; w = MAX; } else { w = w * MAX / h; h = MAX; } }
                              canvas.width = w; canvas.height = h;
                              canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                              const url9i = canvas.toDataURL('image/jpeg', 0.7);
                              setEditedOrder(prev => ({ ...prev, photo_9: url9i }));
                              savePhotoImmediate('photo_9', url9i);
                            };
                            img.src = ev.target.result;
                          };
                          reader.readAsDataURL(file);
                          e.target.value = '';
                        }}
                      />
                    </div>
                    {editedOrder.photo_9 && (
                      <button type="button" className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs hover:bg-red-600 z-10"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setEditedOrder(prev => ({ ...prev, photo_9: null })); savePhotoImmediate('photo_9', null); }}
                        data-testid="modal-photo-9-remove"
                      >x</button>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Customer History */}
            <div className="border-t border-gray-200 pt-4 mt-2">
              <h4 className="text-sm font-semibold text-gray-700 mb-3" data-testid="customer-history-title">Historico do Cliente</h4>
              {historyLoading ? (
                <div className="flex items-center gap-2 text-sm text-gray-400 py-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Carregando...
                </div>
              ) : customerHistory.length === 0 ? (
                <p className="text-sm text-gray-400">Nenhuma OS anterior encontrada para este cliente.</p>
              ) : (
                <div className="border border-gray-200 rounded-md overflow-hidden max-h-48 overflow-y-auto">
                  <table className="w-full text-sm" data-testid="customer-history-table">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">OS</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Data</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Produto</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {customerHistory.map((item, idx) => (
                        <tr key={idx} className="bg-white hover:bg-gray-50">
                          <td className="px-3 py-2 text-gray-900 font-medium whitespace-nowrap">{item.os_number}</td>
                          <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{item.registration_date}</td>
                          <td className="px-3 py-2 text-gray-600">{item.product} {item.brand}</td>
                          <td className="px-3 py-2">{item.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            {editedOrder.scheduling_history && editedOrder.scheduling_history.length > 0 && (
              <div className="space-y-2">
                <Label>Histórico de Agendamento</Label>
                <div className="border border-gray-200 rounded-md overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Data</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Descrição</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {editedOrder.scheduling_history.map((item, idx) => (
                        <tr key={idx} className="bg-white">
                          <td className="px-3 py-2 text-gray-900 whitespace-nowrap">{item.date}</td>
                          <td className="px-3 py-2 text-gray-600">{item.description}</td>
                          <td className="px-3 py-2 text-gray-600">{item.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="flex flex-col sm:flex-row items-center justify-between gap-2 pt-4 border-t border-gray-100">
          <div className="text-xs text-gray-400 flex items-center gap-1">
            {autoSaving && <><Loader2 className="h-3 w-3 animate-spin" /> Salvando automaticamente...</>}
            {!autoSaving && lastSaved && <><Check className="h-3 w-3 text-green-500" /> Salvo às {lastSaved}</>}
          </div>
          <div className="flex gap-2 w-full sm:w-auto">
            <Button
              variant="outline"
              onClick={onClose}
              className="border-gray-300 w-full sm:w-auto"
              data-testid="modal-cancel"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSave}
              className="bg-gray-900 hover:bg-gray-800 text-white w-full sm:w-auto"
              disabled={saving}
              data-testid="modal-save"
            >
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : (
                'Salvar Alterações'
              )}
            </Button>
          </div>
        </div>

        {/* Garantia Subtype Overlay */}
        {showGarantiaPopup && (
          <div className="absolute inset-0 z-50 bg-white flex flex-col items-center justify-center p-6 rounded-lg" data-testid="garantia-popup">
            <h3 className="text-lg font-semibold mb-6">Selecione o tipo de Garantia</h3>
            <div className="flex flex-col gap-3 w-full max-w-sm">
              {GARANTIA_SUBTYPES.map(s => (
                <Button key={s} variant="outline"
                  className="w-full justify-start text-left h-12 text-base"
                  data-testid={`modal-garantia-btn-${s.toLowerCase().replace(/ /g, '-')}`}
                  onClick={() => {
                    setEditedOrder(prev => ({ ...prev, service_type: s }));
                    setShowGarantiaPopup(false);
                  }}
                >
                  {s}
                </Button>
              ))}
              <Button variant="ghost" className="mt-2 text-gray-500" onClick={() => setShowGarantiaPopup(false)}>
                Cancelar
              </Button>
            </div>
          </div>
        )}
        {/* Orçamento Status Overlay */}
        {showOrcamentoPopup && (
          <div className="absolute inset-0 z-50 bg-white flex flex-col items-center justify-center p-6 rounded-lg" data-testid="modal-orcamento-popup">
            <h3 className="text-lg font-semibold mb-6">Status Orcamento</h3>
            <div className="flex flex-col gap-3 w-full max-w-sm">
              {ORCAMENTO_STATUS.map(s => (
                <Button key={s} variant="outline"
                  className="w-full justify-start text-left h-12 text-base"
                  data-testid={`modal-orc-status-btn-${s.toLowerCase()}`}
                  onClick={() => {
                    if (s === 'Execução') {
                      setEditedOrder(prev => ({ ...prev, status_orcamento: s }));
                      setShowOrcamentoPopup(false);
                      setShowOrcamentoConclusaoPopup(true);
                    } else {
                      setEditedOrder(prev => ({ ...prev, status_orcamento: s, conclusao_orcamento: '' }));
                      setShowOrcamentoPopup(false);
                    }
                  }}
                >{s}</Button>
              ))}
              <Button variant="ghost" className="mt-2 text-gray-500" onClick={() => setShowOrcamentoPopup(false)}>Cancelar</Button>
            </div>
          </div>
        )}
        {/* Orçamento Conclusão Overlay */}
        {showOrcamentoConclusaoPopup && (
          <div className="absolute inset-0 z-50 bg-white flex flex-col items-center justify-center p-6 rounded-lg" data-testid="modal-orcamento-conclusao-popup">
            <h3 className="text-lg font-semibold mb-6">Conclusao Orcamento</h3>
            <div className="flex flex-col gap-3 w-full max-w-sm">
              {ORCAMENTO_CONCLUSAO.map(s => (
                <Button key={s} variant="outline"
                  className="w-full justify-start text-left h-12 text-base"
                  data-testid={`modal-orc-conclusao-btn-${s.toLowerCase().replace(/ /g, '-')}`}
                  onClick={() => {
                    setEditedOrder(prev => ({ ...prev, conclusao_orcamento: s }));
                    setShowOrcamentoConclusaoPopup(false);
                  }}
                >{s}</Button>
              ))}
              <Button variant="ghost" className="mt-2 text-gray-500" onClick={() => setShowOrcamentoConclusaoPopup(false)}>Cancelar</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>

    {/* QR Code Popup */}
    <Dialog open={showQrPopup} onOpenChange={setShowQrPopup}>
      <DialogContent className="w-[280px] max-w-[85vw] p-5 text-center rounded-xl" data-testid="qr-popup" data-overlay="true">
        <DialogTitle className="sr-only">QR Code Avaliação</DialogTitle>
        <img src="/assets/qr-code.png" alt="QR Code Avaliação" className="w-40 h-40 mx-auto" />
        <p className="text-sm font-semibold text-gray-800 mt-3">Avalie o atendimento</p>
        <p className="text-xs text-gray-400 mt-1">Escaneie o QR Code acima</p>
      </DialogContent>
    </Dialog>

    <SignatureModal
      open={signModalOpen}
      onClose={() => setSignModalOpen(false)}
      order={order}
      getAuthHeader={getAuthHeader}
      isOverlay={isOverlay}
      onSigned={(updatedOrder) => {
        // Merge das assinaturas na ordem editada + preserva CPF/nome do cliente
        // vindos do banco (podem ter sido preenchidos via link público).
        const merged = { ...editedOrder, ...updatedOrder };
        setEditedOrder(merged);
        // Re-busca /signatures para pegar `signed=true` canônico e o
        // `order_summary` completo (usado pelo "Visualizar Assinatura").
        axios.get(`${API}/service-orders/${encodeURIComponent(order.os_number)}/signatures`, getAuthHeader())
          .then(res => setSigData(res.data))
          .catch(() => {
            // Fallback pra estado local caso o GET falhe
            setSigData({
              signed: !!(merged.signature_technician && merged.signature_client),
              signature_technician: merged.signature_technician,
              signature_client: merged.signature_client,
              signature_client_name: merged.signature_client_name,
              signature_client_cpf: merged.signature_client_cpf,
              signature_tech_name: merged.signature_tech_name,
              signature_date: merged.signature_date,
              order_summary: merged,
            });
          });
        onUpdate(merged);
        toast.success('OS assinada e finalizada com sucesso!');
      }}
    />
    </>
  );
};

export default ServiceOrdersPage;

// Named exports for reuse in other pages (RoutesPage, DashboardLayout overlay)
export { OrderDetailModal, BrandLogo, STATUS_COLORS, OS_STATUSES, SERVICE_TYPES, GARANTIA_SUBTYPES, ORCAMENTO_STATUS, ORCAMENTO_CONCLUSAO, BRAND_LIST, getBrandLogo };
