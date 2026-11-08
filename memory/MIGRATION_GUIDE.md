# Guia de Migração — MasterMaq Sync Hub

Guia definitivo para clonar o projeto para um novo ambiente Emergent, preservando 100% do estado atual sem alterar código.

**Repositório GitHub**: https://github.com/u32378656-ops/system-maq.git
**Última atualização**: Julho/2026 — inclui perfil Invisacook (white-label), filtros de prioridade/cancelada, Laudo Mastermaq reescrito.

---

## 1️⃣ Visão geral do stack

| Camada | Tech |
| --- | --- |
| Frontend | React 19 (CRA), Tailwind, Shadcn/UI, lucide-react, axios, react-router 6 |
| Backend | Python 3 + FastAPI + uvicorn (gerenciado por Supervisor na porta 8001) |
| DB principal | Supabase (PostgreSQL via PostgREST — dados relacionais) |
| DB secundário | MongoDB (users, os_metadata (priority/print_count), tracking GPS, session, laudo_drafts) |
| Scraping | Playwright + Chromium headless |
| Docx | python-docx + openpyxl (import planilha) |
| Auth | JWT customizado (não Emergent Auth) — 3 roles: admin, technician, invisacook |
| Integrações | Google Maps, WhatsApp Cloud API, Assinafy (assinatura), Emergent LLM Key, Telecontrol (scraping) |

---

## 2️⃣ Passo a passo

### A. Substituir o /app

- No novo ambiente Emergent, apagar TUDO em `/app` exceto `.git` e `.emergent`.
- Clonar o repositório do usuário: `git clone --depth 1 https://github.com/u32378656-ops/system-maq.git /tmp/repo && cp -r /tmp/repo/* /tmp/repo/.[!.]* /app/` (menos `.git`).
- NÃO copiar `node_modules`, `__pycache__`, `.venv` — serão recriados.

Comando cru pra fazer tudo:
```bash
cd /app
for item in $(ls -A); do
  [ "$item" != ".git" ] && [ "$item" != ".emergent" ] && rm -rf "/app/$item"
done
rm -rf /tmp/repo
git clone --depth 1 https://github.com/u32378656-ops/system-maq.git /tmp/repo
cd /tmp/repo && for item in $(ls -A); do
  [ "$item" != ".git" ] && cp -r "/tmp/repo/$item" "/app/"
done
```

### B. Instalar dependências

```bash
cd /app/backend && pip install -r requirements.txt
cd /app/frontend && yarn install --ignore-engines
# ⚠️ --ignore-engines é OBRIGATÓRIO — @supabase/supabase-js 2.110+ pede Node 22,
# mas o Emergent tem Node 20. Sem essa flag, o yarn aborta.

# Playwright browsers (obrigatório pro scraper Telecontrol)
playwright install chromium
playwright install-deps chromium
```

**Observação de deps opcionais**: `canvas` (dep opcional do frontend) tenta compilar via node-pre-gyp e falha silenciosamente no Emergent. É OPCIONAL — o app sobe normal. Só instalar `libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev` se algum recurso quebrar por isso.

### C. Configurar .env

Copiar do ambiente antigo (**NUNCA commitar**):

**/app/backend/.env (28 chaves — todas obrigatórias):**

```
MONGO_URL="mongodb://localhost:27017"
DB_NAME="test_database"
SUPABASE_URL=https://vqzwgkevsaihlgmcswvi.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZxendna2V2c2FpaGxnbWNzd3ZpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjA3NDE3MCwiZXhwIjoyMDk3NjUwMTcwfQ.STR6tG5JuRFPfJWGXST7C8KOg1heJ_qYnwrkIZacwYE
WA_APP_SECRET=b0a9490b5940099e4ee1ab5f5e8f9bf0
WA_APP_ID=2006415486698372
CORS_ORIGINS="*"
APP_LOGIN_EMAIL="mastermaqassistencia@gmail.com"
APP_LOGIN_PASSWORD="atr132641"
JWT_SECRET="mastermaq_secret_key_2024_secure"
TELECONTROL_LOGIN="19955560000128"
TELECONTROL_PASSWORD="Thami2007"
TELECONTROL_LOGIN_HQ="19955560000128"
TELECONTROL_PASSWORD_HQ="Atr132641?"
TELECONTROL_BASE_URL="https://posvenda.telecontrol.com.br"
SYNC_INTERVAL_MINUTES=30
HISENSE_SYNC_WINDOW_DAYS=30
GOOGLE_MAPS_API_KEY=AIzaSyCoMnKhkr2-KEdAWGylwqsugdAlZCZfKO8
ASSINAFY_API_KEY=GT16ydBNcrU9-fLNjbZgHMki04tOkGOyidfygfWtYMXamezOrB4-TDZFnIdtcEZM
ASSINAFY_WORKSPACE_ID=1020d773dbfd5c45ef25fc99090a
ASSINAFY_API_URL=https://api.assinafy.com.br/v1
PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
EMERGENT_LLM_KEY=sk-emergent-8A069A47e2d8093A1F
WA_PERMANENT_TOKEN=EAAcg0wJbQ4QBRIqZCr74wxfElV5ZAh29xUy9DOcaa8F1SkBGZCIeVNPvLxmJzP1egr0zQWqAhZBeC7xwNub1ji5wVco9sZAtxdss6ZAK8q75nYsWy7usDKoiebFqqMMgmWZA9i9kQ1EcLoK9XCRdH1F1AUQU3mjmO9gUPE9uekms4nMhXkT80vnzwnDClZCPYAZDZD
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZxendna2V2c2FpaGxnbWNzd3ZpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIwNzQxNzAsImV4cCI6MjA5NzY1MDE3MH0.PdvTS0CaydEanXy-Is5q8gSD98Uw-dTIcT2tfkYyY6A
EXTERNAL_API_KEY=mastermaq_ext_2024_secure
EXTERNAL_WEBHOOK_URL=https://mastermaqassistencia.com.br/api/external/webhook/status
SUPABASE_SENHA="Master-systems#0818"
```

**/app/frontend/.env:**

```
REACT_APP_BACKEND_URL=<URL público do preview, gerada pelo Emergent>
REACT_APP_GOOGLE_MAPS_API_KEY=AIzaSyCoMnKhkr2-KEdAWGylwqsugdAlZCZfKO8
WDS_SOCKET_PORT=443
```

⚠️ **NÃO** adicionar aspas nos valores. **NÃO** adicionar comentários. **NÃO** alterar `MONGO_URL`, `DB_NAME`, `REACT_APP_BACKEND_URL` — são protegidas pela plataforma.

### D. Banco Supabase — verificar se todas as tabelas + funções existem

O Supabase é compartilhado (`vqzwgkevsaihlgmcswvi`) e já tem os dados. Confirmar via SQL (ou pgAdmin):

```sql
-- Tabelas essenciais:
SELECT count(*) FROM service_orders;    -- deve ter ~6800+
SELECT count(*) FROM routes;             -- ~60
SELECT count(*) FROM manuais;            -- ~57
SELECT count(*) FROM notifications;      -- ~400
SELECT count(*) FROM products;           -- variável
SELECT count(*) FROM laudo_drafts;       -- variável

-- Função RPC crítica pra egress:
SELECT photos_status_for('27643');       -- retorna jsonb
```

**Recomendado (opcional mas MUITO recomendado)**: criar índice na coluna `source` pra deixar as queries por fonte (incluindo Invisacook) rápidas:

```sql
CREATE INDEX IF NOT EXISTS idx_service_orders_source ON service_orders(source);
```

Se algo estiver faltando, ver `/tmp/migrate_to_new.py` do ambiente antigo (script de migração completa) ou `/app/backend/migrate_to_new_supabase.py`.

**Sobre MongoDB local**: `os_metadata` (priority/print_count), `users`, `laudo_drafts` e `notifications_seen` são armazenados em MongoDB LOCAL do container. A cada migração o Mongo vem vazio, então:
- Prioridades marcadas se perdem — remarque as OSs conforme necessário.
- Rascunhos de laudos se perdem — o LaudoModal detecta e recria conforme o técnico digitar.
- Usuários se perdem (menos o admin master, que é seedado automaticamente pelo `APP_LOGIN_EMAIL`+`APP_LOGIN_PASSWORD` a cada boot). **Precisará recriar o usuário Invisacook** via `POST /api/users` (ver seção 5).

### E. Subir os serviços

```bash
sudo supervisorctl restart backend frontend
sleep 5
sudo supervisorctl status  # backend e frontend devem estar RUNNING
```

### F. Verificar tudo em 3 comandos

```bash
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
JWT=$(grep ^JWT_SECRET /app/backend/.env | cut -d= -f2 | tr -d '"')

# 1) Health + todas as 28 env vars presentes
curl -s "$API/api/admin/env-check?secret=$JWT" | python3 -m json.tool
# Esperado: "missing":[], supabase_project_ref="vqzwgkevsaihlgmcswvi", live_products_query.http_status=200

# 2) Login e listar OSs
TOKEN=$(curl -s -X POST "$API/api/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"mastermaqassistencia@gmail.com","password":"atr132641"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s "$API/api/service-orders?limit=2" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d['total'])"
# Esperado: total > 6000

# 3) Frontend
curl -sI "$API/" | head -1  # esperado: HTTP/1.1 200 OK ou HTTP/2 200
```

---

## 3️⃣ Arquitetura — como orientar

- **Backend entrypoint**: `/app/backend/server.py` (~2.8k linhas, monolito). Sub-módulos:
  - `supabase_db.py` — adapter Mongo→PostgREST (raise em erro, NUNCA silencia)
  - `telecontrol_scraper.py` — 2 scrapers (Hisense + HQ)
  - `laudo_generator.py`, `laudo_mastermaq_generator.py` — geração DOCX (o Mastermaq foi reescrito em julho/2026 com substituição a nível de run do python-docx pra preservar fontes/alinhamento — NÃO reverter)
  - `inventory_routes.py` — CRUD estoque
  - `tracking_module.py`, `manuais_module.py`, `whatsapp_module.py` — routers
  - `users_module.py` — RBAC (admin, technician, invisacook) com bcrypt
- **Frontend**: `/app/frontend/src/App.js` (rotas), páginas em `pages/`, componentes em `components/`
- **Regra de ouro**: TODA rota backend começa com `/api/`. TODA chamada frontend usa `REACT_APP_BACKEND_URL`.

### Perfil Invisacook (white-label completo)

Adicionado em julho/2026 — perfil restrito de parceiro:
- **Backend RBAC** (`server.py` L1157-1762): Invisacook só vê/cria/edita OSs com `source="invisacook"`. Numeração INV-##### com sequência própria no Mongo (`os_metadata_col._key = "invisacook_seq"`), independente da numeração Mastermaq.
- **Frontend** (`DashboardLayout.js` + `ServiceOrdersPage.js`):
  - `useAuth` expõe `isInvisacook` (`context/AuthContext.js:155`)
  - Sidebar **branco** (revertido de preto por preferência do usuário)
  - Header com bg `#F7F5F2` só para Invisacook
  - Botão "Instalar App" com fill `#E8551F`, texto e borda pretos (só Invisacook)
  - Logo INVISACOOK (`/assets/invisacook-logo.webp`) substitui a Mastermaq
  - Title dinâmico: "Invisacook | Portal de OSs" / favicon `/assets/invisacook-logo.webp`
  - Menu lateral só mostra "Ordens de Serviço"
  - Filtros ocultos: chips de fonte, "Todas as Marcas"
  - Botão "Gerar Laudo", badge overdue, notificações e badge `role-badge` no header — TODOS ocultos
  - Card de OS com `source="invisacook"` mostra logo Invisacook em vez de Mastermaq/Telecontrol
- **BRAND_LIST** inclui `Invisacook` como marca selecionável.

---

## 4️⃣ Otimizações críticas ativas (NÃO reverter!)

- **Photo lazy-load** — `GET /service-orders/{os_number}` só retorna fotos com `?include_photos=1`. Reduz egress ~99%.
- **Photos-status via RPC** — função Postgres `photos_status_for()` retorna booleans server-side (não faz download das fotos).
- **Cache em memória (server-side)**: dashboard 5min, statuses/brands 10min, OS list 60s, notifications 30s, telecontrol/status 60s. Cache key inclui `role`, então Invisacook não polui cache do admin.
- **Auto-sync HQ REMOVIDO** — HQ só roda via botão "Sincronizar" (SLA <1min com Hisense+HQ em paralelo).
- **`update_one` do adapter RAISE em erro** — nunca mais silencioso (senão perde dados como aconteceu com `laudo_drafts` em 22/jun).
- **Priority preservada** — `priority` em `os_metadata_col` só muta se o body do PUT contém o campo `priority` explicitamente. Autosaves de status/notas não zeram o selo (fix do bug "OSs finalizadas perdem prioridade").
- **Filtro Priority cross-page** — busca todos os `os_number` marcados no Mongo ANTES de paginar no Supabase. Sem isso, o filtro só via a página atual (30 rows).
- **`OS Cancelada` sempre disponível no filtro de status** — merge de `OS_STATUSES` canônicos com statuses do servidor, mesmo se nenhuma OS estiver com esse status no momento.
- **Laudo Mastermaq DOCX** — `laudo_mastermaq_generator.py` usa `_set_cell_text_preserving_runs()` pra manter fontes/alinhamento/negrito do template original. SEM campos Hisense (Série, Batch, Instalação, Tensão, fotos 3/5/6/8).

---

## 5️⃣ Contas de teste

- **Admin único**: `mastermaqassistencia@gmail.com` / `atr132641`
  - Seedado automaticamente a cada boot via `seed_admin()` em `users_module.py`.
- **Invisacook (perfil restrito)**: `invisacook@invisacookbrasil.com` / `Invisa@2026`
  - **NÃO é seedado automaticamente**. Precisa recriar a cada migração:
    ```bash
    API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
    TOKEN=$(curl -s -X POST "$API/api/auth/login" -H "Content-Type: application/json" \
      -d '{"email":"mastermaqassistencia@gmail.com","password":"atr132641"}' \
      | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
    curl -s -X POST "$API/api/users" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name":"Invisacook","email":"invisacook@invisacookbrasil.com","password":"Invisa@2026","role":"invisacook","active":true}'
    ```
- **Telecontrol Hisense**: `19955560000128` / `Thami2007`
- **Telecontrol HQ**: `19955560000128` / `Atr132641?` (⚠️ o `?` no final, não `!`)

Todas as credenciais também em `/app/memory/test_credentials.md`.

---

## 6️⃣ Checklist final antes de entregar

- [ ] `/api/admin/env-check` retorna `missing:[]` e `supabase_project_ref: "vqzwgkevsaihlgmcswvi"`
- [ ] Login admin funciona
- [ ] Dashboard mostra ~6800 OSs
- [ ] Botão "Sincronizar" traz OSs HQ em <1 min
- [ ] Cadastrar produto sem preencher nada gera código `PROD-XXXXXXXX` (HTTP 200)
- [ ] Página pública `/p/<code>` abre sem login
- [ ] Página pública `/os-view/<os_number>` abre sem login
- [ ] Impressão de OS gera QR (aponta pra `/o/<os_number>`)
- [ ] Impressão de Produto gera QR (aponta pra `/p/<code>`)
- [ ] LaudoModal salva rascunho e mostra "Salvo há X min"
- [ ] Gerar DOCX Hisense / Recall / Mastermaq funcionam (Mastermaq preserva fontes)
- [ ] Import de planilha `.xlsx`/`.csv` cria produtos
- [ ] **Usuário Invisacook criado** via `POST /api/users` (ver seção 5)
- [ ] Login Invisacook (`invisacook@invisacookbrasil.com` / `Invisa@2026`) mostra:
  - Só "Ordens de Serviço" no menu
  - Header com bg `#F7F5F2`
  - Sidebar branca
  - Logo INVISACOOK no topo do sidebar
  - Title da aba: "Invisacook | Portal de OSs"
  - Favicon Invisacook
  - Sem chips de fonte, sem filtro de marca, sem notificações, sem badge overdue
- [ ] `sudo supervisorctl status` — backend e frontend RUNNING

---

## 7️⃣ Troubleshooting

Se algo falhar durante a migração:

1. Consulte `/app/memory/PRD.md` (histórico completo) e `/app/memory/test_credentials.md`.
2. Todo blocker anterior está documentado lá com causa raiz + fix.
3. **Frontend não sobe** (`craco: not found` ou erro de compile): `cd /app/frontend && yarn install --ignore-engines` e depois `sudo supervisorctl restart frontend`.
4. **Backend não conecta no Supabase**: verifique `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` — o `env-check` do passo F.1 aponta exatamente qual está errado.
5. **Playwright não acha o Chromium**: `PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright` no `.env` — se necessário, rode `playwright install chromium` novamente.
6. **Lint bloqueia deploy** (`E722 bare except`): já corrigido nesta iteração, mas se aparecer em outro arquivo, substitua `except:` por `except Exception:`.

⚠️ **NÃO CHAMAR TESTING AGENT DURANTE A MIGRAÇÃO** — o dono do projeto testa manualmente.

Utilizar as mesmas variáveis e clonar sobre `/app`.
