import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import DashboardLayout from '../components/DashboardLayout';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import {
  Package, Plus, Search, ArrowUpCircle, ArrowDownCircle,
  Truck, ClipboardList, AlertTriangle, XCircle, CheckCircle,
  Trash2, Edit, ChevronDown, ChevronUp, BarChart3, QrCode, Upload, X
} from 'lucide-react';
import { printProductLabel } from '../utils/printingService';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api/inventory`;

const DEFAULT_CATEGORIES = [];
const UNITS = ['UN', 'Metro', 'Kg', 'Litro'];
const SERIAL_STATUSES = ['Em estoque', 'Instalado', 'Vendido', 'Em garantia'];
const ENTRY_REASONS = ['Compra', 'Devolução', 'Ajuste positivo'];
const EXIT_REASONS = ['Uso em OS', 'Venda', 'Perda', 'Ajuste negativo'];

const TABS = [
  { id: 'dashboard', label: 'Painel', icon: BarChart3 },
  { id: 'products', label: 'Produtos', icon: Package },
  { id: 'serials', label: 'Seriais', icon: ClipboardList },
  { id: 'movements', label: 'Movimentações', icon: ArrowUpCircle },
  { id: 'suppliers', label: 'Fornecedores', icon: Truck },
];

// === Stat Card ===
const StatCard = ({ label, value, icon: Icon }) => {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4" data-testid={`stat-${label.toLowerCase().replace(/\s/g,'-')}`}>
      <div className="flex items-center gap-2 mb-1 text-gray-600">
        <Icon size={18} />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
    </div>
  );
};

// === Stock Status Badge ===
const StockBadge = ({ current, min }) => {
  if (current === 0 && min > 0) return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700" data-testid="stock-badge-out"><XCircle size={12}/> Sem estoque</span>;
  if (current <= min && min > 0) return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700" data-testid="stock-badge-low"><AlertTriangle size={12}/> Baixo</span>;
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700" data-testid="stock-badge-ok"><CheckCircle size={12}/> OK</span>;
};

// === Product Form Modal ===
const PRODUCT_TYPES = [
  'Geladeira', 'Freezer', 'Fogão', 'Cooktop', 'Forno', 'Micro-ondas',
  'Coifa', 'Depurador', 'Lava-louças', 'Lava-roupas', 'Secadora',
  'Ar-condicionado', 'Adega', 'Cervejeira', 'Purificador', 'Bebedouro',
  'Cafeteira', 'Fritadeira', 'Liquidificador', 'Batedeira', 'Outros',
];

const ProductFormModal = ({ open, onClose, product, onSave, categoryOptions = [] }) => {
  const [form, setForm] = useState({
    code: '', name: '', category: '', brand: '', model: '',
    description: '', unit: 'UN', cost: 0, sale_price: 0,
    default_supplier: '', min_stock: 0, location: '',
    serial_number: '', batch: '',
    product_type: '', image_url: '',
  });
  // Image capture state — see /app/memory/graphify_usage.md notes on this
  // pattern. `imagePreview` is what we render; `imageFile` is the raw File
  // to upload on submit; `hasNewImage` distinguishes "user changed picture"
  // from "user is just editing other fields" so we don't re-upload the
  // same image on every save.
  const [imagePreview, setImagePreview] = useState('');
  const [imageFile, setImageFile] = useState(null);
  const [hasNewImage, setHasNewImage] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);
  const dropRef = useRef(null);

  useEffect(() => {
    if (product) {
      setForm({
        code: '', name: '', category: '', brand: '', model: '',
        description: '', unit: 'UN', cost: 0, sale_price: 0,
        default_supplier: '', min_stock: 0, location: '',
        serial_number: '', batch: '',
        product_type: '', image_url: '',
        ...product,
      });
      setImagePreview(product.image_url || '');
    } else {
      setForm({ code: '', name: '', category: '', brand: '', model: '',
        description: '', unit: 'UN', cost: 0, sale_price: 0,
        default_supplier: '', min_stock: 0, location: '',
        serial_number: '', batch: '',
        product_type: '', image_url: '' });
      setImagePreview('');
    }
    setImageFile(null);
    setHasNewImage(false);
  }, [product, open]);

  // Ctrl+V paste — only when this modal is the active surface. We attach on
  // the container ref and stop propagation so the page-wide paste handler
  // (if any) doesn't also fire.
  useEffect(() => {
    if (!open) return;
    const onPaste = (e) => {
      const items = e.clipboardData?.items || [];
      for (const it of items) {
        if (it.type && it.type.startsWith('image/')) {
          const blob = it.getAsFile();
          if (blob) { processImageFile(blob); e.preventDefault(); break; }
        }
      }
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [open]);

  const processImageFile = (file) => {
    if (!file || !file.type?.startsWith('image/')) return;
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = () => {
      setImagePreview(reader.result);
      setHasNewImage(true);
    };
    reader.readAsDataURL(file);
  };

  const handleFileInputChange = (e) => {
    const file = e.target.files?.[0];
    if (file) processImageFile(file);
    e.target.value = '';  // allow re-selecting the same file
  };

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) processImageFile(file);
  };

  const handleUrlImage = async () => {
    const url = window.prompt('Cole a URL da imagem:');
    if (!url) return;
    const trimmed = url.trim();
    if (!/^https?:\/\//i.test(trimmed)) {
      toast.error('URL inválida');
      return;
    }
    // For a URL, we skip re-upload: store as-is. Preview shows the image
    // straight from the source. hasNewImage stays false because there's
    // nothing to upload to Storage.
    setImagePreview(trimmed);
    setForm(f => ({ ...f, image_url: trimmed }));
    setImageFile(null);
    setHasNewImage(false);
  };

  const clearImage = () => {
    setImagePreview('');
    setImageFile(null);
    setHasNewImage(false);
    setForm(f => ({ ...f, image_url: '' }));
  };

  const uploadImageToStorage = async (file) => {
    const fd = new FormData();
    fd.append('file', file);
    const token = localStorage.getItem('token');
    const res = await axios.post(
      `${API}/inventory/upload-image`,
      fd,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return res.data.url;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      let finalImageUrl = form.image_url || '';
      if (hasNewImage && imageFile) {
        setUploading(true);
        finalImageUrl = await uploadImageToStorage(imageFile);
      }
      onSave({ ...form, image_url: finalImageUrl });
    } catch (err) {
      toast.error('Falha ao enviar imagem: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>{product ? 'Editar Produto' : 'Novo Produto'}</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          {/* IMAGE — first, as user requested. Click / drag / Ctrl+V / URL. */}
          <div>
            <Label className="text-xs">Imagem do Produto</Label>
            <div
              ref={dropRef}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => !imagePreview && fileInputRef.current?.click()}
              className={`relative w-full h-40 border-2 border-dashed rounded-md flex items-center justify-center overflow-hidden cursor-pointer transition-colors ${
                dragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-gray-50 hover:bg-gray-100'
              }`}
              data-testid="product-image-dropzone"
            >
              {imagePreview ? (
                <>
                  <img
                    src={imagePreview}
                    alt="preview"
                    className="max-w-full max-h-full object-contain"
                    data-testid="product-image-preview"
                  />
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); clearImage(); }}
                    className="absolute top-1 right-1 bg-white/90 hover:bg-white rounded-full p-1 shadow"
                    aria-label="Remover imagem"
                    data-testid="product-image-clear"
                  >
                    <X size={14} />
                  </button>
                </>
              ) : (
                <div className="text-center text-xs text-gray-500 px-2">
                  <div className="font-medium">Clique, arraste ou cole (Ctrl+V) uma imagem</div>
                  <div className="mt-0.5">JPG, PNG, WEBP · até 8 MB</div>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileInputChange}
                className="hidden"
                data-testid="product-image-file-input"
              />
            </div>
            <div className="flex gap-2 mt-1">
              <Button type="button" variant="outline" size="sm" className="text-xs h-7"
                onClick={() => fileInputRef.current?.click()} data-testid="product-image-pick">
                Escolher arquivo
              </Button>
              <Button type="button" variant="outline" size="sm" className="text-xs h-7"
                onClick={handleUrlImage} data-testid="product-image-url">
                Usar URL
              </Button>
              {uploading && <span className="text-xs text-blue-600 self-center">Enviando…</span>}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Label className="text-xs">Produto</Label>
              {/* product_type = user-facing category: "Geladeira", "Coifa", etc.
                  Datalist gives a starter set but user can type anything. */}
              <Input
                list="product-type-options"
                value={form.product_type}
                onChange={e => setForm({...form, product_type: e.target.value})}
                className="h-8 text-sm"
                placeholder="Ex: Geladeira, Coifa, Fogão..."
                data-testid="product-type"
              />
              <datalist id="product-type-options">
                {PRODUCT_TYPES.map(t => <option key={t} value={t} />)}
              </datalist></div>
            <div><Label className="text-xs">Código</Label>
              <Input value={form.code} onChange={e => setForm({...form, code: e.target.value})} className="h-8 text-sm" readOnly={!!product} placeholder={product ? '' : 'auto-gerado se vazio'} data-testid="product-code" /></div>
            <div><Label className="text-xs">Nome</Label>
              <Input value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="h-8 text-sm" data-testid="product-name" /></div>
            <div><Label className="text-xs">Categoria</Label>
              {/* Free-text input bound to a `<datalist>` so the user can either
                  pick from already-cadastrada categories OR type a brand-new
                  one. Empty string is OK (categoria não obrigatória). */}
              <Input
                list="product-category-options"
                value={form.category}
                onChange={e => setForm({...form, category: e.target.value})}
                className="h-8 text-sm"
                placeholder="Digite ou escolha..."
                data-testid="product-category"
              />
              <datalist id="product-category-options">
                {categoryOptions.map(c => <option key={c} value={c} />)}
              </datalist></div>
            <div><Label className="text-xs">Marca</Label>
              <Input value={form.brand} onChange={e => setForm({...form, brand: e.target.value})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Modelo</Label>
              <Input value={form.model} onChange={e => setForm({...form, model: e.target.value})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Unidade</Label>
              {/* Free-text — usuário pediu pra digitar qualquer unidade
                  (ex: "5kg", "100ml") ao invés de selecionar de lista fixa.
                  Datalist mantém os defaults como sugestão. */}
              <Input
                list="product-unit-options"
                value={form.unit}
                onChange={e => setForm({...form, unit: e.target.value})}
                className="h-8 text-sm"
                placeholder="Ex: UN, 5kg, 100ml..."
                data-testid="product-unit"
              />
              <datalist id="product-unit-options">
                {UNITS.map(u => <option key={u} value={u} />)}
              </datalist></div>
            <div><Label className="text-xs">Nº de Série</Label>
              <Input value={form.serial_number} onChange={e => setForm({...form, serial_number: e.target.value})} className="h-8 text-sm" data-testid="product-serial-number" /></div>
            <div><Label className="text-xs">Art/Batch</Label>
              <Input value={form.batch} onChange={e => setForm({...form, batch: e.target.value})} className="h-8 text-sm" data-testid="product-batch" /></div>
            <div><Label className="text-xs">Custo (R$)</Label>
              <Input type="number" step="0.01" value={form.cost} onChange={e => setForm({...form, cost: parseFloat(e.target.value) || 0})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Preço Venda (R$)</Label>
              <Input type="number" step="0.01" value={form.sale_price} onChange={e => setForm({...form, sale_price: parseFloat(e.target.value) || 0})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Estoque Mínimo</Label>
              <Input type="number" value={form.min_stock} onChange={e => setForm({...form, min_stock: parseInt(e.target.value) || 0})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Localização</Label>
              <Input value={form.location} onChange={e => setForm({...form, location: e.target.value})} placeholder="Ex: Prateleira A3" className="h-8 text-sm" /></div>
            <div className="col-span-2"><Label className="text-xs">Fornecedor Padrão</Label>
              <Input value={form.default_supplier} onChange={e => setForm({...form, default_supplier: e.target.value})} className="h-8 text-sm" /></div>
          </div>
          <div><Label className="text-xs">Descrição</Label>
            <Input value={form.description} onChange={e => setForm({...form, description: e.target.value})} className="h-8 text-sm" /></div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
            <Button type="submit" size="sm" disabled={uploading} data-testid="product-save-btn">
              {uploading ? 'Enviando…' : 'Salvar'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};

// === Movement Form Modal ===
const MovementFormModal = ({ open, onClose, products, onSave }) => {
  const [form, setForm] = useState({ product_code: '', quantity: 1, movement_type: 'Entrada', reason: 'Compra', document: '', notes: '' });
  const reasons = form.movement_type === 'Entrada' ? ENTRY_REASONS : EXIT_REASONS;

  useEffect(() => {
    if (open) setForm(f => ({ ...f, reason: form.movement_type === 'Entrada' ? 'Compra' : 'Uso em OS' }));
  }, [form.movement_type, open]);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Nova Movimentação</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label className="text-xs">Produto</Label>
            <select value={form.product_code} onChange={e => setForm({...form, product_code: e.target.value})} className="w-full h-8 text-sm border rounded px-2" data-testid="movement-product">
              <option value="">Selecione...</option>
              {products.map(p => <option key={p.code} value={p.code}>{p.code} - {p.name} (est: {p.current_stock})</option>)}
            </select></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label className="text-xs">Tipo</Label>
              <select value={form.movement_type} onChange={e => setForm({...form, movement_type: e.target.value})} className="w-full h-8 text-sm border rounded px-2" data-testid="movement-type">
                <option value="Entrada">Entrada</option>
                <option value="Saída">Saída</option>
              </select></div>
            <div><Label className="text-xs">Quantidade</Label>
              <Input type="number" min={1} value={form.quantity} onChange={e => setForm({...form, quantity: parseInt(e.target.value) || 1})} className="h-8 text-sm" data-testid="movement-qty" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label className="text-xs">Motivo</Label>
              <select value={form.reason} onChange={e => setForm({...form, reason: e.target.value})} className="w-full h-8 text-sm border rounded px-2">
                {reasons.map(r => <option key={r} value={r}>{r}</option>)}
              </select></div>
            <div><Label className="text-xs">Documento (NF/OS)</Label>
              <Input value={form.document} onChange={e => setForm({...form, document: e.target.value})} className="h-8 text-sm" /></div>
          </div>
          <div><Label className="text-xs">Observações</Label>
            <Input value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} className="h-8 text-sm" /></div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
            <Button size="sm" onClick={() => { if(!form.product_code){toast.error('Selecione um produto');return;} onSave(form); }} data-testid="movement-save-btn">Registrar</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// === Supplier Form Modal ===
const SupplierFormModal = ({ open, onClose, onSave }) => {
  const [form, setForm] = useState({ name: '', cnpj: '', contact: '', phone: '', email: '', products_supplied: '' });
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Novo Fornecedor</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label className="text-xs">Nome *</Label><Input value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="h-8 text-sm" data-testid="supplier-name" /></div>
            <div><Label className="text-xs">CNPJ</Label><Input value={form.cnpj} onChange={e => setForm({...form, cnpj: e.target.value})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Contato</Label><Input value={form.contact} onChange={e => setForm({...form, contact: e.target.value})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Telefone</Label><Input value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Email</Label><Input value={form.email} onChange={e => setForm({...form, email: e.target.value})} className="h-8 text-sm" /></div>
            <div><Label className="text-xs">Peças Fornecidas</Label><Input value={form.products_supplied} onChange={e => setForm({...form, products_supplied: e.target.value})} className="h-8 text-sm" /></div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
            <Button size="sm" onClick={() => { if(!form.name){toast.error('Nome é obrigatório');return;} onSave(form); }} data-testid="supplier-save-btn">Salvar</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// ===== MAIN PAGE =====
export default function InventoryPage() {
  const { getAuthHeader } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [products, setProducts] = useState([]);
  const [movements, setMovements] = useState([]);
  const [serials, setSerials] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [search, setSearch] = useState('');
  const [showProductModal, setShowProductModal] = useState(false);
  const [showMovementModal, setShowMovementModal] = useState(false);
  const [showSupplierModal, setShowSupplierModal] = useState(false);
  const [editProduct, setEditProduct] = useState(null);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [brandFilter, setBrandFilter] = useState('');
  const [modelFilter, setModelFilter] = useState('');
  const [stockFilter, setStockFilter] = useState('');

  const load = useCallback(async () => {
    const h = getAuthHeader();
    try {
      const [pRes, dRes] = await Promise.all([
        axios.get(`${API}/products`, h),
        axios.get(`${API}/dashboard`, h),
      ]);
      setProducts(pRes.data);
      setDashboard(dRes.data);
    } catch (e) { if (e.response?.status !== 401) console.error(e); }
  }, [getAuthHeader]);

  const loadTab = useCallback(async () => {
    const h = getAuthHeader();
    try {
      if (activeTab === 'movements') {
        const r = await axios.get(`${API}/movements`, h);
        setMovements(r.data);
      } else if (activeTab === 'serials') {
        const r = await axios.get(`${API}/serials`, h);
        setSerials(r.data);
      } else if (activeTab === 'suppliers') {
        const r = await axios.get(`${API}/suppliers`, h);
        setSuppliers(r.data);
      }
    } catch (e) { if (e.response?.status !== 401) console.error(e); }
  }, [getAuthHeader, activeTab]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadTab(); }, [loadTab]);

  const saveProduct = async (form) => {
    try {
      if (editProduct) {
        await axios.put(`${API}/products/${form.code}`, form, getAuthHeader());
        toast.success('Produto atualizado');
      } else {
        await axios.post(`${API}/products`, form, getAuthHeader());
        toast.success('Produto cadastrado');
      }
      setShowProductModal(false);
      setEditProduct(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao salvar'); }
  };

  const deleteProduct = async (code) => {
    if (!window.confirm(`Remover produto ${code}?`)) return;
    try {
      await axios.delete(`${API}/products/${code}`, getAuthHeader());
      toast.success('Produto removido');
      load();
    } catch (e) { toast.error('Erro ao remover'); }
  };

  const saveMovement = async (form) => {
    try {
      await axios.post(`${API}/movements`, form, getAuthHeader());
      toast.success('Movimentação registrada');
      setShowMovementModal(false);
      load();
      if (activeTab === 'movements') loadTab();
    } catch (e) { toast.error(e.response?.data?.detail || 'Erro'); }
  };

  const saveSupplier = async (form) => {
    try {
      await axios.post(`${API}/suppliers`, form, getAuthHeader());
      toast.success('Fornecedor cadastrado');
      setShowSupplierModal(false);
      loadTab();
    } catch (e) { toast.error(e.response?.data?.detail || 'Erro'); }
  };

  const deleteSupplier = async (name) => {
    if (!window.confirm(`Remover fornecedor ${name}?`)) return;
    try {
      await axios.delete(`${API}/suppliers/${encodeURIComponent(name)}`, getAuthHeader());
      toast.success('Fornecedor removido');
      loadTab();
    } catch (e) { toast.error('Erro'); }
  };

  // Spreadsheet import — accepts .xlsx or .csv. Posts to /products/import which
  // upserts by `code` (auto-generated when absent) and tolerates empty cells.
  const handleImportProductsFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-uploading the same filename
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    const loadingToast = toast.loading('Importando planilha...');
    try {
      const auth = getAuthHeader();
      const res = await axios.post(`${API}/products/import`, fd, {
        headers: { ...auth.headers, 'Content-Type': 'multipart/form-data' },
      });
      const { created = 0, updated = 0, skipped_empty_name: skipped = 0, errors = [] } = res.data || {};
      toast.dismiss(loadingToast);
      const msg = `${created} criado(s), ${updated} atualizado(s)${skipped ? `, ${skipped} ignorado(s) sem nome` : ''}`;
      if (errors.length) toast.warning(`${msg} — ${errors.length} erro(s). Veja o console.`);
      else toast.success(msg);
      if (errors.length) console.warn('Erros na importação:', errors);
      load();
    } catch (err) {
      toast.dismiss(loadingToast);
      toast.error(err?.response?.data?.detail || 'Falha ao importar planilha');
    }
  };

  // Distinct category and brand values found in the current products list
  // — used to populate the filters AND the form datalist. Falls back to the
  // default 4 categories so the dropdowns are never empty.
  const categoryOptions = useMemo(() => {
    const fromProducts = products.map(p => (p?.category || '').trim()).filter(Boolean);
    const merged = Array.from(new Set([...DEFAULT_CATEGORIES, ...fromProducts]));
    return merged.sort((a, b) => a.localeCompare(b, 'pt-BR'));
  }, [products]);

  const brandOptions = useMemo(() => {
    const fromProducts = products.map(p => (p?.brand || '').trim()).filter(Boolean);
    return Array.from(new Set(fromProducts)).sort((a, b) => a.localeCompare(b, 'pt-BR'));
  }, [products]);

  // Model dropdown narrows to the currently-selected brand (if any) so the
  // list stays short. With no brand selected, all distinct models are shown.
  const modelOptions = useMemo(() => {
    const fromProducts = products
      .filter(p => !brandFilter || (p?.brand || '') === brandFilter)
      .map(p => (p?.model || '').trim())
      .filter(Boolean);
    return Array.from(new Set(fromProducts)).sort((a, b) => a.localeCompare(b, 'pt-BR'));
  }, [products, brandFilter]);

  const filteredProducts = products.filter(p => {
    const matchSearch = !search || p.code.toLowerCase().includes(search.toLowerCase()) || (p.name || '').toLowerCase().includes(search.toLowerCase());
    const matchCat = !categoryFilter || (p.category || '') === categoryFilter;
    const matchBrand = !brandFilter || (p.brand || '') === brandFilter;
    const matchModel = !modelFilter || (p.model || '') === modelFilter;
    let matchStock = true;
    if (stockFilter === 'low') matchStock = p.current_stock > 0 && p.current_stock <= p.min_stock;
    if (stockFilter === 'out') matchStock = p.current_stock === 0;
    if (stockFilter === 'ok') matchStock = p.current_stock > p.min_stock;
    return matchSearch && matchCat && matchBrand && matchModel && matchStock;
  });

  // ---- TAB CONTENT ----

  const renderDashboard = () => (
    <div className="space-y-4" data-testid="inventory-dashboard">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total Produtos" value={dashboard?.total_products || 0} icon={Package} />
        <StatCard label="Valor Total" value={`R$ ${(dashboard?.total_value || 0).toLocaleString('pt-BR', {minimumFractionDigits:2})}`} icon={BarChart3} />
        <StatCard label="Estoque Baixo" value={dashboard?.low_stock || 0} icon={AlertTriangle} />
        <StatCard label="Sem Estoque" value={dashboard?.out_of_stock || 0} icon={XCircle} />
      </div>

      {(dashboard?.purchase_suggestions?.length > 0) && (
        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-semibold text-sm mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-amber-500" /> Sugestão de Compra</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs text-gray-500">
                <th className="pb-2">Código</th><th className="pb-2">Produto</th><th className="pb-2 text-center">Estoque</th><th className="pb-2 text-center">Mínimo</th><th className="pb-2 text-center">Comprar</th>
              </tr></thead>
              <tbody>
                {dashboard.purchase_suggestions.map((s, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-1.5 font-mono text-xs">{s.code}</td>
                    <td className="py-1.5">{s.name}</td>
                    <td className="py-1.5 text-center"><span className={s.current_stock === 0 ? 'text-red-600 font-bold' : 'text-amber-600'}>{s.current_stock}</span></td>
                    <td className="py-1.5 text-center">{s.min_stock}</td>
                    <td className="py-1.5 text-center font-bold text-blue-600">{s.to_buy}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(dashboard?.recent_movements?.length > 0) && (
        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-semibold text-sm mb-3">Movimentações Recentes</h3>
          <div className="space-y-1.5">
            {dashboard.recent_movements.map((m, i) => (
              <div key={i} className="flex items-center gap-2 text-sm py-1 border-b last:border-0">
                {m.movement_type === 'Entrada'
                  ? <ArrowUpCircle size={14} className="text-green-500" />
                  : <ArrowDownCircle size={14} className="text-red-500" />}
                <span className="font-mono text-xs text-gray-500">{m.product_code}</span>
                <span className={m.movement_type === 'Entrada' ? 'text-green-600' : 'text-red-600'}>
                  {m.movement_type === 'Entrada' ? '+' : '-'}{m.quantity}
                </span>
                <span className="text-gray-400 text-xs">{m.reason}</span>
                <span className="ml-auto text-xs text-gray-400">{new Date(m.date).toLocaleDateString('pt-BR')}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  const renderProducts = () => (
    <div className="space-y-3" data-testid="inventory-products">
      <div className="flex gap-2 flex-wrap items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-2.5 top-2.5 text-gray-400" />
          <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar produto..." className="pl-8 h-9 text-sm" data-testid="product-search" />
        </div>
        <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)} className="h-9 text-sm border rounded px-2" data-testid="category-filter">
          <option value="">Todas Categorias</option>
          {categoryOptions.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={brandFilter} onChange={e => { setBrandFilter(e.target.value); setModelFilter(''); }} className="h-9 text-sm border rounded px-2" data-testid="brand-filter">
          <option value="">Todas Marcas</option>
          {brandOptions.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        <select value={modelFilter} onChange={e => setModelFilter(e.target.value)} className="h-9 text-sm border rounded px-2" data-testid="model-filter">
          <option value="">Todos Modelos</option>
          {modelOptions.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <select value={stockFilter} onChange={e => setStockFilter(e.target.value)} className="h-9 text-sm border rounded px-2">
          <option value="">Todo Estoque</option>
          <option value="ok">OK</option>
          <option value="low">Baixo</option>
          <option value="out">Sem Estoque</option>
        </select>
        <Button size="sm" onClick={() => { setEditProduct(null); setShowProductModal(true); }} data-testid="add-product-btn">
          <Plus size={14} className="mr-1" /> Novo Produto
        </Button>
        <Button size="sm" variant="outline" onClick={() => setShowMovementModal(true)} data-testid="add-movement-btn">
          <ArrowUpCircle size={14} className="mr-1" /> Movimentação
        </Button>
        <label htmlFor="import-products-file" className="cursor-pointer">
          <input
            id="import-products-file"
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={handleImportProductsFile}
            data-testid="import-products-file-input"
          />
          <span
            className="inline-flex items-center justify-center rounded-md text-sm font-medium border border-input bg-background h-9 px-3 hover:bg-accent hover:text-accent-foreground"
            data-testid="import-products-btn"
          >
            <Upload size={14} className="mr-1" /> Importar Planilha
          </span>
        </label>
      </div>

      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="bg-gray-50 border-b text-left text-xs text-gray-500 uppercase">
            <th className="px-3 py-2">Código</th>
            <th className="px-3 py-2">Nome</th>
            <th className="px-3 py-2">Categoria</th>
            <th className="px-3 py-2">Marca</th>
            <th className="px-3 py-2">Modelo</th>
            <th className="px-3 py-2 text-center">Unidade</th>
            <th className="px-3 py-2">Local</th>
            <th className="px-3 py-2 text-right">Preço</th>
            <th className="px-3 py-2 w-20"></th>
          </tr></thead>
          <tbody>
            {filteredProducts.length === 0 ? (
              <tr><td colSpan={9} className="text-center py-8 text-gray-400">Nenhum produto encontrado</td></tr>
            ) : filteredProducts.map(p => (
              <tr key={p.code} className="border-b last:border-0 hover:bg-gray-50" data-testid={`product-row-${p.code}`}>
                <td className="px-3 py-2 font-mono text-xs">{p.code}</td>
                <td className="px-3 py-2 font-medium">{p.name}</td>
                <td className="px-3 py-2 text-xs text-gray-500">{p.category}</td>
                <td className="px-3 py-2 text-xs">{p.brand}</td>
                <td className="px-3 py-2 text-xs text-gray-600">{p.model}</td>
                <td className="px-3 py-2 text-center font-medium" data-testid={`product-unit-${p.code}`}>{p.unit || '—'}</td>
                <td className="px-3 py-2 text-xs text-gray-400">{p.location}</td>
                <td className="px-3 py-2 text-right text-xs">R$ {(p.sale_price || 0).toFixed(2)}</td>
                <td className="px-3 py-2 text-right">
                  <div className="flex gap-1 justify-end">
                    <button
                      onClick={() => printProductLabel(p, { size: '50x30' })}
                      className="p-1 text-gray-400 hover:text-gray-900"
                      title="Imprimir adesivo térmico com QR code"
                      data-testid={`product-print-${p.code}`}
                    >
                      <QrCode size={14} />
                    </button>
                    <button onClick={() => { setEditProduct(p); setShowProductModal(true); }} className="p-1 text-gray-400 hover:text-blue-600"><Edit size={14} /></button>
                    <button onClick={() => deleteProduct(p.code)} className="p-1 text-gray-400 hover:text-red-600"><Trash2 size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderSerials = () => (
    <div className="space-y-3" data-testid="inventory-serials">
      <div className="bg-white rounded-lg border overflow-hidden">
        <div className="px-4 py-3 border-b flex justify-between items-center">
          <h3 className="font-semibold text-sm">Controle por Número de Série</h3>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="bg-gray-50 border-b text-left text-xs text-gray-500 uppercase">
            <th className="px-3 py-2">Nº Série</th><th className="px-3 py-2">Produto</th><th className="px-3 py-2">Fornecedor</th>
            <th className="px-3 py-2">Status</th><th className="px-3 py-2">OS</th><th className="px-3 py-2">Entrada</th>
          </tr></thead>
          <tbody>
            {serials.length === 0 ? (
              <tr><td colSpan={6} className="text-center py-6 text-gray-400">Nenhum serial cadastrado</td></tr>
            ) : serials.map((s, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="px-3 py-2 font-mono text-xs">{s.serial_number}</td>
                <td className="px-3 py-2">{s.product_code}</td>
                <td className="px-3 py-2 text-xs">{s.supplier}</td>
                <td className="px-3 py-2"><span className={`px-2 py-0.5 rounded-full text-xs ${
                  s.status === 'Em estoque' ? 'bg-green-100 text-green-700' :
                  s.status === 'Instalado' ? 'bg-blue-100 text-blue-700' :
                  s.status === 'Vendido' ? 'bg-gray-100 text-gray-700' :
                  'bg-amber-100 text-amber-700'}`}>{s.status}</span></td>
                <td className="px-3 py-2 text-xs">{s.os_number || '-'}</td>
                <td className="px-3 py-2 text-xs text-gray-400">{s.entry_date ? new Date(s.entry_date).toLocaleDateString('pt-BR') : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderMovements = () => (
    <div className="space-y-3" data-testid="inventory-movements">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowMovementModal(true)}><Plus size={14} className="mr-1" /> Nova Movimentação</Button>
      </div>
      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="bg-gray-50 border-b text-left text-xs text-gray-500 uppercase">
            <th className="px-3 py-2">Data</th><th className="px-3 py-2">Produto</th><th className="px-3 py-2">Tipo</th>
            <th className="px-3 py-2 text-center">Qtd</th><th className="px-3 py-2">Motivo</th><th className="px-3 py-2">Documento</th>
            <th className="px-3 py-2 text-center">Estoque Ant.</th><th className="px-3 py-2 text-center">Estoque Nov.</th>
          </tr></thead>
          <tbody>
            {movements.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-6 text-gray-400">Nenhuma movimentação</td></tr>
            ) : movements.map((m, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="px-3 py-2 text-xs">{new Date(m.date).toLocaleDateString('pt-BR')}</td>
                <td className="px-3 py-2 font-mono text-xs">{m.product_code}</td>
                <td className="px-3 py-2">{m.movement_type === 'Entrada'
                  ? <span className="inline-flex items-center gap-1 text-green-600"><ArrowUpCircle size={12}/>Entrada</span>
                  : <span className="inline-flex items-center gap-1 text-red-600"><ArrowDownCircle size={12}/>Saída</span>}</td>
                <td className="px-3 py-2 text-center font-bold">{m.quantity}</td>
                <td className="px-3 py-2 text-xs">{m.reason}</td>
                <td className="px-3 py-2 text-xs font-mono">{m.document || '-'}</td>
                <td className="px-3 py-2 text-center text-xs">{m.previous_stock}</td>
                <td className="px-3 py-2 text-center font-bold text-xs">{m.new_stock}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderSuppliers = () => (
    <div className="space-y-3" data-testid="inventory-suppliers">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowSupplierModal(true)}><Plus size={14} className="mr-1" /> Novo Fornecedor</Button>
      </div>
      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="bg-gray-50 border-b text-left text-xs text-gray-500 uppercase">
            <th className="px-3 py-2">Nome</th><th className="px-3 py-2">CNPJ</th><th className="px-3 py-2">Contato</th>
            <th className="px-3 py-2">Telefone</th><th className="px-3 py-2">Email</th><th className="px-3 py-2">Peças</th><th className="px-3 py-2 w-14"></th>
          </tr></thead>
          <tbody>
            {suppliers.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-6 text-gray-400">Nenhum fornecedor</td></tr>
            ) : suppliers.map((s, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="px-3 py-2 font-medium">{s.name}</td>
                <td className="px-3 py-2 text-xs font-mono">{s.cnpj}</td>
                <td className="px-3 py-2 text-xs">{s.contact}</td>
                <td className="px-3 py-2 text-xs">{s.phone}</td>
                <td className="px-3 py-2 text-xs">{s.email}</td>
                <td className="px-3 py-2 text-xs">{s.products_supplied}</td>
                <td className="px-3 py-2"><button onClick={() => deleteSupplier(s.name)} className="p-1 text-gray-400 hover:text-red-600"><Trash2 size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <DashboardLayout>
      <div className="p-4 md:p-6 space-y-4" data-testid="inventory-page">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-800">Estoque</h1>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1" data-testid="inventory-tabs">
          {TABS.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors
                ${activeTab === tab.id ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
              data-testid={`tab-${tab.id}`}>
              <tab.icon size={14} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'dashboard' && renderDashboard()}
        {activeTab === 'products' && renderProducts()}
        {activeTab === 'serials' && renderSerials()}
        {activeTab === 'movements' && renderMovements()}
        {activeTab === 'suppliers' && renderSuppliers()}

        {/* Modals */}
        <ProductFormModal open={showProductModal} onClose={() => { setShowProductModal(false); setEditProduct(null); }}
          product={editProduct} onSave={saveProduct} categoryOptions={categoryOptions} />
        <MovementFormModal open={showMovementModal} onClose={() => setShowMovementModal(false)}
          products={products} onSave={saveMovement} />
        <SupplierFormModal open={showSupplierModal} onClose={() => setShowSupplierModal(false)}
          onSave={saveSupplier} />
      </div>
    </DashboardLayout>
  );
}
