import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import DashboardLayout from '../components/DashboardLayout';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { toast } from 'sonner';
import { Plus, Pencil, Trash2, Loader2, Users as UsersIcon, ShieldCheck, Eye, EyeOff } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const PAGES = [
  ['service-orders', 'Ordens de Serviço'], ['routes', 'Roteiros'], ['inventory', 'Estoque'], ['financial', 'Financeiro'],
  ['manuais', 'Manuais'], ['mi', 'Mi'], ['whatsapp', 'WhatsApp API'], ['users', 'Usuários'], ['webhooks', 'Webhooks'], ['labels', 'Adesivos'],
];
const ROLE_PAGES = {
  admin: PAGES.map(([k]) => k), technician: ['routes', 'manuais'], invisacook: ['service-orders'],
};

const emptyForm = { name: '', email: '', password: '', phone: '', role: 'technician', active: true, pages: ROLE_PAGES.technician };

function PagesPicker({ form, setForm }) {
  const locked = form.role === 'invisacook';
  const toggle = (k) => setForm(f => ({ ...f, pages: f.pages.includes(k) ? f.pages.filter(p => p !== k) : [...f.pages, k] }));
  return (
    <div data-testid="user-form-pages">
      <Label>Páginas com acesso</Label>
      <div className="grid grid-cols-2 gap-1.5 mt-1.5">
        {PAGES.map(([k, label]) => {
          const disabled = locked || (k === 'users' && form.role !== 'admin');
          return (
            <label key={k} className={`flex items-center gap-2 text-sm rounded-md border px-2 py-1.5 ${disabled ? 'opacity-50' : 'cursor-pointer hover:bg-gray-50'}`}>
              <input type="checkbox" checked={form.pages.includes(k)} disabled={disabled} onChange={() => toggle(k)} data-testid={`user-page-${k}`} />
              {label}
            </label>
          );
        })}
      </div>
      <p className="text-[11px] text-gray-500 mt-1">{locked ? 'Invisacook acessa somente as próprias OSs.' : 'Usuários só pode ser liberado para Admin. O bloqueio vale também no servidor.'}</p>
    </div>
  );
}

export default function UsersPage() {
  const { getAuthHeader } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [showPwd, setShowPwd] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/users`, getAuthHeader());
      setUsers(data || []);
    } catch (e) {
      toast.error('Falha ao carregar usuários');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeader]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditing(null); setShowPwd(false); setForm(emptyForm); setOpen(true); };
  const openEdit = (u) => {
    setEditing(u);
    setShowPwd(true);
    setForm({ name: u.name || '', email: u.email || '', password: u.password || '', phone: u.phone || '', role: u.role || 'technician', active: !!u.active, pages: u.pages || ROLE_PAGES[u.role] || [] });
    setOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email) { toast.error('Nome e email são obrigatórios'); return; }
    if (!editing && !form.password) { toast.error('Defina uma senha para o novo usuário'); return; }

    setSaving(true);
    try {
      if (editing) {
        const body = { ...form };
        if (!body.password || body.password === (editing.password || '')) delete body.password;
        await axios.put(`${API}/users/${editing.id}`, body, getAuthHeader());
        toast.success('Usuário atualizado');
      } else {
        await axios.post(`${API}/users`, form, getAuthHeader());
        toast.success('Usuário criado');
      }
      setOpen(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha ao salvar');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (u) => {
    if (!window.confirm(`Excluir ${u.name} (${u.email})?`)) return;
    try {
      await axios.delete(`${API}/users/${u.id}`, getAuthHeader());
      toast.success('Usuário excluído');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha ao excluir');
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-4" data-testid="users-page">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <UsersIcon className="h-5 w-5 text-gray-600" />
            <h2 className="text-xl font-semibold">Gestão de Usuários</h2>
            <Badge variant="outline">{users.length}</Badge>
          </div>
          <Button onClick={openCreate} className="gap-2" data-testid="add-user-btn">
            <Plus className="h-4 w-4" /> Novo Usuário
          </Button>
        </div>

        <div className="rounded-lg border bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 border-b">
              <tr>
                <th className="text-left p-3">Nome</th>
                <th className="text-left p-3">Email</th>
                <th className="text-left p-3">Telefone</th>
                <th className="text-left p-3">Função</th>
                <th className="text-left p-3">Status</th>
                <th className="text-right p-3">Ações</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="p-8 text-center text-gray-500"><Loader2 className="h-5 w-5 animate-spin inline mr-2" />Carregando...</td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan={6} className="p-8 text-center text-gray-500">Nenhum usuário cadastrado</td></tr>
              ) : users.map(u => (
                <tr key={u.id} className="border-b last:border-0 hover:bg-gray-50" data-testid={`user-row-${u.email}`}>
                  <td className="p-3 font-medium flex items-center gap-2">
                    {u.role === 'admin' && <ShieldCheck className="h-4 w-4 text-blue-600" />}
                    {u.name}
                  </td>
                  <td className="p-3 text-gray-600">{u.email}</td>
                  <td className="p-3 text-gray-600">{u.phone || '—'}</td>
                  <td className="p-3">
                    <Badge className={u.role === 'admin' ? 'bg-blue-100 text-blue-700 hover:bg-blue-100' : u.role === 'invisacook' ? 'bg-orange-100 text-orange-700 hover:bg-orange-100' : 'bg-amber-100 text-amber-700 hover:bg-amber-100'}>
                      {u.role === 'admin' ? 'Admin' : u.role === 'invisacook' ? 'Invisacook' : 'Técnico'}
                    </Badge>
                  </td>
                  <td className="p-3">
                    {u.active ? <Badge className="bg-green-100 text-green-700 hover:bg-green-100">Ativo</Badge> : <Badge variant="secondary">Inativo</Badge>}
                  </td>
                  <td className="p-3 text-right space-x-1">
                    <Button size="sm" variant="ghost" onClick={() => openEdit(u)} data-testid={`edit-user-${u.email}`}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost" className="text-red-600 hover:text-red-700" onClick={() => handleDelete(u)} data-testid={`delete-user-${u.email}`}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md max-h-[90dvh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? 'Editar Usuário' : 'Novo Usuário'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <Label>Nome</Label>
              <Input value={form.name} onChange={e => setForm({...form, name: e.target.value})} data-testid="user-form-name" />
            </div>
            <div>
              <Label>Email</Label>
              <Input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} data-testid="user-form-email" />
            </div>
            <div>
              <Label>Senha</Label>
              <div className="relative">
                <Input type={showPwd ? 'text' : 'password'} value={form.password} onChange={e => setForm({...form, password: e.target.value})} className="pr-10" placeholder={editing && !editing.password ? 'Senha antiga não registrada — defina uma nova' : ''} data-testid="user-form-password" />
                <button type="button" onClick={() => setShowPwd(v => !v)} aria-label={showPwd ? 'Ocultar senha' : 'Mostrar senha'}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-800" data-testid="user-form-password-toggle">
                  {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div>
              <Label>Telefone</Label>
              <Input value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} placeholder="31999999999" data-testid="user-form-phone" />
            </div>
            <div>
              <Label>Função</Label>
              <select
                className="w-full h-10 px-3 border rounded-md text-sm"
                value={form.role}
                onChange={e => setForm({...form, role: e.target.value, pages: ROLE_PAGES[e.target.value]})}
                data-testid="user-form-role"
              >
                <option value="technician">Técnico</option>
                <option value="admin">Admin</option>
                <option value="invisacook">Invisacook (somente OSs Invisacook)</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={form.active} onCheckedChange={v => setForm({...form, active: v})} data-testid="user-form-active" />
              <Label>Usuário ativo</Label>
            </div>
            <PagesPicker form={form} setForm={setForm} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
              <Button type="submit" disabled={saving} data-testid="user-form-save">
                {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
                {editing ? 'Salvar' : 'Criar'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
}
