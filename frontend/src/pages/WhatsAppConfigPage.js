import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import DashboardLayout from '../components/DashboardLayout';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import {
  MessageCircle,
  Settings,
  Send,
  CheckCircle,
  AlertCircle,
  Loader2,
  Phone,
  Shield,
  Link2,
  Eye,
  EyeOff,
  RefreshCw,
  Clock,
  ArrowUpRight,
  Copy,
  Webhook
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function WhatsAppConfigPage() {
  const { token } = useAuth();
  const getAuth = () => ({ headers: { Authorization: `Bearer ${token}` } });

  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showToken, setShowToken] = useState(false);

  // Form fields
  const [accessToken, setAccessToken] = useState('');
  const [phoneNumberId, setPhoneNumberId] = useState('');
  const [wabaId, setWabaId] = useState('');
  const [webhookVerifyToken, setWebhookVerifyToken] = useState('mastermaq_wh_verify_2024');
  const [displayPhone, setDisplayPhone] = useState('');

  // Phone info
  const [phoneInfo, setPhoneInfo] = useState(null);
  const [loadingPhoneInfo, setLoadingPhoneInfo] = useState(false);

  // Webhook status
  const [webhookStatus, setWebhookStatus] = useState(null);

  // Test message
  const [testTo, setTestTo] = useState('');
  const [testMsg, setTestMsg] = useState('');
  const [sending, setSending] = useState(false);

  // Menu interativo
  const [menuConfig, setMenuConfig] = useState(null);
  const [loadingMenu, setLoadingMenu] = useState(false);
  const [savingMenu, setSavingMenu] = useState(false);
  const [menuRepName, setMenuRepName] = useState('Thamires');
  const [menuBrand, setMenuBrand] = useState('Posto Autorizado');
  const [menuBtnLabels, setMenuBtnLabels] = useState(['Enviar dados', 'Tirar duvidas', 'Falar com atendente']);
  const [menuDuvidasMsg, setMenuDuvidasMsg] = useState('');
  const [menuAtendenteMsg, setMenuAtendenteMsg] = useState('');
  const [menuSendTo, setMenuSendTo] = useState('');
  const [menuSendBrand, setMenuSendBrand] = useState('');
  const [sendingMenu, setSendingMenu] = useState(false);

  // Messages
  const [messages, setMessages] = useState([]);
  const [loadingMessages, setLoadingMessages] = useState(false);

  const fetchMenuConfig = useCallback(async () => {
    try {
      setLoadingMenu(true);
      const res = await axios.get(`${API}/whatsapp/menu-config`, getAuth());
      const d = res.data;
      setMenuConfig(d);
      setMenuRepName(d.representative_name || 'Thamires');
      setMenuBrand(d.default_brand || 'Posto Autorizado');
      setMenuDuvidasMsg(d.duvidas_message || '');
      setMenuAtendenteMsg(d.atendente_message || '');
      if (d.buttons && d.buttons.length > 0) {
        setMenuBtnLabels(d.buttons.map(b => b.title));
      }
    } catch {}
    finally { setLoadingMenu(false); }
  }, [token]);

  useEffect(() => { if (token) fetchMenuConfig(); }, [fetchMenuConfig]);

  const handleSaveMenu = async () => {
    setSavingMenu(true);
    try {
      const buttons = [
        { id: 'enviar_dados', title: menuBtnLabels[0] || 'Enviar dados' },
        { id: 'duvidas', title: menuBtnLabels[1] || 'Tirar duvidas' },
        { id: 'atendente', title: menuBtnLabels[2] || 'Falar com atendente' }
      ];
      await axios.post(`${API}/whatsapp/menu-config`, {
        representative_name: menuRepName,
        default_brand: menuBrand,
        buttons,
        duvidas_message: menuDuvidasMsg,
        atendente_message: menuAtendenteMsg,
      }, getAuth());
      toast.success('Configuracao do menu salva!');
      fetchMenuConfig();
    } catch (e) {
      toast.error('Erro ao salvar menu');
    } finally { setSavingMenu(false); }
  };

  const handleSendMenu = async () => {
    if (!menuSendTo) return toast.error('Informe o numero');
    setSendingMenu(true);
    try {
      await axios.post(`${API}/whatsapp/send-menu`, {
        to: menuSendTo,
        brand: menuSendBrand || menuBrand,
      }, getAuth());
      toast.success('Menu enviado!');
    } catch (e) {
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === 'object' ? JSON.stringify(detail) : detail || 'Erro ao enviar menu');
    } finally { setSendingMenu(false); }
  };

  // Templates
  const [templates, setTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/whatsapp/config`, getAuth());
      setConfig(res.data);
      if (res.data.configured) {
        setPhoneNumberId(res.data.phone_number_id || '');
        setWabaId(res.data.waba_id || '');
        setWebhookVerifyToken(res.data.webhook_verify_token || '');
        setDisplayPhone(res.data.display_phone || '');
      }
    } catch { /* not configured */ }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  useEffect(() => {
    if (token) {
      axios.get(`${API}/whatsapp/webhook-status`, getAuth())
        .then(res => setWebhookStatus(res.data))
        .catch(() => {});
    }
  }, [token, config]);

  const handleSave = async () => {
    if (!accessToken && !config?.configured) {
      toast.error('Token de acesso obrigatório');
      return;
    }
    if (!phoneNumberId) {
      toast.error('Phone Number ID obrigatório');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        phone_number_id: phoneNumberId,
        waba_id: wabaId,
        webhook_verify_token: webhookVerifyToken,
        display_phone: displayPhone,
      };
      if (accessToken) payload.access_token = accessToken;
      else if (config?.access_token) payload.access_token = config.access_token;

      await axios.post(`${API}/whatsapp/config`, payload, getAuth());
      toast.success('Configuração salva!');
      setAccessToken('');
      fetchConfig();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao salvar');
    } finally { setSaving(false); }
  };

  const fetchPhoneInfo = async () => {
    setLoadingPhoneInfo(true);
    try {
      const res = await axios.get(`${API}/whatsapp/phone-info`, getAuth());
      setPhoneInfo(res.data);
    } catch (err) {
      toast.error('Erro ao buscar info do telefone');
    } finally { setLoadingPhoneInfo(false); }
  };

  const fetchTemplates = async () => {
    setLoadingTemplates(true);
    try {
      const res = await axios.get(`${API}/whatsapp/templates`, getAuth());
      setTemplates(res.data.data || []);
    } catch (err) {
      toast.error('Erro ao buscar templates');
    } finally { setLoadingTemplates(false); }
  };

  const fetchMessages = async () => {
    setLoadingMessages(true);
    try {
      const res = await axios.get(`${API}/whatsapp/messages`, getAuth());
      setMessages(res.data.messages || []);
    } catch { /* ignore */ }
    finally { setLoadingMessages(false); }
  };

  const handleSendTest = async () => {
    if (!testTo || !testMsg) {
      toast.error('Preencha número e mensagem');
      return;
    }
    setSending(true);
    try {
      await axios.post(`${API}/whatsapp/send`, {
        to: testTo,
        type: 'text',
        text: testMsg,
      }, getAuth());
      toast.success('Mensagem enviada!');
      setTestMsg('');
      fetchMessages();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const errorMsg = typeof detail === 'object' ? JSON.stringify(detail) : detail;
      toast.error(`Erro: ${errorMsg || 'Falha ao enviar'}`);
    } finally { setSending(false); }
  };

  const webhookUrl = `${process.env.REACT_APP_BACKEND_URL}/api/whatsapp/webhook`;

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Copiado!');
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex justify-center items-center py-20"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6" data-testid="whatsapp-config-page">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
            <MessageCircle className="h-5 w-5 text-green-600" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">WhatsApp Business API</h1>
            <p className="text-sm text-gray-500">Configuração e gerenciamento</p>
          </div>
          {config?.configured && (
            <Badge className="ml-auto bg-green-100 text-green-700 border-green-200">
              <CheckCircle className="h-3 w-3 mr-1" /> Configurado
            </Badge>
          )}
        </div>

        {/* Configuration Form */}
        <div className="border border-gray-200 rounded-lg p-5 space-y-4" data-testid="whatsapp-config-form">
          <div className="flex items-center gap-2 mb-2">
            <Settings className="h-4 w-4 text-gray-500" />
            <h2 className="font-medium text-sm">Credenciais da API</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2">
              <Label className="text-xs text-gray-600">Token de Acesso (Access Token)</Label>
              <div className="relative">
                <Input
                  type={showToken ? 'text' : 'password'}
                  value={accessToken}
                  onChange={e => setAccessToken(e.target.value)}
                  placeholder={config?.access_token_masked || 'EAAcg0wJbQ4QBQ...'}
                  className="pr-10 font-mono text-xs"
                  data-testid="wa-access-token"
                />
                <button onClick={() => setShowToken(!showToken)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                  {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="text-[10px] text-gray-400 mt-1">
                Obtenha em: Meta Business Suite &gt; Configurações &gt; WhatsApp &gt; API Setup
              </p>
            </div>

            <div>
              <Label className="text-xs text-gray-600">Phone Number ID</Label>
              <Input
                value={phoneNumberId}
                onChange={e => setPhoneNumberId(e.target.value)}
                placeholder="Ex: 106540352242922"
                className="font-mono text-xs"
                data-testid="wa-phone-number-id"
              />
            </div>

            <div>
              <Label className="text-xs text-gray-600">WABA ID (opcional)</Label>
              <Input
                value={wabaId}
                onChange={e => setWabaId(e.target.value)}
                placeholder="WhatsApp Business Account ID"
                className="font-mono text-xs"
                data-testid="wa-waba-id"
              />
            </div>

            <div>
              <Label className="text-xs text-gray-600">Telefone de Exibição</Label>
              <Input
                value={displayPhone}
                onChange={e => setDisplayPhone(e.target.value)}
                placeholder="(31) 3422-5293"
                className="text-xs"
                data-testid="wa-display-phone"
              />
            </div>

            <div>
              <Label className="text-xs text-gray-600">Webhook Verify Token</Label>
              <Input
                value={webhookVerifyToken}
                onChange={e => setWebhookVerifyToken(e.target.value)}
                className="font-mono text-xs"
                data-testid="wa-verify-token"
              />
            </div>
          </div>

          <Button onClick={handleSave} disabled={saving} className="bg-green-600 hover:bg-green-700 text-white" data-testid="wa-save-config">
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <CheckCircle className="h-4 w-4 mr-2" />}
            Salvar Configuração
          </Button>
        </div>

        {/* Webhook Configuration */}
        <div className="border border-gray-200 rounded-lg p-5 space-y-3" data-testid="whatsapp-webhook-section">
          <div className="flex items-center gap-2 mb-1">
            <Webhook className="h-4 w-4 text-gray-500" />
            <h2 className="font-medium text-sm">Configuração de Webhook</h2>
          </div>
          <p className="text-xs text-gray-500">
            Configure estes valores no painel do Meta Developers &gt; WhatsApp &gt; Configuration &gt; Callback URL
          </p>

          {/* Webhook Status Indicators */}
          {webhookStatus && (
            <div className="flex flex-wrap gap-2 py-2">
              <Badge className={`text-[10px] ${webhookStatus.configured ? 'bg-green-100 text-green-700 border-green-200' : 'bg-red-100 text-red-700 border-red-200'}`}>
                {webhookStatus.configured ? <CheckCircle className="h-3 w-3 mr-1" /> : <AlertCircle className="h-3 w-3 mr-1" />}
                API {webhookStatus.configured ? 'Configurada' : 'Pendente'}
              </Badge>
              <Badge className={`text-[10px] ${webhookStatus.app_secret_set ? 'bg-green-100 text-green-700 border-green-200' : 'bg-yellow-100 text-yellow-700 border-yellow-200'}`}>
                <Shield className="h-3 w-3 mr-1" />
                Assinatura {webhookStatus.app_secret_set ? 'Ativa' : 'Desativada'}
              </Badge>
              <Badge className={`text-[10px] ${webhookStatus.verify_token_set ? 'bg-green-100 text-green-700 border-green-200' : 'bg-yellow-100 text-yellow-700 border-yellow-200'}`}>
                <Shield className="h-3 w-3 mr-1" />
                Verify Token {webhookStatus.verify_token_set ? 'OK' : 'Pendente'}
              </Badge>
              {webhookStatus.app_id && (
                <Badge variant="outline" className="text-[10px] text-gray-500">
                  App ID: {webhookStatus.app_id}
                </Badge>
              )}
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label className="text-xs text-gray-600 w-28 flex-shrink-0">Callback URL:</Label>
              <code className="text-xs bg-gray-50 px-3 py-1.5 rounded border border-gray-200 font-mono flex-1 truncate">{webhookUrl}</code>
              <Button variant="ghost" size="sm" onClick={() => copyToClipboard(webhookUrl)} className="flex-shrink-0">
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-gray-600 w-28 flex-shrink-0">Verify Token:</Label>
              <code className="text-xs bg-gray-50 px-3 py-1.5 rounded border border-gray-200 font-mono flex-1">{webhookVerifyToken}</code>
              <Button variant="ghost" size="sm" onClick={() => copyToClipboard(webhookVerifyToken)} className="flex-shrink-0">
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {webhookStatus?.signature_validation && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-800">
              <Shield className="h-3.5 w-3.5 inline mr-1.5" />
              <strong>Validação X-Hub-Signature-256 ativa.</strong> Todas as notificações recebidas são verificadas com HMAC-SHA256 usando o App Secret configurado.
            </div>
          )}

          <p className="text-[10px] text-gray-400">
            Campos de webhook para assinar: messages, message_deliveries, message_reads
          </p>
        </div>

        {/* Phone Info & Status */}
        {config?.configured && (
          <div className="border border-gray-200 rounded-lg p-5 space-y-3" data-testid="whatsapp-phone-info">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Phone className="h-4 w-4 text-gray-500" />
                <h2 className="font-medium text-sm">Status do Número</h2>
              </div>
              <Button variant="outline" size="sm" onClick={fetchPhoneInfo} disabled={loadingPhoneInfo} data-testid="wa-fetch-phone-info">
                {loadingPhoneInfo ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                <span className="ml-1 text-xs">Verificar</span>
              </Button>
            </div>
            {phoneInfo && (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                <div className="bg-gray-50 p-2.5 rounded">
                  <span className="text-gray-400 block">Nome Verificado</span>
                  <span className="font-medium">{phoneInfo.verified_name || '-'}</span>
                </div>
                <div className="bg-gray-50 p-2.5 rounded">
                  <span className="text-gray-400 block">Telefone</span>
                  <span className="font-medium">{phoneInfo.display_phone_number || '-'}</span>
                </div>
                <div className="bg-gray-50 p-2.5 rounded">
                  <span className="text-gray-400 block">Qualidade</span>
                  <Badge variant="outline" className={`text-[10px] ${phoneInfo.quality_rating === 'GREEN' ? 'text-green-600 border-green-300' : phoneInfo.quality_rating === 'YELLOW' ? 'text-yellow-600 border-yellow-300' : 'text-red-600 border-red-300'}`}>
                    {phoneInfo.quality_rating || '-'}
                  </Badge>
                </div>
                <div className="bg-gray-50 p-2.5 rounded">
                  <span className="text-gray-400 block">Plataforma</span>
                  <span className="font-medium">{phoneInfo.platform_type || '-'}</span>
                </div>
                <div className="bg-gray-50 p-2.5 rounded">
                  <span className="text-gray-400 block">Verificação</span>
                  <span className="font-medium">{phoneInfo.code_verification_status || '-'}</span>
                </div>
                <div className="bg-gray-50 p-2.5 rounded">
                  <span className="text-gray-400 block">Throughput</span>
                  <span className="font-medium">{phoneInfo.throughput?.level || '-'}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Test Message */}
        {config?.configured && (
          <div className="border border-gray-200 rounded-lg p-5 space-y-3" data-testid="whatsapp-test-message">
            <div className="flex items-center gap-2 mb-1">
              <Send className="h-4 w-4 text-gray-500" />
              <h2 className="font-medium text-sm">Enviar Mensagem de Teste</h2>
            </div>
            <div className="flex gap-3 flex-wrap">
              <div className="flex-1 min-w-[180px]">
                <Label className="text-xs text-gray-600">Número (com DDD)</Label>
                <Input
                  value={testTo}
                  onChange={e => setTestTo(e.target.value)}
                  placeholder="5531999998888"
                  className="text-xs font-mono"
                  data-testid="wa-test-to"
                />
              </div>
              <div className="flex-[2] min-w-[240px]">
                <Label className="text-xs text-gray-600">Mensagem</Label>
                <Input
                  value={testMsg}
                  onChange={e => setTestMsg(e.target.value)}
                  placeholder="Olá, teste da API WhatsApp Business!"
                  className="text-xs"
                  data-testid="wa-test-msg"
                  onKeyDown={e => e.key === 'Enter' && handleSendTest()}
                />
              </div>
              <div className="flex items-end">
                <Button onClick={handleSendTest} disabled={sending} className="bg-green-600 hover:bg-green-700 text-white h-9" data-testid="wa-send-test">
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <p className="text-[10px] text-gray-400">
              <AlertCircle className="h-3 w-3 inline mr-1" />
              Mensagens de texto só podem ser enviadas dentro da janela de 24h (após o cliente enviar mensagem primeiro). Para iniciar conversa, use um template aprovado.
            </p>
          </div>
        )}

        {/* Templates */}
        {config?.configured && config?.waba_id && (
          <div className="border border-gray-200 rounded-lg p-5 space-y-3" data-testid="whatsapp-templates">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Shield className="h-4 w-4 text-gray-500" />
                <h2 className="font-medium text-sm">Templates de Mensagem</h2>
              </div>
              <Button variant="outline" size="sm" onClick={fetchTemplates} disabled={loadingTemplates} data-testid="wa-fetch-templates">
                {loadingTemplates ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                <span className="ml-1 text-xs">Carregar</span>
              </Button>
            </div>
            {templates.length > 0 && (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {templates.map((t, i) => (
                  <div key={i} className="flex items-center justify-between p-2.5 bg-gray-50 rounded text-xs">
                    <div>
                      <span className="font-medium">{t.name}</span>
                      <span className="text-gray-400 ml-2">({t.language})</span>
                    </div>
                    <Badge variant="outline" className={`text-[10px] ${t.status === 'APPROVED' ? 'text-green-600 border-green-300' : t.status === 'REJECTED' ? 'text-red-600 border-red-300' : 'text-yellow-600 border-yellow-300'}`}>
                      {t.status}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Recent Messages */}
        {config?.configured && (
          <div className="border border-gray-200 rounded-lg p-5 space-y-3" data-testid="whatsapp-messages">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-gray-500" />
                <h2 className="font-medium text-sm">Mensagens Recentes</h2>
              </div>
              <Button variant="outline" size="sm" onClick={fetchMessages} disabled={loadingMessages} data-testid="wa-fetch-messages">
                {loadingMessages ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                <span className="ml-1 text-xs">Atualizar</span>
              </Button>
            </div>
            {messages.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-4">Nenhuma mensagem registrada</p>
            ) : (
              <div className="space-y-1.5 max-h-64 overflow-y-auto">
                {messages.map((m, i) => (
                  <div key={i} className={`flex items-start gap-2 p-2 rounded text-xs ${m.direction === 'outbound' ? 'bg-green-50' : 'bg-gray-50'}`}>
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${m.direction === 'outbound' ? 'bg-green-200' : 'bg-gray-200'}`}>
                      {m.direction === 'outbound' ? <ArrowUpRight className="h-3 w-3 text-green-700" /> : <MessageCircle className="h-3 w-3 text-gray-600" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{m.direction === 'outbound' ? `Para: ${m.to}` : `De: ${m.from}`}</span>
                        {m.contact_name && <span className="text-gray-400">({m.contact_name})</span>}
                        {m.status && <Badge variant="outline" className="text-[9px]">{m.status}</Badge>}
                      </div>
                      <p className="text-gray-600 truncate">{m.body || `[${m.type}]`}</p>
                    </div>
                    <span className="text-[10px] text-gray-400 flex-shrink-0">
                      {m.sent_at ? new Date(m.sent_at).toLocaleString('pt-BR') : m.received_at ? new Date(m.received_at).toLocaleString('pt-BR') : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Help Links */}
        <div className="text-xs text-gray-400 space-y-1 pt-2">

        {/* Interactive Menu Section */}
        <div className="border rounded-lg p-4 sm:p-6 space-y-4" data-testid="whatsapp-menu-section">
          <div className="flex items-center gap-2 mb-2">
            <MessageCircle className="h-5 w-5 text-green-600" />
            <h2 className="font-semibold text-base">Menu Interativo</h2>
            <Badge className="bg-green-100 text-green-700 text-[10px]">Bot</Badge>
          </div>
          <p className="text-xs text-gray-500">Configure o menu de botoes enviado ao cliente. Quando o cliente clica em um botao, o sistema responde automaticamente.</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label className="text-xs">Nome do Representante</Label>
              <Input value={menuRepName} onChange={e => setMenuRepName(e.target.value)} placeholder="Thamires" data-testid="menu-rep-name" />
            </div>
            <div>
              <Label className="text-xs">Marca Padrao</Label>
              <Input value={menuBrand} onChange={e => setMenuBrand(e.target.value)} placeholder="Posto Autorizado" data-testid="menu-brand" />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Botoes (max 3)</Label>
            {menuBtnLabels.map((label, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="text-xs text-gray-400 w-4">{i+1}.</span>
                <Input value={label} onChange={e => { const n = [...menuBtnLabels]; n[i] = e.target.value; setMenuBtnLabels(n); }} className="flex-1" data-testid={`menu-btn-${i}`} />
              </div>
            ))}
          </div>

          <div>
            <Label className="text-xs">Mensagem "Tirar duvidas" (resposta automatica)</Label>
            <textarea value={menuDuvidasMsg} onChange={e => setMenuDuvidasMsg(e.target.value)} rows={2} className="w-full text-sm border rounded-md px-3 py-2 mt-1" placeholder="Fique a vontade para enviar sua duvida..." data-testid="menu-duvidas-msg" />
          </div>

          <div>
            <Label className="text-xs">Mensagem "Falar com atendente" (resposta automatica)</Label>
            <textarea value={menuAtendenteMsg} onChange={e => setMenuAtendenteMsg(e.target.value)} rows={2} className="w-full text-sm border rounded-md px-3 py-2 mt-1" placeholder="Aguarde um momento..." data-testid="menu-atendente-msg" />
          </div>

          <Button onClick={handleSaveMenu} disabled={savingMenu} className="bg-green-600 hover:bg-green-700" data-testid="save-menu-btn">
            {savingMenu ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Settings className="h-4 w-4 mr-1" />}
            Salvar Configuracao
          </Button>

          {/* Preview */}
          <div className="border rounded-lg p-4 bg-gray-50">
            <p className="text-xs text-gray-500 mb-2 font-medium">Pre-visualizacao da mensagem:</p>
            <div className="bg-white border rounded-lg p-3 text-sm space-y-2 max-w-sm">
              <p><strong>{(() => { const h = new Date().getHours(); return h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite'; })()},</strong></p>
              <p>Meu nome e <strong>{menuRepName || 'Thamires'}</strong>, represento o <strong>{menuBrand || 'Posto Autorizado'}</strong>, e estou entrando em contato para dar continuidade ao seu atendimento.</p>
              <p>Como deseja prosseguir?</p>
              <div className="flex flex-col gap-1.5 pt-2">
                {menuBtnLabels.map((l, i) => (
                  <div key={i} className="border rounded-full px-3 py-1.5 text-center text-xs text-blue-600 border-blue-200 bg-blue-50">{l}</div>
                ))}
              </div>
            </div>
          </div>

          {/* Send Menu */}
          <div className="border-t pt-4">
            <Label className="text-xs font-medium">Enviar Menu para Cliente</Label>
            <div className="flex gap-2 mt-2">
              <Input value={menuSendTo} onChange={e => setMenuSendTo(e.target.value)} placeholder="Telefone (ex: 5531999999999)" className="flex-1" data-testid="menu-send-to" />
              <Input value={menuSendBrand} onChange={e => setMenuSendBrand(e.target.value)} placeholder="Marca (opcional)" className="w-40" data-testid="menu-send-brand" />
              <Button onClick={handleSendMenu} disabled={sendingMenu} className="bg-green-600 hover:bg-green-700 shrink-0" data-testid="send-menu-btn">
                {sendingMenu ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>

        {/* Original Help Links */}
          <p><Link2 className="h-3 w-3 inline mr-1" />
            <a href="https://developers.facebook.com/docs/whatsapp/cloud-api" target="_blank" rel="noreferrer" className="underline hover:text-gray-600">Documentação da API de Nuvem do WhatsApp</a>
          </p>
          <p><Link2 className="h-3 w-3 inline mr-1" />
            <a href="https://business.facebook.com/settings/whatsapp-business-accounts" target="_blank" rel="noreferrer" className="underline hover:text-gray-600">Gerenciador do WhatsApp Business</a>
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
}
