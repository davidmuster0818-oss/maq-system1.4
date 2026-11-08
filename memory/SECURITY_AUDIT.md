# Auditoria de Segurança — Mastermaq (2026-11-07)

Referências: OWASP ASVS 4 / OWASP API Security Top 10 (2023). Teste reproduzível: `python backend/tests/pentest.py` (cria e apaga contas TEST_).

## 1. Vulnerabilidades encontradas
| # | Criticidade | Achado | Status |
|---|---|---|---|
| 1 | CRITICAL | Chave anon do Supabase (pública no bundle) lia direto do banco **7.152 OSs e 160 roteiros** (nome, telefone, endereço) — tabelas sem RLS | CORRIGIDO: RLS ligado em todas as 16 tabelas + REVOKE anon/authenticated (`migrations/security_rls_lockdown.sql`). Prova: anon → 42501 permission denied |
| 2 | HIGH | IDOR/BOLA: técnico lia/alterava qualquer OS pelo número (`GET/PUT /api/service-orders/{n}`) | CORRIGIDO: técnico sem página OS só acessa OSs dos roteiros dele (403) |
| 3 | HIGH | Sessões não revogáveis: usuário desativado/excluído ou com senha trocada continuava com token válido por 30 dias | CORRIGIDO: checagem de usuário ativo + `tokens_valid_after` em todo request; validade 7 dias com renovação automática |
| 4 | HIGH | Login sem proteção contra força bruta | CORRIGIDO: 8 tentativas/15 min por email, 20/15 min por IP → 429 + registro |
| 5 | HIGH | Técnico listava todas as OSs (`GET /api/service-orders`) | CORRIGIDO: só com página OS ou Roteiros liberada |
| 6 | MEDIUM | Mesma chave Google usada no navegador e no servidor (exposta no bundle e no histórico Git) | AÇÃO DO DONO: ver seção 3 |
| 7 | MEDIUM | `/docs`, `/redoc`, `/openapi.json` públicos (mapa completo da API) | CORRIGIDO: desativados |
| 8 | MEDIUM | Sem cabeçalhos de segurança / CSP | CORRIGIDO: nosniff, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy, COOP; CSP nas páginas |
| 9 | MEDIUM | Source maps no build de produção (código-fonte legível no DevTools) | CORRIGIDO: desligados no build (craco) |
| 10 | MEDIUM | `/api/tracking/config` sem login | CORRIGIDO: exige login |
| 11 | MEDIUM | Erros 500 podiam devolver detalhes internos | CORRIGIDO: handler global devolve mensagem genérica, detalhe só no log |
| 12 | MEDIUM | Backups de geocode versionados no Git (`backend/backups/`) | CORRIGIDO: removidos do Git e ignorados |
| 13 | LOW | Token "alg none"/forjado | JÁ PROTEGIDO (401), confirmado |
| 14 | LOW | CORS `*` com credenciais | CORRIGIDO: sem credenciais (app usa Bearer, não cookie) |
| 15 | LOW | Endpoints públicos sem limite (QR, rastreio, assinatura, PDF temporário) | CORRIGIDO: 60 req/min por IP |
| 16 | LOW | Senha de usuário sem tamanho mínimo; comparação de senha legado não constante | CORRIGIDO: mínimo 8; `hmac.compare_digest` |

## 2. Matriz de permissões (servidor)
Páginas por usuário, editáveis em Usuários → Editar. Bloqueio aplicado no servidor (middleware) além do menu.
| Página | Rotas da API protegidas | Admin | Técnico (padrão) | Invisacook |
|---|---|---|---|---|
| Ordens de Serviço | lista OS, dashboard, telecontrol, notificações, scrapers | ✔ | ✖ (lista liberada se tiver Roteiros) | ✔ (só OSs Invisacook) |
| Roteiros | /routes, /rf, /tracking | ✔ | ✔ (só os roteiros dele) | ✖ |
| Estoque | /inventory | ✔ | ✖ | ✖ |
| Financeiro | (sem API) | ✔ | ✖ | ✖ |
| Manuais | /manuais | ✔ | ✔ | ✖ |
| Mi | /mi | ✔ | ✖ | ✖ |
| WhatsApp API | /whatsapp (exceto webhook Meta) | ✔ | ✖ | ✖ |
| Usuários | /users | ✔ | nunca | nunca |
| Webhooks | /webhooks | ✔ | ✖ | ✖ |
| Adesivos | /label-templates (alteração) | ✔ | ✖ | ✖ |
O admin principal (do .env) sempre tem tudo. Página liberada pelo admin a um técnico também libera as rotas "só admin" daquela página (exceto Usuários).

## 3. Credenciais para rotacionar / restringir (ação do dono)
- **Google Maps (CRÍTICO de custo)**: a chave atual está no bundle e no histórico Git e é a mesma do servidor. Criar 2 chaves: (a) navegador — restrição "Referenciadores HTTP" para os domínios do app, APIs: Maps JavaScript; (b) servidor — APIs: Routes, Geocoding, Places, Static Maps; definir cotas diárias e alerta de faturamento. Depois trocar `REACT_APP_GOOGLE_MAPS_API_KEY` e `GOOGLE_MAPS_API_KEY`.
- **Supabase anon key**: ficou inofensiva com o RLS; rotação opcional.
- **Supabase service key / senha do banco, JWT_SECRET, Telecontrol, Meta WhatsApp, Ollama, Pluggy, Assinafy**: não encontrados no navegador nem no histórico Git. Rotacionar se alguém teve acesso ao servidor/.env. Trocar JWT_SECRET desloga todos.

## 4. Testes de invasão (36/36 PASS)
Sem login (12 rotas privadas) → 401/403 · token forjado → 401 · técnico em Usuários/Mi/WhatsApp/Estoque/Dashboard/Webhooks/Adesivos → 403 · página removida bloqueia no servidor · página concedida funciona · Usuários nunca liberado a não-admin · IDOR leitura/alteração de OS → 403 · token de usuário desativado → 401 · token anterior à troca de senha → 401 · força bruta → 429 · cabeçalhos presentes · openapi desligado · injeção na busca sem efeito · anon Supabase em service_orders/routes/whatsapp_messages/products → negado.

## 5. Monitoramento
Coleção Mongo `security_events`: login_ok, login_failed, login_blocked, forbidden_page, forbidden_admin, rate_limited, user_created/updated/deleted (sem senha/token).

## 6. Riscos que permanecem
- QR de etiqueta (`/os/public/by-number`) continua por número, por decisão do dono (etiquetas internas). Mitigado por limite de 60/min por IP e dados mascarados.
- Canais de broadcast do rastreio (Supabase Realtime) podem ser ouvidos por quem souber o ID do roteiro (UUID, não enumerável com RLS ligado).
- Bucket `product-images` é público (imagens de produto, intencional).
- CSP usa `'unsafe-inline'` em scripts (exigido pelo index.html atual); validar CSP após publicar.
- Token de sessão em localStorage (risco só se houver XSS; CSP + React mitigam).
- Limites de requisição ficam em memória do servidor (zeram ao reiniciar).
- Restrições do Google Maps/cotas dependem do dono (seção 3).
- `/admin/env-check` ainda usa `?secret=` (comparação segura, mas o segredo passa na URL).
