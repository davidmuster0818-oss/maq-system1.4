/**
 * LabelTemplatesPage — editor visual de adesivos térmicos (fabric.js).
 *
 * Permite criar/editar templates de adesivos com:
 *  - Tamanho configurável (mm)
 *  - Elementos: texto, imagem, QR code (placeholder), retângulos
 *  - Save/Load via /api/label-templates
 *  - Preview WYSIWYG + impressão
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { fabric } from 'fabric';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import DashboardLayout from '../components/DashboardLayout';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { Save, Trash2, Type, Image as ImageIcon, Square, QrCode, Plus, FileText, Loader2, Printer } from 'lucide-react';
import QRCode from 'qrcode';
import { printCustomLabel } from '../utils/printingService';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const DPI = 96 / 25.4; // px per mm

const PRESETS = [
  { name: '50×30 mm', w: 50, h: 30 },
  { name: '80×50 mm', w: 80, h: 50 },
  { name: '100×50 mm', w: 100, h: 50 },
];

export default function LabelTemplatesPage() {
  const { getAuthHeader, isAdmin } = useAuth();
  const canvasRef = useRef(null);
  const fabricRef = useRef(null);
  const [templates, setTemplates] = useState([]);
  const [active, setActive] = useState(null);
  const [name, setName] = useState('Novo template');
  const [size, setSize] = useState({ w: 50, h: 30 });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadList = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/label-templates`, getAuthHeader());
      setTemplates(res.data || []);
    } catch (_) {}
    finally { setLoading(false); }
  }, [getAuthHeader]);

  useEffect(() => { loadList(); }, [loadList]);

  // Init fabric canvas once
  useEffect(() => {
    if (!canvasRef.current || fabricRef.current) return;
    const c = new fabric.Canvas(canvasRef.current, {
      width: size.w * DPI, height: size.h * DPI,
      backgroundColor: '#ffffff', preserveObjectStacking: true,
    });
    fabricRef.current = c;
    return () => { c.dispose(); fabricRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Resize canvas when size changes
  useEffect(() => {
    if (!fabricRef.current) return;
    fabricRef.current.setDimensions({ width: size.w * DPI, height: size.h * DPI });
    fabricRef.current.renderAll();
  }, [size]);

  const loadTemplate = (tpl) => {
    setActive(tpl);
    setName(tpl.name);
    setSize({ w: tpl.width_mm, h: tpl.height_mm });
    if (fabricRef.current && tpl.canvas_json) {
      fabricRef.current.loadFromJSON(tpl.canvas_json, () => {
        fabricRef.current.renderAll();
      });
    }
  };

  const addText = () => {
    if (!fabricRef.current) return;
    const t = new fabric.IText('Texto', { left: 20, top: 20, fontSize: 18, fontFamily: 'Arial, sans-serif', fill: '#000' });
    fabricRef.current.add(t).setActiveObject(t);
  };

  const addRect = () => {
    if (!fabricRef.current) return;
    const r = new fabric.Rect({ left: 20, top: 60, width: 80, height: 30, fill: 'transparent', stroke: '#000', strokeWidth: 2 });
    fabricRef.current.add(r).setActiveObject(r);
  };

  const addImage = () => {
    const url = window.prompt('URL da imagem (ou /assets/...)', '/assets/mastermaq-logo.png');
    if (!url) return;
    fabric.Image.fromURL(url, (img) => {
      img.scaleToWidth(80);
      img.set({ left: 20, top: 20 });
      fabricRef.current.add(img).setActiveObject(img);
    }, { crossOrigin: 'anonymous' });
  };

  const addQR = async () => {
    const payload = window.prompt('Conteúdo do QR (use {{os_number}} para placeholder dinâmico)', '{{os_number}}');
    if (!payload) return;
    try {
      const dataUrl = await QRCode.toDataURL(payload, { margin: 0, width: 200 });
      fabric.Image.fromURL(dataUrl, (img) => {
        img.scaleToWidth(80);
        img.set({ left: size.w * DPI - 90, top: 10, qrPayload: payload, isPlaceholder: true });
        fabricRef.current.add(img).setActiveObject(img);
      });
    } catch (e) {
      toast.error('Erro ao gerar QR');
    }
  };

  const deleteSelected = () => {
    const o = fabricRef.current?.getActiveObject();
    if (o) { fabricRef.current.remove(o); fabricRef.current.discardActiveObject(); fabricRef.current.renderAll(); }
  };

  const save = async () => {
    if (!fabricRef.current) return;
    if (!name.trim()) { toast.error('Nome obrigatório'); return; }
    setSaving(true);
    try {
      const canvas_json = fabricRef.current.toJSON(['qrPayload', 'isPlaceholder']);
      const body = { name: name.trim(), width_mm: size.w, height_mm: size.h, canvas_json, scope: 'global' };
      if (active?.id) {
        await axios.put(`${API}/label-templates/${active.id}`, body, getAuthHeader());
        toast.success('Template atualizado');
      } else {
        const res = await axios.post(`${API}/label-templates`, body, getAuthHeader());
        setActive(res.data);
        toast.success('Template criado');
      }
      loadList();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha ao salvar');
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!active?.id) return;
    if (!window.confirm(`Excluir "${active.name}"?`)) return;
    try {
      await axios.delete(`${API}/label-templates/${active.id}`, getAuthHeader());
      setActive(null); setName('Novo template');
      fabricRef.current?.clear();
      loadList();
    } catch (_) {}
  };

  const print = () => {
    if (!fabricRef.current) return;
    // PNG em 3x pra manter nitidez no papel térmico (~305 DPI).
    const png = fabricRef.current.toDataURL({ format: 'png', multiplier: 3 });
    // Mapa: tamanhos do editor → sizeKey do motor de impressão (SIZES em printingService).
    // 50×30 → bobina 58mm com 4mm de liner (mesmo do adesivo de OS/Produto).
    // 80×50 e 100×50 → paper = content (sem liner).
    // Tamanhos custom → paperW/paperH = w/h do template, sem liner.
    let sizeKey = null;
    if (size.w === 50 && size.h === 30) sizeKey = '50x30';
    else if (size.w === 30 && size.h === 50) sizeKey = '50x30-portrait';
    else if (size.w === 80 && size.h === 50) sizeKey = '80x50';
    else if (size.w === 100 && size.h === 50) sizeKey = '100x50';
    printCustomLabel(png, {
      sizeKey,
      customContent: sizeKey ? null : { w: size.w, h: size.h },
      name: name || 'Adesivo',
    });
  };

  const newTemplate = () => {
    setActive(null); setName('Novo template');
    fabricRef.current?.clear();
    fabricRef.current?.setBackgroundColor('#fff', () => fabricRef.current.renderAll());
  };

  if (!isAdmin) {
    return <DashboardLayout><div className="p-6 text-center text-gray-500">Apenas administradores podem editar templates.</div></DashboardLayout>;
  }

  return (
    <DashboardLayout>
      <div className="space-y-4" data-testid="label-templates-page">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-gray-600" />
            <h2 className="text-xl font-semibold">Templates de Adesivo</h2>
          </div>
          <Button onClick={newTemplate} className="gap-2" data-testid="label-new-btn">
            <Plus className="h-4 w-4" /> Novo Template
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4">
          {/* Sidebar: list of templates */}
          <aside className="bg-white border rounded-lg p-3 space-y-2 max-h-[70vh] overflow-auto">
            <h3 className="text-xs uppercase tracking-wide text-gray-500 px-2">Salvos</h3>
            {loading ? <div className="p-4 text-center"><Loader2 className="h-4 w-4 animate-spin inline" /></div> : templates.length === 0 ? (
              <p className="text-xs text-gray-400 px-2">Nenhum template salvo ainda.</p>
            ) : templates.map(t => (
              <button key={t.id}
                onClick={() => loadTemplate(t)}
                className={`w-full text-left px-2 py-1.5 rounded text-sm hover:bg-gray-100 ${active?.id === t.id ? 'bg-blue-50 text-blue-700' : ''}`}
                data-testid={`label-tpl-${t.id}`}
              >
                <div className="font-medium truncate">{t.name}</div>
                <div className="text-[10px] text-gray-500">{t.width_mm}×{t.height_mm}mm</div>
              </button>
            ))}
          </aside>

          {/* Editor */}
          <main className="bg-white border rounded-lg p-4 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Nome do template</Label>
                <Input value={name} onChange={e => setName(e.target.value)} data-testid="label-name-input" />
              </div>
              <div>
                <Label className="text-xs">Largura (mm)</Label>
                <Input type="number" value={size.w} onChange={e => setSize(s => ({ ...s, w: Math.max(10, Number(e.target.value) || 50) }))} />
              </div>
              <div>
                <Label className="text-xs">Altura (mm)</Label>
                <Input type="number" value={size.h} onChange={e => setSize(s => ({ ...s, h: Math.max(10, Number(e.target.value) || 30) }))} />
              </div>
            </div>

            <div className="flex gap-1 flex-wrap">
              {PRESETS.map(p => (
                <Button key={p.name} size="sm" variant="outline" onClick={() => setSize({ w: p.w, h: p.h })} className="text-xs">
                  {p.name}
                </Button>
              ))}
            </div>

            <div className="flex flex-wrap gap-2 border-t pt-3">
              <Button size="sm" variant="outline" onClick={addText} className="gap-1" data-testid="label-add-text"><Type className="h-3.5 w-3.5" /> Texto</Button>
              <Button size="sm" variant="outline" onClick={addImage} className="gap-1"><ImageIcon className="h-3.5 w-3.5" /> Imagem</Button>
              <Button size="sm" variant="outline" onClick={addRect} className="gap-1"><Square className="h-3.5 w-3.5" /> Retângulo</Button>
              <Button size="sm" variant="outline" onClick={addQR} className="gap-1"><QrCode className="h-3.5 w-3.5" /> QR Code</Button>
              <Button size="sm" variant="outline" onClick={deleteSelected} className="gap-1 text-red-600"><Trash2 className="h-3.5 w-3.5" /> Apagar</Button>
            </div>

            <div className="bg-gray-100 p-4 rounded flex items-center justify-center overflow-auto">
              <div style={{ background: '#fff', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}>
                <canvas ref={canvasRef} />
              </div>
            </div>

            <div className="flex gap-2 justify-end border-t pt-3">
              {active?.id && (
                <Button variant="outline" onClick={remove} className="gap-2 text-red-600"><Trash2 className="h-4 w-4" /> Excluir</Button>
              )}
              <Button variant="outline" onClick={print} className="gap-2"><Printer className="h-4 w-4" /> Imprimir Preview</Button>
              <Button onClick={save} disabled={saving} className="gap-2" data-testid="label-save-btn">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Salvar
              </Button>
            </div>
          </main>
        </div>
      </div>
    </DashboardLayout>
  );
}
