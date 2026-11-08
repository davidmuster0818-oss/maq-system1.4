import React, { useState, useRef, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { toast } from 'sonner';
import { 
  ChevronLeft, ChevronRight, Upload, X, 
  Download, Loader2, Check, Save, Eye, Clock
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const PHOTO_LABELS = [
  "FOTO 1 – Instalação do Produto",
  "FOTO 2 – Instalação do Produto",
  "FOTO 3 – Local onde o Produto está Instalado",
  "FOTO 4 – Instalação Elétrica",
  "FOTO 5 – Nº de Serie",
  "FOTO 6 – Peça Avariada",
  "FOTO 7 – Defeito/Erro Encontrado",
  "FOTO 8 – Defeito/Erro Encontrado"
];

const RECALL_PHOTO_LABELS = [
  "FOTO 1 – Imagem geral do local onde o produto foi instalado",
  "FOTO 2 – Lateral esquerda do produto",
  "FOTO 3 – Lateral direita do produto",
  "FOTO 4 – Topo do produto",
  "FOTO 5 – Etiqueta do produto com Batch e nº de série",
  "FOTO 6 – Foto geral do interior do produto",
  "FOTO 7 – Foto do cordão de solda do cesto"
];

const TOTAL_STEPS = 4;

const ImageUploadField = ({ index, label, image, onImageChange }) => {
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const compressImage = (file) => {
    return new Promise((resolve) => {
      const img = new window.Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const MAX_SIZE = 800;
        let w = img.width, h = img.height;
        if (w > MAX_SIZE || h > MAX_SIZE) {
          if (w > h) { h = Math.round(h * MAX_SIZE / w); w = MAX_SIZE; }
          else { w = Math.round(w * MAX_SIZE / h); h = MAX_SIZE; }
        }
        canvas.width = w;
        canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL('image/jpeg', 0.8));
      };
      img.src = URL.createObjectURL(file);
    });
  };

  const handleFileSelect = async (file) => {
    if (file && file.type.startsWith('image/')) {
      const compressed = await compressImage(file);
      onImageChange(index, compressed);
    }
  };

  const handlePaste = async (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) await handleFileSelect(file);
        return;
      }
    }
  };

  return (
    <div className="space-y-1">
      <Label className="text-[10px] font-medium leading-tight">{label}</Label>
      <div
        tabIndex={0}
        className={`border-2 border-dashed rounded-lg p-1.5 cursor-pointer transition-colors outline-none focus:ring-2 focus:ring-blue-300
          ${isDragging ? 'border-blue-500 bg-blue-50' : image ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-gray-400'}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => { e.preventDefault(); setIsDragging(false); handleFileSelect(e.dataTransfer.files?.[0]); }}
        onPaste={handlePaste}
        onClick={() => fileInputRef.current?.click()}
        data-testid={`image-upload-${index}`}
      >
        <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
          onChange={(e) => handleFileSelect(e.target.files?.[0])} />
        {image ? (
          <div className="relative">
            <img src={image} alt={label} className="w-full h-24 object-cover rounded" />
            <button onClick={(e) => { e.stopPropagation(); onImageChange(index, null); }}
              className="absolute top-0.5 right-0.5 p-0.5 bg-red-500 text-white rounded-full hover:bg-red-600">
              <X size={10} />
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-20 text-gray-400">
            <Upload size={18} className="mb-1" />
            <span className="text-[9px]">Clique, arraste ou cole</span>
          </div>
        )}
      </div>
    </div>
  );
};

const StepIndicator = ({ currentStep }) => {
  const labels = ['Dados', 'Fotos', 'Final', 'Preview'];
  return (
    <div className="flex items-center justify-center mb-3">
      {[1, 2, 3, 4].map((step) => (
        <React.Fragment key={step}>
          <div className="flex flex-col items-center">
            <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium
              ${currentStep >= step ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'}`}>
              {step}
            </div>
            <span className="text-[8px] mt-0.5 text-gray-500">{labels[step - 1]}</span>
          </div>
          {step < TOTAL_STEPS && <div className={`w-8 h-0.5 mx-0.5 mt-[-8px] ${currentStep > step ? 'bg-blue-600' : 'bg-gray-200'}`} />}
        </React.Fragment>
      ))}
    </div>
  );
};

const LaudoModal = ({ open, onClose, order, getAuthHeader, onUpdated }) => {
  const [laudoType, setLaudoType] = useState(null); // null = show selector, 'hisense' or 'recall'
  const [currentStep, setCurrentStep] = useState(1);
  const [isGenerating, setIsGenerating] = useState(false);
  const [digitalLink, setDigitalLink] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [autoSaving, setAutoSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const [savedAgoMinutes, setSavedAgoMinutes] = useState(0);

  // Live "Salvo há X min" — recompute every 30s so the counter increments
  // visibly. When autosave fires, `lastSavedAt` bumps to Date.now() and this
  // effect immediately resets the counter to 0.
  useEffect(() => {
    if (!lastSavedAt) return;
    const compute = () => {
      const mins = Math.max(0, Math.floor((Date.now() - lastSavedAt) / 60000));
      setSavedAgoMinutes(mins);
    };
    compute();
    const t = setInterval(compute, 30000);
    return () => clearInterval(t);
  }, [lastSavedAt]);
  const [laudoHistory, setLaudoHistory] = useState([]);
  const autoSaveTimerRef = useRef(null);
  const lastSnapshotRef = useRef('');
  const draftLoadedRef = useRef(false);
  // Autosave gating flags — replace the previous fixed 300ms timeout with
  // REAL signals so autosave never fires before both loads have completed.
  // If either load fails, we still enable autosave (`try/catch/finally`
  // below sets both to true) so the user can start editing offline.
  const [draftFetched, setDraftFetched] = useState(false);
  const [photosFetched, setPhotosFetched] = useState(false);
  
  const [formData, setFormData] = useState({
    os_number: '', customer_name: '', model: '', serial_number: '',
    batch: '', brand: '', service_type: '', reported_defect: '',
    technical_diagnosis: '', installation_correct: '', required_parts: '',
  });

  const [images, setImages] = useState(Array(8).fill(null));

  const [finalData, setFinalData] = useState({
    technical_notes: '', final_status: '', technician: '',
    location: 'BELO HORIZONTE', date: new Date().toLocaleDateString('pt-BR'),
    voltage_f1f2: '', voltage_f1_terra: '', voltage_f2_terra: '',
  });

  useEffect(() => {
    if (order && open) {
      // Reset gating flags on every open so autosave stays locked until both
      // network calls (draft + fresh OS with photos) complete.
      setDraftFetched(false);
      setPhotosFetched(false);

      // Load draft
      axios.get(`${API}/laudo/draft/${order.os_number}`, getAuthHeader())
        .then(res => {
          const draft = res.data;
          if (draft && draft.os_number) {
            setFormData({
              os_number: draft.os_number || order.os_number || '',
              customer_name: draft.customer_name || order.customer_name || '',
              model: draft.model || order.model || '',
              serial_number: draft.serial_number || order.serial_number || '',
              batch: draft.batch || order.batch || '',
              brand: draft.brand || order.brand || '',
              service_type: draft.service_type || order.service_type || '',
              reported_defect: draft.reported_defect || order.reported_defect || '',
              technical_diagnosis: draft.technical_diagnosis || order.technical_diagnosis || '',
              installation_correct: draft.installation_correct || order.installation_correct || '',
              required_parts: draft.required_parts || order.required_parts || '',
            });
            setFinalData({
              technical_notes: draft.technical_notes || '',
              final_status: draft.final_status || '',
              technician: draft.technician || order.technician || '',
              location: draft.location || 'BELO HORIZONTE',
              date: draft.date || new Date().toLocaleDateString('pt-BR'),
              voltage_f1f2: draft.voltage_f1f2 || order.voltage_f1f2 || '',
              voltage_f1_terra: draft.voltage_f1_terra || order.voltage_f1_terra || '',
              voltage_f2_terra: draft.voltage_f2_terra || order.voltage_f2_terra || '',
            });
            // Load photos: draft images first, fallback to OS photos
            const draftImages = (draft.images || []).length > 0 ? draft.images : null;
            const orderPhotos = [1,2,3,4,5,6,7,8].map(i => order[`photo_${i}`] || null);
            if (draftImages && draftImages.some(img => img)) {
              setImages(draftImages.map(img => img || null));
            } else if (orderPhotos.some(p => p)) {
              setImages(orderPhotos);
            }
            toast.info('Rascunho anterior carregado');
          } else {
            setFormData({
              os_number: order.os_number || '', customer_name: order.customer_name || '',
              model: order.model || '', serial_number: order.serial_number || '',
              batch: order.batch || '', brand: order.brand || '',
              service_type: order.service_type || '', reported_defect: order.reported_defect || '',
              technical_diagnosis: order.technical_diagnosis || '',
              installation_correct: order.installation_correct || '',
              required_parts: order.required_parts || '',
            });
            setFinalData({
              technical_notes: '', final_status: '', 
              technician: order.technician || '',
              location: 'BELO HORIZONTE', date: new Date().toLocaleDateString('pt-BR'),
              voltage_f1f2: order.voltage_f1f2 || '',
              voltage_f1_terra: order.voltage_f1_terra || '',
              voltage_f2_terra: order.voltage_f2_terra || '',
            });
            // Load photos from OS
            const orderPhotos = [1,2,3,4,5,6,7,8].map(i => order[`photo_${i}`] || null);
            if (orderPhotos.some(p => p)) setImages(orderPhotos);
          }
        })
        .catch(() => {
          setFormData({
            os_number: order.os_number || '', customer_name: order.customer_name || '',
            model: order.model || '', serial_number: order.serial_number || '',
            batch: order.batch || '', brand: order.brand || '',
            service_type: order.service_type || '', reported_defect: order.reported_defect || '',
            technical_diagnosis: order.technical_diagnosis || '',
            installation_correct: order.installation_correct || '',
            required_parts: order.required_parts || '',
          });
          setFinalData({
            technical_notes: '', final_status: '',
            technician: order.technician || '',
            location: 'BELO HORIZONTE', date: new Date().toLocaleDateString('pt-BR'),
            voltage_f1f2: order.voltage_f1f2 || '',
            voltage_f1_terra: order.voltage_f1_terra || '',
            voltage_f2_terra: order.voltage_f2_terra || '',
          });
          // Load photos from OS
          const orderPhotos = [1,2,3,4,5,6,7,8].map(i => order[`photo_${i}`] || null);
          if (orderPhotos.some(p => p)) setImages(orderPhotos);
        })
        .finally(() => { setDraftFetched(true); });

      // Force-fetch the OS WITH photos so the modal's `images` state is
      // hydrated from the authoritative Supabase copy (order prop may come
      // from the list without ?include_photos=1). Autosave stays locked
      // until this completes — see gating effect below.
      axios.get(`${API}/service-orders/${encodeURIComponent(order.os_number)}?include_photos=1`, getAuthHeader())
        .then(res => {
          const fresh = res.data || {};
          setImages(prev => {
            const next = [...prev];
            let changed = false;
            for (let i = 0; i < 8; i++) {
              if (!next[i] && fresh[`photo_${i + 1}`]) {
                next[i] = fresh[`photo_${i + 1}`];
                changed = true;
              }
            }
            return changed ? next : prev;
          });
        })
        .catch(() => { /* offline / rate-limit / 5xx — user can still work locally */ })
        .finally(() => { setPhotosFetched(true); });

      // Load history
      axios.get(`${API}/laudo/history/${order.os_number}`, getAuthHeader())
        .then(res => setLaudoHistory(res.data || []))
        .catch(() => setLaudoHistory([]));
      
      setCurrentStep(1);
      setLaudoType(null);
    }
    if (!open) {
      // Flush any pending save when the modal closes (e.g. parent toggled
      // `open` directly). flushAndClose isn't called in this case so we
      // ensure the timer doesn't get lost in the cleanup.
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
        // Best-effort save with current refs
        const snap = JSON.stringify({
          formData: formDataRef.current,
          finalData: finalDataRef.current,
          images: imagesRef.current,
        });
        if (snap !== lastSnapshotRef.current && order?.os_number) {
          runLaudoSave().catch(() => {});
        }
      }
      draftLoadedRef.current = false;
      // Reset gating so the next open re-blocks autosave until both loads finish.
      setDraftFetched(false);
      setPhotosFetched(false);
    }
  }, [order?.os_number, open, getAuthHeader]); // eslint-disable-line react-hooks/exhaustive-deps
  // ↑ IMPORTANT: depend on order?.os_number, NOT the whole order object.
  // Parent (ServiceOrdersPage.applyOrderUpdates) merges save patches back
  // into `laudoOrder`, which changes the prop identity but not the OS being
  // edited. If we depended on the full `order` we would reload the draft +
  // reset formData mid-typing — overwriting what the user just typed AND
  // resetting laudoType to null (which would visually close the Hisense /
  // Recall step view, matching the "modal fechando após 3s" symptom).

  // MERGE-ONLY sync from parent — fill empty formData/finalData/images
  // from order prop when parent refreshes it, without overwriting edits.
  useEffect(() => {
    if (!open || !order?.os_number || !draftLoadedRef.current) return;
    const fdMap = {
      customer_name: 'customer_name', model: 'model', serial_number: 'serial_number',
      batch: 'batch', brand: 'brand', service_type: 'service_type',
      reported_defect: 'reported_defect', technical_diagnosis: 'technical_diagnosis',
      installation_correct: 'installation_correct', required_parts: 'required_parts',
    };
    const fndMap = {
      voltage_f1f2: 'voltage_f1f2', voltage_f1_terra: 'voltage_f1_terra',
      voltage_f2_terra: 'voltage_f2_terra', technician: 'technician',
    };
    setFormData(prev => {
      const next = { ...prev };
      let changed = false;
      for (const [k, ok] of Object.entries(fdMap)) {
        const isPrevEmpty = !prev[k] || String(prev[k]).trim() === '';
        const orderVal = order[ok];
        if (isPrevEmpty && orderVal && String(orderVal).trim() !== '') {
          next[k] = orderVal; changed = true;
        }
      }
      return changed ? next : prev;
    });
    setFinalData(prev => {
      const next = { ...prev };
      let changed = false;
      for (const [k, ok] of Object.entries(fndMap)) {
        const isPrevEmpty = !prev[k] || String(prev[k]).trim() === '';
        const orderVal = order[ok];
        if (isPrevEmpty && orderVal && String(orderVal).trim() !== '') {
          next[k] = orderVal; changed = true;
        }
      }
      return changed ? next : prev;
    });
    setImages(prev => {
      const next = [...prev];
      let changed = false;
      for (let i = 0; i < 8; i++) {
        if (!next[i] && order[`photo_${i + 1}`]) {
          next[i] = order[`photo_${i + 1}`]; changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [order, open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Refs holding the latest values — used by autosave & flush so we never
  // capture stale closures (which is what caused inconsistent saves on mobile).
  const formDataRef = useRef(formData);
  const finalDataRef = useRef(finalData);
  const imagesRef = useRef(images);
  useEffect(() => { formDataRef.current = formData; }, [formData]);
  useEffect(() => { finalDataRef.current = finalData; }, [finalData]);
  useEffect(() => { imagesRef.current = images; }, [images]);

  // Autosave GATE — arm the debounced autosave ONLY when BOTH network loads
  // (draft + fresh OS with photos) have completed. Replaces the previous
  // fixed 300ms timeout that raced with slow mobile networks and could fire
  // autosave before hydration, wiping photos with empty state. If either
  // fetch fails, `.finally()` still flips the flag so the user can work.
  useEffect(() => {
    if (draftFetched && photosFetched) {
      draftLoadedRef.current = true;
      lastSnapshotRef.current = '';
    }
  }, [draftFetched, photosFetched]);

  // The actual save routine — single source of truth. Called by the debounced
  // autosave AND by flush-on-close. Both laudo/save and the OS PUT run
  // INDEPENDENTLY so one failing doesn't cancel the other.
  //
  // IMPORTANT: the OS PUT (step 2) is ADDITIVE — we only send a field if the
  // user actually filled it in this LaudoModal session. Empty/blank fields are
  // NOT sent so that data the user typed elsewhere (e.g. inside the
  // OrderDetailModal which runs its own autosave in parallel) is preserved.
  // Sending `field: ''` for unfilled fields previously caused destructive
  // overwrites of just-saved OS data — see fix in iteration 11.
  const runLaudoSave = useCallback(async () => {
    if (!order?.os_number) return;
    const fd = formDataRef.current || {};
    const fnd = finalDataRef.current || {};
    const imgs = imagesRef.current || [];
    setAutoSaving(true);
    try {
      // 1) Save laudo draft (independent).
      // ADDITIVE payload: only include fields the user actually filled. The
      // backend also skips empty keys, but stripping here is cheaper on the
      // wire AND avoids Supabase egress on empty strings.
      const additive = {};
      Object.entries({ ...fd, ...fnd }).forEach(([k, v]) => {
        if (v !== undefined && v !== null && String(v).trim() !== '') additive[k] = v;
      });
      additive.os_number = fd.os_number || order.os_number;  // always required
      additive.images = imgs.map(img => img || "");  // photos_count derived from length
      try { await axios.post(`${API}/laudo/save`, additive, getAuthHeader()); }
      catch (e) { console.warn('laudo/save failed:', e?.response?.status); }

      // 2) Sync into OS (independent — even if step 1 failed, photos still persist).
      // Build payload additively: only include fields with non-empty values.
      const osUpdate = {};
      const addIfFilled = (k, v) => {
        const s = (v ?? '').toString();
        if (s.trim() !== '') osUpdate[k] = s;
      };
      // Photos: ADDITIVE — only send photo_i if we actually have image data
      // for that slot. This prevents accidental wiping of photos already in
      // the DB when the modal opens with empty slots (e.g. race condition
      // during hydration on slow mobile networks). Explicit clearing is now
      // owned by handleImageChange(index, null) + a dedicated action; the
      // autosave path must never destroy existing photos.
      for (let i = 0; i < 8; i++) {
        const raw = imgs[i];
        if (typeof raw === 'string' && raw.trim() !== '') {
          osUpdate[`photo_${i + 1}`] = raw;
        }
      }
      // Text fields: only sync when actually filled in LaudoModal.
      addIfFilled('model', fd.model);
      addIfFilled('serial_number', fd.serial_number);
      addIfFilled('batch', fd.batch);
      addIfFilled('brand', fd.brand);
      addIfFilled('service_type', fd.service_type);
      addIfFilled('reported_defect', fd.reported_defect);
      addIfFilled('technical_diagnosis', fd.technical_diagnosis);
      addIfFilled('installation_correct', fd.installation_correct);
      addIfFilled('required_parts', fd.required_parts);
      addIfFilled('voltage_f1f2', fnd.voltage_f1f2);
      addIfFilled('voltage_f1_terra', fnd.voltage_f1_terra);
      addIfFilled('voltage_f2_terra', fnd.voltage_f2_terra);
      addIfFilled('technician', fnd.technician);
      try {
        await axios.put(`${API}/service-orders/${encodeURIComponent(fd.os_number || order.os_number)}`, osUpdate, getAuthHeader());
        // Notify parent so list / OrderDetailModal stay in sync with backend.
        if (typeof onUpdated === 'function') {
          try { onUpdated(fd.os_number || order.os_number, osUpdate); } catch (_) {}
        }
      }
      catch (e) { console.warn('OS sync failed:', e?.response?.status); }

      lastSnapshotRef.current = JSON.stringify({ formData: fd, finalData: fnd, images: imgs });
      // Store the timestamp so the header badge can show "Salvo há X min"
      // updating live via a 1-min interval below.
      setLastSavedAt(Date.now());
    } finally {
      setAutoSaving(false);
    }
  }, [order?.os_number, getAuthHeader, onUpdated]); // eslint-disable-line react-hooks/exhaustive-deps

  // Autosave: debounce 600ms after any change.
  // Depend on `order?.os_number` (not `order`) so this effect does NOT
  // re-fire when the parent merges save patches into `order` — which would
  // cause re-runs to clear and re-schedule the timer endlessly, sometimes
  // racing with the input setState and losing the latest character.
  useEffect(() => {
    if (!open || !order?.os_number || !draftLoadedRef.current) return;
    const snapshot = JSON.stringify({ formData, finalData, images });
    if (snapshot === lastSnapshotRef.current) return;
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(() => { runLaudoSave().catch(() => {}); }, 600);
    return () => { if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current); };
  }, [formData, finalData, images, open, order?.os_number, runLaudoSave]); // eslint-disable-line react-hooks/exhaustive-deps

  // Flush pending save BEFORE closing — guarantees no data loss when the
  // user closes the modal quickly after typing (very common on mobile).
  const flushAndClose = useCallback(async () => {
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    const snapshot = JSON.stringify({
      formData: formDataRef.current,
      finalData: finalDataRef.current,
      images: imagesRef.current,
    });
    if (snapshot !== lastSnapshotRef.current) {
      await runLaudoSave();
    }
    onClose();
  }, [runLaudoSave, onClose]);

  // Also save on pagehide / visibilitychange (mobile background) so we don't
  // lose work when the user switches apps with the modal open.
  useEffect(() => {
    if (!open) return;
    const onPageHide = () => {
      const snapshot = JSON.stringify({
        formData: formDataRef.current,
        finalData: finalDataRef.current,
        images: imagesRef.current,
      });
      if (snapshot !== lastSnapshotRef.current) {
        // Best-effort blocking call via fetch keepalive
        try {
          const fd = formDataRef.current || {};
          const fnd = finalDataRef.current || {};
          const imgs = imagesRef.current || [];
          const body = JSON.stringify({ ...fd, ...fnd, images: imgs.map(i => i || "") });
          fetch(`${API}/laudo/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(getAuthHeader().headers || {}) },
            body, keepalive: true,
          }).catch(() => {});
        } catch (_) {}
      }
    };
    window.addEventListener('pagehide', onPageHide);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') onPageHide();
    });
    return () => window.removeEventListener('pagehide', onPageHide);
  }, [open, getAuthHeader]);

  const handleImageChange = (index, imageData) => {
    const newImages = [...images];
    newImages[index] = imageData;
    setImages(newImages);
  };

  const saveDraft = async () => {
    setIsSaving(true);
    try {
      const data = { ...formData, ...finalData, images: images.map(img => img || "") };
      await axios.post(`${API}/laudo/save`, data, getAuthHeader());

      // Persist the 8 photos directly on the OS so other flows (routes —
      // "Concluir Atendimento") can verify completion regardless of draft.
      // ADDITIVE: only send slots with actual image data (matches runLaudoSave
      // semantics). Empty slots are NOT sent — server-side guard also refuses
      // to clear existing photos without explicit `clear_photos` flag.
      try {
        const photoUpdate = {};
        images.forEach((img, i) => {
          if (typeof img === 'string' && img.trim() !== '') {
            photoUpdate[`photo_${i + 1}`] = img;
          }
        });
        if (Object.keys(photoUpdate).length > 0) {
          await axios.put(`${API}/service-orders/${encodeURIComponent(formData.os_number)}`, photoUpdate, getAuthHeader());
        }
      } catch (_) { /* non-fatal — draft still saved */ }

      toast.success('Rascunho salvo!');
    } catch { toast.error('Erro ao salvar rascunho'); }
    finally { setIsSaving(false); }
  };

  const generateLaudo = async () => {
    setIsGenerating(true);
    const activePhotoLabels = laudoType === 'recall' ? RECALL_PHOTO_LABELS : PHOTO_LABELS;
    const laudoData = { ...formData, ...finalData, images: images.map(img => img || ""), laudo_type: laudoType || 'hisense', photo_labels: activePhotoLabels };
    if (laudoType === 'mastermaq') {
      try {
        const { data } = await axios.post(`${API}/laudo/mastermaq-digital`, laudoData, getAuthHeader());
        const link = data.url || `${process.env.REACT_APP_BACKEND_URL}${data.path}`;
        setDigitalLink(link);
        navigator.clipboard?.writeText(link).catch(() => {});
        window.open(link, '_blank');
        toast.success('Laudo digital gerado — link copiado!');
        axios.get(`${API}/laudo/history/${formData.os_number}`, getAuthHeader()).then(res => setLaudoHistory(res.data || [])).catch(() => {});
      } catch (error) {
        toast.error(error?.response?.data?.detail || 'Erro ao gerar laudo digital.');
      } finally {
        setIsGenerating(false);
      }
      return;
    }
    try {
      const response = await axios.post(`${API}/laudo/generate-docx`, laudoData, {
        ...getAuthHeader(), responseType: 'blob'
      });
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `Laudo_OS_${formData.os_number}.docx`;
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      // Defer cleanup to avoid removeChild conflicts with React
      setTimeout(() => {
        try { document.body.removeChild(link); } catch (_) {}
        window.URL.revokeObjectURL(url);
      }, 100);
      toast.success('Laudo gerado e salvo no histórico!');
      // Reload history
      axios.get(`${API}/laudo/history/${formData.os_number}`, getAuthHeader())
        .then(res => setLaudoHistory(res.data || []))
        .catch(() => {});
    } catch (error) {
      console.error('Error generating laudo:', error);
      toast.error('Erro ao gerar laudo.');
    } finally {
      setIsGenerating(false);
    }
  };

  const isRecall = laudoType === 'recall';
  const activePhotoLabels = isRecall ? RECALL_PHOTO_LABELS : PHOTO_LABELS;

  const renderStep1 = () => (
    <div className="space-y-3">
      <h3 className="font-semibold text-sm text-gray-700 border-b pb-1">
        {isRecall ? 'Laudo de Inspeção - Recall' : 'Informações da OS'}
      </h3>
      {laudoHistory.length > 0 && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2" data-testid="laudo-history-badge">
          <div className="flex items-center gap-2 text-green-700 text-xs font-medium">
            <Check size={14} />
            Laudo já gerado {laudoHistory.length}x
            <span className="text-green-500 font-normal">
              (último: {new Date(laudoHistory[0].generated_at).toLocaleDateString('pt-BR')} às {new Date(laudoHistory[0].generated_at).toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit'})})
            </span>
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div><Label className="text-xs">Nº OS</Label>
          <Input value={formData.os_number} readOnly className="bg-gray-100 h-8 text-sm" data-testid="laudo-os-number" /></div>
        <div><Label className="text-xs">Cliente</Label>
          <Input value={formData.customer_name} onChange={e => setFormData({...formData, customer_name: e.target.value})} className="h-8 text-sm" data-testid="laudo-customer" /></div>
        <div><Label className="text-xs">Modelo</Label>
          <Input value={formData.model} onChange={e => setFormData({...formData, model: e.target.value})} className="h-8 text-sm" data-testid="laudo-model" /></div>
        <div><Label className="text-xs">Nº Série</Label>
          <Input value={formData.serial_number} onChange={e => setFormData({...formData, serial_number: e.target.value})} className="h-8 text-sm" data-testid="laudo-serial" /></div>
        <div><Label className="text-xs">Batch (ART)</Label>
          <Input value={formData.batch} onChange={e => setFormData({...formData, batch: e.target.value})} className="h-8 text-sm" data-testid="laudo-batch" /></div>
        {!isRecall && (
          <div><Label className="text-xs">Marca</Label>
            <Input value={formData.brand} onChange={e => setFormData({...formData, brand: e.target.value})} className="h-8 text-sm" data-testid="laudo-brand" /></div>
        )}
      </div>
      {!isRecall && (
        <>
          <h3 className="font-semibold text-sm text-gray-700 border-b pb-1 mt-2">Diagnóstico</h3>
          <div className="space-y-2">
            <div><Label className="text-xs">Defeito Relatado</Label>
              <Textarea value={formData.reported_defect} onChange={e => setFormData({...formData, reported_defect: e.target.value})} className="text-sm min-h-[45px]" data-testid="laudo-defect" /></div>
            <div><Label className="text-xs">Diagnóstico Técnico</Label>
              <Textarea value={formData.technical_diagnosis} onChange={e => setFormData({...formData, technical_diagnosis: e.target.value})} className="text-sm min-h-[45px]" data-testid="laudo-diagnosis" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-xs">Instalação Correta?</Label>
                <select value={formData.installation_correct} onChange={e => setFormData({...formData, installation_correct: e.target.value})}
                  className="w-full h-8 text-sm border rounded px-2" data-testid="laudo-installation">
                  <option value="">--</option>
                  <option value="SIM">SIM</option>
                  <option value="NÃO">NÃO</option>
                </select></div>
              <div><Label className="text-xs">Peças Necessárias</Label>
                <Input value={formData.required_parts} onChange={e => setFormData({...formData, required_parts: e.target.value})} className="h-8 text-sm" data-testid="laudo-parts" /></div>
            </div>
          </div>
        </>
      )}
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-3">
      <h3 className="font-semibold text-sm text-gray-700 border-b pb-1">
        Fotos do Atendimento ({activePhotoLabels.length} imagens{isRecall ? ' - Recall' : ''})
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {activePhotoLabels.map((label, i) => (
          <ImageUploadField key={i} index={i} label={label} image={images[i]} onImageChange={handleImageChange} />
        ))}
      </div>
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-3">
      {!isRecall && (
        <>
          <h3 className="font-semibold text-sm text-gray-700 border-b pb-1">Tensão de Alimentação</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div><Label className="text-xs">F1 + F2 (V)</Label>
              <Input value={finalData.voltage_f1f2} onChange={e => setFinalData({...finalData, voltage_f1f2: e.target.value})} className="h-8 text-sm" data-testid="laudo-voltage-f1f2" /></div>
            <div><Label className="text-xs">F1 + Terra (V)</Label>
              <Input value={finalData.voltage_f1_terra} onChange={e => setFinalData({...finalData, voltage_f1_terra: e.target.value})} className="h-8 text-sm" data-testid="laudo-voltage-f1terra" /></div>
            <div><Label className="text-xs">F2 + Terra (V)</Label>
              <Input value={finalData.voltage_f2_terra} onChange={e => setFinalData({...finalData, voltage_f2_terra: e.target.value})} className="h-8 text-sm" data-testid="laudo-voltage-f2terra" /></div>
          </div>
        </>
      )}
      <h3 className="font-semibold text-sm text-gray-700 border-b pb-1 mt-2">Finalização</h3>
      <div className="space-y-2">
        <div><Label className="text-xs">Observações Técnicas</Label>
          <Textarea value={finalData.technical_notes} onChange={e => setFinalData({...finalData, technical_notes: e.target.value})} className="text-sm min-h-[45px]" data-testid="laudo-notes" /></div>
        <div><Label className="text-xs">Status Final</Label>
          <select value={finalData.final_status} onChange={e => setFinalData({...finalData, final_status: e.target.value})}
            className="w-full h-9 text-sm border rounded px-2 bg-white" data-testid="laudo-final-status">
            <option value="">Selecione o status...</option>
            <option value="✅ VISITA TÉCNICA REALIZADA, CONCLUÍDA">✅ VISITA TÉCNICA REALIZADA, CONCLUÍDA</option>
            <option value="❌ AGUARDANDO ENVIO DAS PEÇAS SOLICITADAS PARA CONSERTO">❌ AGUARDANDO ENVIO DAS PEÇAS SOLICITADAS PARA CONSERTO</option>
          </select></div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div><Label className="text-xs">Técnico Responsável</Label>
            <Input value={finalData.technician} onChange={e => setFinalData({...finalData, technician: e.target.value})} className="h-8 text-sm" data-testid="laudo-technician" /></div>
          <div><Label className="text-xs">Local</Label>
            <Input value={finalData.location} onChange={e => setFinalData({...finalData, location: e.target.value})} className="h-8 text-sm" data-testid="laudo-location" /></div>
          <div><Label className="text-xs">Data</Label>
            <Input value={finalData.date} onChange={e => setFinalData({...finalData, date: e.target.value})} className="h-8 text-sm" data-testid="laudo-date" /></div>
        </div>
      </div>
    </div>
  );

  const renderPreview = () => {
    const imageCount = images.filter(Boolean).length;
    const brandDisplay = formData.brand && formData.brand.toLowerCase().includes('gorenje')
      ? 'Produto Gorenje ✓ | Produto Hisense'
      : 'Produto Gorenje | Produto Hisense ✓';
    
    if (isRecall) {
      return (
        <div className="bg-white border border-gray-300 rounded" data-testid="laudo-preview" style={{fontSize:'11px'}}>
          <div className="bg-[#1a2744] text-white px-4 py-2 flex justify-between items-center rounded-t">
            <span className="font-bold text-xs">Laudo Técnico de Inspeção - Recall</span>
            <span className="text-[10px] opacity-80">ASSISTÊNCIA TÉC. MASTERMAQ</span>
          </div>
          <table className="w-full border-collapse text-[11px]" style={{borderSpacing:0}}>
            <tbody>
              <tr>
                <td className="bg-gray-100 font-bold px-2 py-1.5 w-[130px] border border-gray-300">NÚMERO OS</td>
                <td className="px-2 py-1.5 border border-gray-300">{formData.os_number}</td>
                <td className="bg-gray-100 font-bold px-2 py-1.5 w-[140px] border border-gray-300">ASSISTÊNCIA TÉC.</td>
                <td className="px-2 py-1.5 border border-gray-300">MASTERMAQ</td>
              </tr>
              <tr>
                <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">NOME DO CLIENTE</td>
                <td colSpan={3} className="px-2 py-1.5 border border-gray-300">{formData.customer_name}</td>
              </tr>
              <tr>
                <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">MODELO DO PROD.</td>
                <td className="px-2 py-1.5 border border-gray-300">{formData.model}</td>
                <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">Nº DE SERIE</td>
                <td className="px-2 py-1.5 border border-gray-300">{formData.serial_number}</td>
              </tr>
              <tr>
                <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">ART ou Batch</td>
                <td colSpan={3} className="px-2 py-1.5 border border-gray-300">{formData.batch}</td>
              </tr>
            </tbody>
          </table>
          <div className="p-2 border-x border-gray-300">
            <div className="grid grid-cols-2 gap-2">
              {RECALL_PHOTO_LABELS.map((label, i) => (
                <div key={i} className="border border-gray-300 rounded overflow-hidden">
                  <div className="text-white text-[9px] px-2 py-0.5 font-medium" style={{backgroundColor:'#c0392b'}}>{label}</div>
                  {images[i] ? (
                    <img src={images[i]} alt={label} className="w-full h-[70px] object-cover" />
                  ) : (
                    <div className="w-full h-[70px] bg-white"></div>
                  )}
                </div>
              ))}
            </div>
          </div>
          <table className="w-full border-collapse text-[11px]" style={{borderSpacing:0}}>
            <tbody>
              <tr>
                <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">Anotações Técnicas:</td>
              </tr>
              <tr>
                <td className="px-2 py-2 border border-gray-300 min-h-[30px]" style={{whiteSpace:'pre-wrap'}}>
                  <span className="font-bold">Observações técnicas:</span> {finalData.technical_notes || ''}
                </td>
              </tr>
              <tr>
                <td className="px-2 py-1.5 border border-gray-300">{finalData.final_status || ''}</td>
              </tr>
            </tbody>
          </table>
          <div className="px-3 py-3 border-x border-b border-gray-300 rounded-b text-center">
            <div className="text-[11px]">
              {finalData.location}{finalData.date ? `, ${finalData.date}` : ''}
            </div>
            <div className="text-[10px] text-gray-500 mt-1">Data de emissão do Laudo: {new Date().toLocaleDateString('pt-BR')}</div>
            <div className="mt-6 border-t border-gray-400 w-48 mx-auto pt-1">
              <div className="text-[11px] font-semibold">{finalData.technician || ''}</div>
              <div className="text-[9px] text-gray-500">Técnico Responsável</div>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="bg-white border border-gray-300 rounded" data-testid="laudo-preview" style={{fontSize:'11px'}}>
        {/* Header bar - matches DOCX header */}
        <div className="bg-[#1a2744] text-white px-4 py-2 flex justify-between items-center rounded-t">
          <span className="font-bold text-xs">Relatório de Atendimento ao Cliente</span>
          <span className="text-[10px] opacity-80">MASTERMAQ ASSISTÊNCIA TÉCNICA</span>
        </div>

        {/* Table 0: Header Info - exact match to DOCX */}
        <table className="w-full border-collapse text-[11px]" style={{borderSpacing:0}}>
          <tbody>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 w-[130px] border border-gray-300">NÚMERO OS</td>
              <td className="px-2 py-1.5 border border-gray-300">{formData.os_number}</td>
              <td className="bg-gray-100 font-bold px-2 py-1.5 w-[140px] border border-gray-300">ASSISTÊNCIA TÉC.</td>
              <td className="px-2 py-1.5 border border-gray-300">MASTERMAQ</td>
            </tr>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">NOME DO CLIENTE</td>
              <td colSpan={3} className="px-2 py-1.5 border border-gray-300">{formData.customer_name}</td>
            </tr>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">MODELO DO PROD.</td>
              <td className="px-2 py-1.5 border border-gray-300">{formData.model}</td>
              <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">Nº DE SERIE</td>
              <td className="px-2 py-1.5 border border-gray-300">{formData.serial_number}</td>
            </tr>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">ART ou Batch</td>
              <td className="px-2 py-1.5 border border-gray-300">{formData.batch}</td>
              <td colSpan={2} className="px-2 py-1.5 border border-gray-300 text-center text-[10px]">{brandDisplay}</td>
            </tr>
          </tbody>
        </table>

        {/* Table 1: Defect Info - exact match to DOCX */}
        <table className="w-full border-collapse text-[11px]" style={{borderSpacing:0}}>
          <tbody>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 w-[180px] border border-gray-300 align-top">DEFEITO RELATADO PELO CLIENTE *</td>
              <td className="px-2 py-1.5 border border-gray-300">{formData.reported_defect || ''}</td>
            </tr>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300 align-top">DIAGNÓSTICO TÉCNICO *</td>
              <td className="px-2 py-1.5 border border-gray-300">{formData.technical_diagnosis || ''}</td>
            </tr>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">INSTALAÇÃO CORRETA? *</td>
              <td className="px-2 py-1.5 border border-gray-300">{formData.installation_correct || ''}</td>
            </tr>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">PEÇAS NECESSÁRIAS PARA REPARO *</td>
              <td className="px-2 py-1.5 border border-gray-300">{formData.required_parts || ''}</td>
            </tr>
          </tbody>
        </table>

        {/* Photo Grid - matches DOCX VML frame layout */}
        <div className="p-2 border-x border-gray-300">
          <div className="grid grid-cols-2 gap-2">
            {PHOTO_LABELS.map((label, i) => (
              <div key={i} className="border border-gray-300 rounded overflow-hidden">
                <div className="text-white text-[9px] px-2 py-0.5 font-medium" style={{backgroundColor:'#00b9ab'}}>{label}</div>
                {images[i] ? (
                  <img src={images[i]} alt={label} className="w-full h-[70px] object-cover" />
                ) : (
                  <div className="w-full h-[70px] bg-white"></div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Voltage */}
        <div className="px-3 py-2 border border-gray-300">
          <div className="font-bold text-[11px] mb-1">Detalhamento da Tensão de Alimentação do Produto:</div>
          {(finalData.voltage_f1f2 || finalData.voltage_f1_terra || finalData.voltage_f2_terra) ? (
            <div className="text-[11px] text-center">
              F1+F2: {finalData.voltage_f1f2}V &nbsp;&nbsp;|&nbsp;&nbsp; F1+Terra: {finalData.voltage_f1_terra}V &nbsp;&nbsp;|&nbsp;&nbsp; F2+Terra: {finalData.voltage_f2_terra}V
            </div>
          ) : (
            <div className="h-[20px]"></div>
          )}
        </div>

        {/* Technical Notes - matches DOCX Table 2 */}
        <table className="w-full border-collapse text-[11px]" style={{borderSpacing:0}}>
          <tbody>
            <tr>
              <td className="bg-gray-100 font-bold px-2 py-1.5 border border-gray-300">Anotações Técnicas:</td>
            </tr>
            <tr>
              <td className="px-2 py-2 border border-gray-300 min-h-[30px]" style={{whiteSpace:'pre-wrap'}}>
                <span className="font-bold">Observações técnicas:</span>  {finalData.technical_notes || ''}
              </td>
            </tr>
            <tr>
              <td className="px-2 py-1.5 border border-gray-300">{finalData.final_status || ''}</td>
            </tr>
          </tbody>
        </table>

        {/* Footer */}
        <div className="px-3 py-3 border-x border-b border-gray-300 rounded-b text-center">
          <div className="text-[11px]">
            {finalData.location}{finalData.date ? `, ${finalData.date}` : ''}
          </div>
          <div className="mt-6 border-t border-gray-400 w-48 mx-auto pt-1">
            <div className="text-[11px] font-semibold">{finalData.technician || ''}</div>
            <div className="text-[9px] text-gray-500">Técnico Responsável</div>
          </div>
        </div>

        {/* History */}
        {laudoHistory.length > 0 && (
          <div className="bg-gray-50 px-3 py-2 border-x border-b border-gray-300 rounded-b">
            <div className="flex items-center gap-1.5 text-[10px] text-gray-500 font-medium mb-1">
              <Clock size={12} /> Histórico de gerações ({laudoHistory.length})
            </div>
            {laudoHistory.slice(0, 5).map((h, i) => (
              <div key={i} className="text-[9px] text-gray-400">
                {new Date(h.generated_at).toLocaleDateString('pt-BR')} {new Date(h.generated_at).toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit'})}
                {h.technician ? ` - ${h.technician}` : ''}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // Type selector render
  const renderTypeSelector = () => (
    <div className="flex flex-col items-center justify-center py-8 px-4 space-y-6">
      <h2 className="text-lg font-bold text-gray-800">Selecionar Tipo de Laudo</h2>
      <p className="text-sm text-gray-500 text-center">Escolha o tipo de laudo técnico para a OS #{order?.os_number}</p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full max-w-2xl">
        <button
          onClick={() => setLaudoType('hisense')}
          className="flex flex-col items-center gap-3 p-6 border-2 border-gray-200 rounded-xl hover:border-blue-500 hover:bg-blue-50 transition-all group"
          data-testid="laudo-type-hisense"
        >
          <div className="w-12 h-12 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center group-hover:bg-blue-200 transition-colors">
            <Download size={20} />
          </div>
          <span className="font-semibold text-sm text-gray-800">Laudo Hisense</span>
          <span className="text-[10px] text-gray-400 text-center">Padrão com 8 fotos, diagnóstico completo</span>
        </button>
        <button
          onClick={() => setLaudoType('recall')}
          className="flex flex-col items-center gap-3 p-6 border-2 border-gray-200 rounded-xl hover:border-red-500 hover:bg-red-50 transition-all group"
          data-testid="laudo-type-recall"
        >
          <div className="w-12 h-12 rounded-full bg-red-100 text-red-600 flex items-center justify-center group-hover:bg-red-200 transition-colors">
            <Eye size={20} />
          </div>
          <span className="font-semibold text-sm text-gray-800">Laudo Hisense Recall</span>
          <span className="text-[10px] text-gray-400 text-center">Inspeção Recall com 7 fotos específicas</span>
        </button>
        <button
          onClick={() => setLaudoType('mastermaq')}
          className="flex flex-col items-center gap-3 p-6 border-2 border-gray-200 rounded-xl hover:border-emerald-500 hover:bg-emerald-50 transition-all group"
          data-testid="laudo-type-mastermaq"
        >
          <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center group-hover:bg-emerald-200 transition-colors">
            <Download size={20} />
          </div>
          <span className="font-semibold text-sm text-gray-800">Laudo Mastermaq</span>
          <span className="text-[10px] text-gray-400 text-center">Sem série/lote/tensão, 1 foto (defeito)</span>
        </button>
      </div>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) flushAndClose(); }}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col overflow-hidden" aria-describedby="laudo-description" data-overlay="true">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="text-base font-bold text-center" data-testid="laudo-modal-title">
            {!laudoType ? 'Gerar Laudo Técnico' : 
             currentStep === 4 ? 'Pré-visualização do Laudo' : 
             `${isRecall ? 'Laudo Recall' : 'Laudo Técnico'} - OS #${formData.os_number}`}
          </DialogTitle>
        </DialogHeader>

        {!laudoType ? (
          renderTypeSelector()
        ) : (
          <>
            <StepIndicator currentStep={currentStep} />

        <div className="overflow-y-auto flex-1 min-h-0 px-1" data-testid="laudo-step-content">
          {currentStep === 1 && renderStep1()}
          {currentStep === 2 && renderStep2()}
          {currentStep === 3 && renderStep3()}
          {currentStep === 4 && renderPreview()}
        </div>

        <div className="flex justify-between items-center pt-2 border-t flex-shrink-0" data-testid="laudo-navigation">
          <div className="flex items-center gap-3">
            {currentStep > 1 && (
              <Button variant="outline" size="sm" onClick={() => setCurrentStep(currentStep - 1)} data-testid="laudo-back-btn">
                <ChevronLeft size={14} className="mr-1" /> Voltar
              </Button>
            )}
            <span className="text-xs text-gray-400 flex items-center gap-1" data-testid="laudo-autosave-indicator">
              {autoSaving ? (<><Loader2 size={12} className="animate-spin" /> Salvando…</>)
                : lastSavedAt ? (
                  <>
                    <Check size={12} className={savedAgoMinutes <= 2 ? 'text-green-500' : 'text-amber-500'} />
                    <span data-testid="laudo-saved-ago">
                      Salvo há {savedAgoMinutes === 0 ? 'menos de 1 min' : `${savedAgoMinutes} min`}
                    </span>
                  </>
                )
                : null}
            </span>
          </div>
          
          <div className="flex gap-2">
            {currentStep < 4 && (
              <Button variant="outline" size="sm" onClick={saveDraft} disabled={isSaving} data-testid="laudo-save-btn">
                {isSaving ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Save size={14} className="mr-1" />}
                Salvar Rascunho
              </Button>
            )}

            {currentStep < 3 ? (
              <Button size="sm" onClick={() => setCurrentStep(currentStep + 1)} data-testid="laudo-next-btn">
                Avançar <ChevronRight size={14} className="ml-1" />
              </Button>
            ) : currentStep === 3 ? (
              <Button size="sm" onClick={() => setCurrentStep(4)} className="bg-indigo-600 hover:bg-indigo-700" data-testid="laudo-preview-btn">
                <Eye size={14} className="mr-1" /> Pré-visualizar
              </Button>
            ) : (
              <>
              {digitalLink && (
                <a href={digitalLink} target="_blank" rel="noreferrer" className="text-xs underline text-blue-700 self-center" data-testid="laudo-digital-link">Abrir laudo digital</a>
              )}
              <Button size="sm" onClick={generateLaudo} disabled={isGenerating}
                className="bg-blue-600 hover:bg-blue-700" data-testid="laudo-generate-btn">
                {isGenerating ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Download size={14} className="mr-1" />}
                {laudoType === 'mastermaq' ? 'Gerar Laudo Digital (PDF)' : 'Gerar Laudo DOCX'}
              </Button>
              </>
            )}
          </div>
        </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default LaudoModal;
