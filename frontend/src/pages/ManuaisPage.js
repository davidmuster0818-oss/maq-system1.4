import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import mammoth from 'mammoth';
import { useAuth } from '../context/AuthContext';
import DashboardLayout from '../components/DashboardLayout';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import {
  Upload,
  FileText,
  Search,
  Trash2,
  Eye,
  Loader2,
  FolderOpen,
  Filter,
  ChevronDown,
  ChevronRight,
  Download,
  Pencil,
  Plus,
  GripVertical,
  Check,
  X,
  ExternalLink
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DEFAULT_BRANDS = [
  'Hisense', 'HQ', 'Gorenje', 'Bertazzoni', 'Lofra', 'Franke',
  'Consul', 'Brastemp', 'Electrolux', 'Samsung', 'LG', 'Bosch',
  'Midea', 'Philco', 'Panasonic', 'Viking', 'Liebherr', 'Tecno', 'Belmicro'
];

const DEFAULT_CATEGORIES = [
  'Refrigerador', 'Freezer', 'Lava e Seca', 'Maquina de Lavar',
  'Cooktop', 'Forno', 'Micro-ondas', 'Ar Condicionado', 'Frigobar',
  'Adega', 'Lava-Loucas', 'Secadora', 'Purificador'
];

const formatSize = (bytes) => {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const isMobile = () => /Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

export default function ManuaisPage() {
  const { token } = useAuth();
  const getAuth = () => ({ headers: { Authorization: `Bearer ${token}` } });
  const fileInputRef = useRef(null);

  const [manuais, setManuais] = useState([]);
  const [brands, setBrands] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');

  // Filters
  const [filterBrand, setFilterBrand] = useState('all');
  const [filterCategory, setFilterCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Upload form
  const [showUpload, setShowUpload] = useState(false);
  const [uploadBrand, setUploadBrand] = useState('');
  const [uploadCategory, setUploadCategory] = useState('');

  // Viewer
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerDoc, setViewerDoc] = useState(null);
  const [viewerUrl, setViewerUrl] = useState('');
  const [viewerHtml, setViewerHtml] = useState('');
  const [viewerLoading, setViewerLoading] = useState(false);
  // PPTX slide preview state
  const [slideIdx, setSlideIdx] = useState(1);
  const [slideCount, setSlideCount] = useState(0);
  const [downloadProgress, setDownloadProgress] = useState(0);

  // Collapse/Expand
  const [collapsedBrands, setCollapsedBrands] = useState(new Set());
  const [collapsedCategories, setCollapsedCategories] = useState(new Set());

  // Inline editing
  const [editingBrand, setEditingBrand] = useState(null); // {old: string, new: string}
  const [editingCategory, setEditingCategory] = useState(null); // {brand: string, old: string, new: string}
  const [addingBrand, setAddingBrand] = useState(false);
  const [newBrandName, setNewBrandName] = useState('');
  const [addingCategory, setAddingCategory] = useState(null); // brand name
  const [newCategoryName, setNewCategoryName] = useState('');

  // Drag and drop
  const [dragItem, setDragItem] = useState(null);
  const [dragOverTarget, setDragOverTarget] = useState(null);

  const fetchManuais = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filterBrand && filterBrand !== 'all') params.append('brand', filterBrand);
      if (filterCategory && filterCategory !== 'all') params.append('category', filterCategory);
      if (searchQuery) params.append('search', searchQuery);
      const res = await axios.get(`${API}/manuais?${params}`, getAuth());
      setManuais(res.data.manuais || []);
      setBrands(res.data.brands || []);
      setCategories(res.data.categories || []);
    } catch { toast.error('Erro ao carregar manuais'); }
    finally { setLoading(false); }
  }, [token, filterBrand, filterCategory, searchQuery]);

  useEffect(() => { fetchManuais(); }, [fetchManuais]);

  const handleUpload = async (files) => {
    if (!files || files.length === 0) return;
    const fileList = Array.from(files).slice(0, 30);
    const invalid = fileList.filter(f => {
      const ext = f.name.split('.').pop()?.toLowerCase();
      return !['pdf', 'docx'].includes(ext);
    });
    if (invalid.length > 0) {
      toast.error(`Arquivos invalidos: ${invalid.map(f => f.name).join(', ')}. Use .pdf ou .docx`);
      return;
    }

    setUploading(true);
    let success = 0;
    let fail = 0;

    for (let i = 0; i < fileList.length; i++) {
      setUploadProgress(`Enviando ${i + 1} de ${fileList.length}...`);
      const formData = new FormData();
      formData.append('file', fileList[i]);
      formData.append('brand', uploadBrand);
      formData.append('category', uploadCategory);
      try {
        await axios.post(`${API}/manuais/upload`, formData, {
          ...getAuth(),
          headers: { ...getAuth().headers, 'Content-Type': 'multipart/form-data' }
        });
        success++;
      } catch {
        fail++;
      }
    }

    setUploading(false);
    setUploadProgress('');
    if (success > 0) toast.success(`${success} manual(is) enviado(s)`);
    if (fail > 0) toast.error(`${fail} arquivo(s) falharam`);
    fetchManuais();
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Remover este manual?')) return;
    try {
      await axios.delete(`${API}/manuais/${id}`, getAuth());
      toast.success('Manual removido');
      fetchManuais();
    } catch { toast.error('Erro ao remover'); }
  };

  const openViewer = async (doc) => {
    // On mobile, open PDF directly via URL with token auth (no blob download = instant)
    if (isMobile() && doc.extension === 'pdf') {
      const directUrl = `${API}/manuais/${doc.id}/download?auth=${encodeURIComponent(token)}`;
      window.open(directUrl, '_blank');
      return;
    }

    setViewerDoc(doc);
    setViewerOpen(true);
    setViewerLoading(true);
    setViewerUrl('');
    setViewerHtml('');
    setSlideIdx(1);
    setSlideCount(doc.slide_count || 0);
    setDownloadProgress(0);

    try {
      if (doc.extension === 'pdf') {
        // Desktop: use direct URL for iframe (streaming, no blob)
        const directUrl = `${API}/manuais/${doc.id}/download?auth=${encodeURIComponent(token)}`;
        setViewerUrl(directUrl);
      } else if (doc.extension === 'docx') {
        const res = await axios.get(`${API}/manuais/${doc.id}/download`, {
          ...getAuth(),
          responseType: 'blob',
          onDownloadProgress: (e) => {
            if (e.total) setDownloadProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
        const arrayBuffer = await res.data.arrayBuffer();
        const result = await mammoth.convertToHtml({ arrayBuffer });
        setViewerHtml(result.value);
      } else if (doc.extension === 'pptx' || doc.extension === 'ppt') {
        // PPTX preview: server renders each slide as PNG on demand.
        if (!doc.slide_count) {
          // No cached preview yet — try to trigger regeneration.
          try {
            const r = await axios.post(`${API}/manuais/${doc.id}/regenerate-preview`, {}, getAuth());
            setSlideCount(r.data?.slide_count || 0);
          } catch {
            toast.error('Preview de slides indisponível para este arquivo');
          }
        }
      }
    } catch {
      toast.error('Erro ao abrir arquivo');
    } finally {
      setViewerLoading(false);
      setDownloadProgress(0);
    }
  };

  const closeViewer = () => {
    setViewerOpen(false);
    setViewerDoc(null);
    setViewerUrl('');
    setViewerHtml('');
    setSlideIdx(1);
    setSlideCount(0);
    setDownloadProgress(0);
  };

  const downloadFile = async (doc) => {
    try {
      const res = await axios.get(`${API}/manuais/${doc.id}/download`, {
        ...getAuth(),
        responseType: 'blob'
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.original_filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Erro ao baixar'); }
  };

  // Collapse/Expand
  const toggleBrand = (brand) => {
    setCollapsedBrands(prev => {
      const next = new Set(prev);
      next.has(brand) ? next.delete(brand) : next.add(brand);
      return next;
    });
  };

  const toggleCategory = (key) => {
    setCollapsedCategories(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  // Rename brand
  const handleRenameBrand = async () => {
    if (!editingBrand || !editingBrand.new.trim()) return;
    try {
      await axios.put(`${API}/manuais/actions/rename-group`, {
        type: 'brand', old_name: editingBrand.old, new_name: editingBrand.new.trim()
      }, getAuth());
      toast.success(`Marca renomeada: ${editingBrand.old} -> ${editingBrand.new.trim()}`);
      setEditingBrand(null);
      fetchManuais();
    } catch { toast.error('Erro ao renomear marca'); }
  };

  // Rename category
  const handleRenameCategory = async () => {
    if (!editingCategory || !editingCategory.new.trim()) return;
    try {
      await axios.put(`${API}/manuais/actions/rename-group`, {
        type: 'category', old_name: editingCategory.old, new_name: editingCategory.new.trim()
      }, getAuth());
      toast.success(`Categoria renomeada: ${editingCategory.old} -> ${editingCategory.new.trim()}`);
      setEditingCategory(null);
      fetchManuais();
    } catch { toast.error('Erro ao renomear categoria'); }
  };

  // Delete brand group
  const handleDeleteBrandGroup = async (brand) => {
    const count = manuais.filter(m => m.brand === brand).length;
    if (!window.confirm(`Remover todos os ${count} manuais da marca "${brand}"?`)) return;
    try {
      await axios.delete(`${API}/manuais/actions/delete-group`, {
        ...getAuth(),
        data: { type: 'brand', name: brand }
      });
      toast.success(`${count} manual(is) removido(s)`);
      fetchManuais();
    } catch { toast.error('Erro ao remover grupo'); }
  };

  // Delete category group
  const handleDeleteCategoryGroup = async (brand, category) => {
    const count = manuais.filter(m => m.brand === brand && m.category === category).length;
    if (!window.confirm(`Remover todos os ${count} manuais da categoria "${category}" em "${brand}"?`)) return;
    try {
      // Delete individually since delete-group is by type only
      const toDelete = manuais.filter(m => m.brand === brand && m.category === category);
      for (const m of toDelete) {
        await axios.delete(`${API}/manuais/${m.id}`, getAuth());
      }
      toast.success(`${toDelete.length} manual(is) removido(s)`);
      fetchManuais();
    } catch { toast.error('Erro ao remover categoria'); }
  };

  // Drag and Drop handlers
  const handleDragStart = (e, manual) => {
    setDragItem(manual);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', manual.id);
  };

  const handleDragOver = (e, targetKey) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverTarget(targetKey);
  };

  const handleDragLeave = () => {
    setDragOverTarget(null);
  };

  const handleDrop = async (e, targetBrand, targetCategory) => {
    e.preventDefault();
    setDragOverTarget(null);

    if (!dragItem) return;
    if (dragItem.brand === targetBrand && dragItem.category === targetCategory) {
      setDragItem(null);
      return;
    }

    try {
      await axios.put(`${API}/manuais/actions/move`, {
        manual_id: dragItem.id,
        brand: targetBrand,
        category: targetCategory
      }, getAuth());
      toast.success(`"${dragItem.original_filename}" movido para ${targetBrand} / ${targetCategory}`);
      fetchManuais();
    } catch { toast.error('Erro ao mover manual'); }
    setDragItem(null);
  };

  const handleDragEnd = () => {
    setDragItem(null);
    setDragOverTarget(null);
  };

  // Group manuais by brand then category
  const grouped = {};
  manuais.forEach(m => {
    const b = m.brand || 'Sem Marca';
    const c = m.category || 'Sem Categoria';
    if (!grouped[b]) grouped[b] = {};
    if (!grouped[b][c]) grouped[b][c] = [];
    grouped[b][c].push(m);
  });

  const allBrands = [...new Set([...DEFAULT_BRANDS, ...brands])].sort();
  const allCategories = [...new Set([...DEFAULT_CATEGORIES, ...categories])].sort();

  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto p-4 sm:p-6" data-testid="manuais-page">
        {/* Header */}
        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Manuais</h1>
            <p className="text-sm text-gray-500">{manuais.length} arquivo(s)</p>
          </div>
          <Button
            onClick={() => setShowUpload(!showUpload)}
            className="bg-gray-900 hover:bg-gray-800 text-white"
            data-testid="upload-toggle-btn"
          >
            <Upload className="h-4 w-4 mr-2" /> Enviar Manuais
          </Button>
        </div>

        {/* Upload Panel */}
        {showUpload && (
          <div className="border border-gray-200 rounded-lg p-4 mb-6 bg-gray-50" data-testid="upload-panel">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
              <div>
                <Label className="text-xs text-gray-600">Marca</Label>
                <Select value={uploadBrand} onValueChange={setUploadBrand}>
                  <SelectTrigger data-testid="upload-brand-select"><SelectValue placeholder="Selecionar marca" /></SelectTrigger>
                  <SelectContent>
                    {allBrands.map(b => <SelectItem key={b} value={b}>{b}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs text-gray-600">Categoria</Label>
                <Select value={uploadCategory} onValueChange={setUploadCategory}>
                  <SelectTrigger data-testid="upload-category-select"><SelectValue placeholder="Selecionar categoria" /></SelectTrigger>
                  <SelectContent>
                    {allCategories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end">
                <div className="w-full">
                  <Label className="text-xs text-gray-600">Arquivos (.pdf, .docx) - ate 30</Label>
                  <Input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.docx,.pptx,.ppt"
                    multiple
                    className="cursor-pointer"
                    data-testid="upload-file-input"
                    onChange={(e) => handleUpload(e.target.files)}
                    disabled={uploading}
                  />
                </div>
              </div>
            </div>
            {uploading && (
              <div className="flex items-center gap-2 text-sm text-gray-600" data-testid="upload-progress">
                <Loader2 className="h-4 w-4 animate-spin" /> {uploadProgress}
              </div>
            )}
          </div>
        )}

        {/* Filters */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Buscar por nome..."
              className="pl-9 border-gray-200"
              data-testid="manual-search"
            />
          </div>
          <Select value={filterBrand} onValueChange={setFilterBrand}>
            <SelectTrigger className="w-40 border-gray-200" data-testid="filter-brand">
              <Filter className="h-3 w-3 mr-1 text-gray-400" /><SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas Marcas</SelectItem>
              {allBrands.map(b => (
                <SelectItem key={b} value={b}>{b}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filterCategory} onValueChange={setFilterCategory}>
            <SelectTrigger className="w-44 border-gray-200" data-testid="filter-category">
              <FolderOpen className="h-3 w-3 mr-1 text-gray-400" /><SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas Categorias</SelectItem>
              {allCategories.map(c => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
        ) : manuais.length === 0 ? (
          <div className="text-center py-20 text-gray-400" data-testid="empty-state">
            <FileText className="h-10 w-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm">Nenhum manual encontrado</p>
          </div>
        ) : (
          <div className="space-y-4">
            {Object.entries(grouped).sort(([a],[b]) => a.localeCompare(b)).map(([brand, cats]) => {
              const brandCollapsed = collapsedBrands.has(brand);
              const totalInBrand = Object.values(cats).reduce((s, arr) => s + arr.length, 0);

              return (
                <div key={brand} className="border border-gray-200 rounded-lg overflow-hidden" data-testid={`brand-group-${brand}`}>
                  {/* Brand Header */}
                  <div className="flex items-center gap-2 px-4 py-3 bg-gray-50 border-b border-gray-200">
                    <button
                      onClick={() => toggleBrand(brand)}
                      className="flex items-center gap-2 flex-1 min-w-0 text-left"
                      data-testid={`toggle-brand-${brand}`}
                    >
                      {brandCollapsed ? (
                        <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
                      )}
                      {editingBrand?.old === brand ? (
                        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                          <Input
                            value={editingBrand.new}
                            onChange={e => setEditingBrand({ ...editingBrand, new: e.target.value })}
                            className="h-7 text-sm w-40 border-gray-300"
                            autoFocus
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleRenameBrand();
                              if (e.key === 'Escape') setEditingBrand(null);
                            }}
                            data-testid={`rename-brand-input-${brand}`}
                          />
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={handleRenameBrand} data-testid={`rename-brand-confirm-${brand}`}>
                            <Check className="h-3.5 w-3.5 text-green-600" />
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setEditingBrand(null)}>
                            <X className="h-3.5 w-3.5 text-gray-400" />
                          </Button>
                        </div>
                      ) : (
                        <span className="text-sm font-semibold text-gray-700 truncate">{brand}</span>
                      )}
                      <Badge variant="outline" className="text-[10px] font-normal flex-shrink-0">
                        {totalInBrand}
                      </Badge>
                    </button>
                    {!editingBrand && (
                      <div className="flex items-center gap-0.5 flex-shrink-0">
                        <Button
                          variant="ghost" size="sm" className="h-7 w-7 p-0"
                          onClick={(e) => { e.stopPropagation(); setEditingBrand({ old: brand, new: brand }); }}
                          title="Renomear marca"
                          data-testid={`edit-brand-${brand}`}
                        >
                          <Pencil className="h-3 w-3 text-gray-400" />
                        </Button>
                        <Button
                          variant="ghost" size="sm" className="h-7 w-7 p-0"
                          onClick={(e) => { e.stopPropagation(); handleDeleteBrandGroup(brand); }}
                          title="Remover todos da marca"
                          data-testid={`delete-brand-${brand}`}
                        >
                          <Trash2 className="h-3 w-3 text-red-400" />
                        </Button>
                      </div>
                    )}
                  </div>

                  {/* Brand Content */}
                  {!brandCollapsed && (
                    <div className="p-3 space-y-3">
                      {Object.entries(cats).sort(([a],[b]) => a.localeCompare(b)).map(([cat, files]) => {
                        const catKey = `${brand}::${cat}`;
                        const catCollapsed = collapsedCategories.has(catKey);
                        const isDropTarget = dragOverTarget === catKey;

                        return (
                          <div
                            key={cat}
                            className={`rounded-lg transition-colors ${isDropTarget ? 'bg-blue-50 ring-2 ring-blue-300' : ''}`}
                            onDragOver={(e) => handleDragOver(e, catKey)}
                            onDragLeave={handleDragLeave}
                            onDrop={(e) => handleDrop(e, brand, cat)}
                            data-testid={`category-group-${brand}-${cat}`}
                          >
                            {/* Category Header */}
                            <div className="flex items-center gap-2 px-2 py-1.5">
                              <button
                                onClick={() => toggleCategory(catKey)}
                                className="flex items-center gap-1.5 flex-1 min-w-0 text-left"
                                data-testid={`toggle-category-${brand}-${cat}`}
                              >
                                {catCollapsed ? (
                                  <ChevronRight className="h-3 w-3 text-gray-400 flex-shrink-0" />
                                ) : (
                                  <ChevronDown className="h-3 w-3 text-gray-400 flex-shrink-0" />
                                )}
                                <FolderOpen className="h-3 w-3 text-gray-400 flex-shrink-0" />
                                {editingCategory?.brand === brand && editingCategory?.old === cat ? (
                                  <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                                    <Input
                                      value={editingCategory.new}
                                      onChange={e => setEditingCategory({ ...editingCategory, new: e.target.value })}
                                      className="h-6 text-xs w-36 border-gray-300"
                                      autoFocus
                                      onKeyDown={e => {
                                        if (e.key === 'Enter') handleRenameCategory();
                                        if (e.key === 'Escape') setEditingCategory(null);
                                      }}
                                      data-testid={`rename-category-input-${brand}-${cat}`}
                                    />
                                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={handleRenameCategory} data-testid={`rename-category-confirm-${brand}-${cat}`}>
                                      <Check className="h-3 w-3 text-green-600" />
                                    </Button>
                                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setEditingCategory(null)}>
                                      <X className="h-3 w-3 text-gray-400" />
                                    </Button>
                                  </div>
                                ) : (
                                  <span className="text-xs text-gray-500 truncate">{cat}</span>
                                )}
                                <span className="text-[10px] text-gray-400 flex-shrink-0">({files.length})</span>
                              </button>
                              {!editingCategory && (
                                <div className="flex items-center gap-0.5 flex-shrink-0">
                                  <Button
                                    variant="ghost" size="sm" className="h-6 w-6 p-0"
                                    onClick={() => setEditingCategory({ brand, old: cat, new: cat })}
                                    title="Renomear categoria"
                                    data-testid={`edit-category-${brand}-${cat}`}
                                  >
                                    <Pencil className="h-2.5 w-2.5 text-gray-400" />
                                  </Button>
                                  <Button
                                    variant="ghost" size="sm" className="h-6 w-6 p-0"
                                    onClick={() => handleDeleteCategoryGroup(brand, cat)}
                                    title="Remover categoria"
                                    data-testid={`delete-category-${brand}-${cat}`}
                                  >
                                    <Trash2 className="h-2.5 w-2.5 text-red-400" />
                                  </Button>
                                </div>
                              )}
                            </div>

                            {/* Category Files */}
                            {!catCollapsed && (
                              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 px-2 pb-2">
                                {files.map(m => (
                                  <div
                                    key={m.id}
                                    draggable
                                    onDragStart={(e) => handleDragStart(e, m)}
                                    onDragEnd={handleDragEnd}
                                    className={`flex items-center gap-3 p-3 border border-gray-100 rounded-lg hover:border-gray-300 transition-colors group cursor-grab active:cursor-grabbing ${dragItem?.id === m.id ? 'opacity-40' : ''}`}
                                    data-testid={`manual-card-${m.id}`}
                                  >
                                    <GripVertical className="h-4 w-4 text-gray-300 flex-shrink-0 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity" />
                                    <div className={`w-9 h-9 rounded flex items-center justify-center flex-shrink-0 ${m.extension === 'pdf' ? 'bg-red-50 text-red-500' : m.extension === 'pptx' || m.extension === 'ppt' ? 'bg-orange-50 text-orange-500' : 'bg-blue-50 text-blue-500'}`}>
                                      <FileText className="h-4 w-4" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                      <p className="text-sm font-medium text-gray-800 truncate">{m.original_filename}</p>
                                      <p className="text-[11px] text-gray-400">{formatSize(m.size)} &middot; {m.extension?.toUpperCase()}</p>
                                    </div>
                                    <div className="flex items-center gap-0.5 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity flex-shrink-0">
                                      <Button variant="ghost" size="sm" onClick={() => openViewer(m)} title="Visualizar" data-testid={`view-${m.id}`}>
                                        <Eye className="h-3.5 w-3.5 text-gray-500" />
                                      </Button>
                                      <Button variant="ghost" size="sm" onClick={() => downloadFile(m)} title="Download" data-testid={`download-${m.id}`}>
                                        <Download className="h-3.5 w-3.5 text-gray-500" />
                                      </Button>
                                      <Button variant="ghost" size="sm" onClick={() => handleDelete(m.id)} title="Remover" data-testid={`delete-${m.id}`}>
                                        <Trash2 className="h-3.5 w-3.5 text-red-400" />
                                      </Button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}

                      {/* Add Category Button */}
                      {addingCategory === brand ? (
                        <div className="flex items-center gap-2 px-2 py-1">
                          <Input
                            value={newCategoryName}
                            onChange={e => setNewCategoryName(e.target.value)}
                            placeholder="Nome da categoria..."
                            className="h-7 text-xs w-48 border-gray-300"
                            autoFocus
                            onKeyDown={e => {
                              if (e.key === 'Escape') { setAddingCategory(null); setNewCategoryName(''); }
                            }}
                            data-testid={`add-category-input-${brand}`}
                          />
                          <Button
                            variant="ghost" size="sm" className="h-7 text-xs text-green-600"
                            onClick={() => {
                              if (newCategoryName.trim()) {
                                toast.info(`Categoria "${newCategoryName.trim()}" adicionada. Envie manuais para popula-la.`);
                                setAddingCategory(null);
                                setNewCategoryName('');
                              }
                            }}
                            data-testid={`add-category-confirm-${brand}`}
                          >
                            <Check className="h-3 w-3 mr-1" /> Adicionar
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => { setAddingCategory(null); setNewCategoryName(''); }}>
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setAddingCategory(brand)}
                          className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
                          data-testid={`add-category-btn-${brand}`}
                        >
                          <Plus className="h-3 w-3" /> Adicionar categoria
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Add Brand Button */}
            {addingBrand ? (
              <div className="flex items-center gap-2 p-3 border border-dashed border-gray-300 rounded-lg">
                <Input
                  value={newBrandName}
                  onChange={e => setNewBrandName(e.target.value)}
                  placeholder="Nome da marca..."
                  className="h-8 text-sm w-48 border-gray-300"
                  autoFocus
                  onKeyDown={e => {
                    if (e.key === 'Escape') { setAddingBrand(false); setNewBrandName(''); }
                  }}
                  data-testid="add-brand-input"
                />
                <Button
                  variant="ghost" size="sm" className="text-xs text-green-600"
                  onClick={() => {
                    if (newBrandName.trim()) {
                      toast.info(`Marca "${newBrandName.trim()}" adicionada. Envie manuais para popula-la.`);
                      setAddingBrand(false);
                      setNewBrandName('');
                    }
                  }}
                  data-testid="add-brand-confirm"
                >
                  <Check className="h-3.5 w-3.5 mr-1" /> Adicionar
                </Button>
                <Button variant="ghost" size="sm" className="text-xs" onClick={() => { setAddingBrand(false); setNewBrandName(''); }}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ) : (
              <button
                onClick={() => setAddingBrand(true)}
                className="flex items-center gap-2 w-full p-3 border border-dashed border-gray-300 rounded-lg text-sm text-gray-400 hover:text-gray-600 hover:border-gray-400 transition-colors"
                data-testid="add-brand-btn"
              >
                <Plus className="h-4 w-4" /> Adicionar nova marca
              </button>
            )}
          </div>
        )}
      </div>

      {/* Viewer Modal - Responsive for mobile */}
      <Dialog open={viewerOpen} onOpenChange={closeViewer}>
        <DialogContent className="max-w-5xl w-[95vw] sm:w-full h-[85vh] sm:h-[90vh] p-0 overflow-hidden rounded-lg" data-testid="viewer-modal">
          <div className="flex items-center justify-between p-3 border-b">
            <DialogTitle className="text-sm font-medium truncate flex-1 pr-4">
              {viewerDoc?.original_filename}
            </DialogTitle>
            <div className="flex items-center gap-1 flex-shrink-0">
              {isMobile() && viewerUrl && (
                <Button variant="ghost" size="sm" onClick={() => window.open(viewerUrl, '_blank')} data-testid="viewer-open-external">
                  <ExternalLink className="h-4 w-4" />
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => viewerDoc && downloadFile(viewerDoc)} data-testid="viewer-download">
                <Download className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="flex-1 overflow-auto" style={{ height: 'calc(85vh - 52px)' }}>
            {viewerLoading ? (
              <div className="flex flex-col justify-center items-center h-full gap-3">
                <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
                {downloadProgress > 0 && (
                  <div className="w-48">
                    <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div className="h-full bg-gray-900 rounded-full transition-all duration-300" style={{ width: `${downloadProgress}%` }} />
                    </div>
                    <p className="text-xs text-gray-400 text-center mt-1">{downloadProgress}%</p>
                  </div>
                )}
              </div>
            ) : viewerUrl ? (
              <iframe src={viewerUrl} className="w-full h-full border-0" title="PDF Viewer" data-testid="pdf-viewer" />
            ) : viewerHtml ? (
              <div className="p-4 sm:p-6 max-w-3xl mx-auto prose prose-sm" dangerouslySetInnerHTML={{ __html: viewerHtml }} data-testid="docx-viewer" />
            ) : viewerDoc && (viewerDoc.extension === 'pptx' || viewerDoc.extension === 'ppt') && slideCount > 0 ? (
              <div className="flex flex-col items-center justify-center h-full bg-gray-100 p-4" data-testid="pptx-viewer">
                <div className="flex-1 w-full flex items-center justify-center overflow-auto">
                  <img
                    src={`${API}/manuais/${viewerDoc.id}/slide/${slideIdx}?auth=${encodeURIComponent(token)}`}
                    alt={`Slide ${slideIdx}`}
                    className="max-w-full max-h-full object-contain shadow-lg bg-white"
                    data-testid={`slide-img-${slideIdx}`}
                  />
                </div>
                <div className="flex items-center gap-3 mt-3 bg-white px-4 py-2 rounded-full shadow border border-gray-200">
                  <Button variant="ghost" size="sm" disabled={slideIdx <= 1} onClick={() => setSlideIdx(s => Math.max(1, s - 1))} data-testid="slide-prev-btn">
                    ◀ Anterior
                  </Button>
                  <span className="text-sm font-medium text-gray-700 px-2" data-testid="slide-counter">
                    Slide {slideIdx} / {slideCount}
                  </span>
                  <Button variant="ghost" size="sm" disabled={slideIdx >= slideCount} onClick={() => setSlideIdx(s => Math.min(slideCount, s + 1))} data-testid="slide-next-btn">
                    Próximo ▶
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-400 text-sm gap-3">
                <p>Nenhum conteudo disponivel</p>
                {viewerDoc && (
                  <Button variant="outline" size="sm" onClick={() => viewerDoc && downloadFile(viewerDoc)} data-testid="viewer-download-fallback">
                    <Download className="h-4 w-4 mr-2" /> Baixar arquivo
                  </Button>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
}
