# Política de uso do Graphify neste projeto

Grafo construído em `/app/graphify-out/` (rodar `graphify update .` após mudanças estruturais).

## Quando USAR o grafo (`graphify query/path/explain`)

- **Exploração arquitetural**: "que funções compõem o subsistema X?"
- **Mapear subsistema desconhecido**: primeiro contato com uma parte do código
- **God-nodes / hubs**: entender o que são as abstrações centrais
- **Trace de dependência entre classes/funções**: `graphify path A B`
- **Overview em briefings novos**: `graphify explain <ClasseCentral>`

## Quando NÃO USAR o grafo (ler arquivo direto)

- **Busca por substring exata** (`grep -n "photo_" server.py`): grep é mais rápido e preciso
- **Fix cirúrgico** conhecido: `view_file` + `search_replace` é o caminho
- **Variáveis de módulo / constantes globais** (ex: `SCRAPER_HEALTH`, `PHOTO_SLOTS`): grafo AST não indexa bem
- **Cross-language paths** (frontend → backend via HTTP): grafo não conecta (não há import estático)
- **Comentários / strings**: grafo indexa símbolos, não texto livre

## Comandos úteis

```bash
export PATH="/root/.local/bin:$PATH"

# Rebuild rápido (~3s, zero API cost) após mudanças estruturais
cd /app && graphify update .

# Rebuild completo (força)
cd /app && graphify extract . --code-only --no-viz --force
cd /app && graphify cluster-only . --no-label

# Queries
graphify query "..." --budget 3000       # ampliar tokens quando truncar
graphify path "ClassA" "ClassB"
graphify explain "SomeSymbol"
```

## Ruído já excluído (via `/app/.graphifyignore`)
- `backend/tests/`, `backend_test.py`, `tests/`
- `test_reports/`, `artifacts/`, `graphify-out/`
- `migration_*.json`, `iteration_*.json`, `fix_dates.py`
- `frontend/build/`, `frontend/node_modules/`
