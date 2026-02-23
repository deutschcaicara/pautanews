# Status / Handoff — Pendências Reais (Fev/2026)

Data: 2026-02-23

Objetivo deste arquivo:
- registrar o que já foi implementado e validado localmente
- listar somente o que ainda falta de forma objetiva
- separar o que depende de infra/dados externos (não é bug de código local)

## Estado atual (código local)

Implementado e validado no repositório:
- Pipeline FAST/RENDER/DEEP com fetch/extract/organizer/score em MVP funcional
- Scheduler por `cadence` + filas Celery alinhadas
- SSE com `EVENT_UPSERT`, `EVENT_STATE_CHANGED`, `EVENT_MERGED`
- State machine persistida (`event_state`) + manutenção (`HYDRATING/PARTIAL_ENRICH`, `QUARANTINE -> EXPIRED`)
- Merge/canonicalização (`merge_audit`, tombstone, re-score pós-merge)
- Feedback editorial com `IGNORE`, `SNOOZE`, `PAUTAR`, `MERGE`, `SPLIT` (MVP)
- APIs de produto (`/api/plantao`, `/api/events/{id}`, `/api/oceano-azul`)
- UI MVP com ações editoriais, histórico de estado/merge/feedback
- CMS Draft endpoint MVP
- Observabilidade custom (Prometheus) + queue probe com RabbitMQ Management opcional
- Backtest gate script (com `skip` controlado quando faltam DB/dataset/legado)
- Backtest gate com fallback por fixture local (crise/normal/marasmo) para validação executável sem DB externo
- Validação forte do `SourceProfile` (strategy/pool/cadence/endpoints/metadata)
- Conversor de fontes legado `~/news` -> DSL do backend com validação (`backend/convert_sources.py`)
- Seed preserva múltiplos endpoints do mesmo domínio (ex.: notícias + agenda), evitando perda de cobertura editorial
- Sync/upsert de fontes legado (`~/news`) no banco local deste servidor concluído
- Dedupe por URL exata de endpoint no sync (clones históricos/aliases desativados)
- Auditoria live de fontes (`backend/scripts/audit_sources_live.py`) com relatório local

## Validação local concluída

Executado com `.venv` local:
- `python3 -m compileall -q backend/app backend/tests backend/scripts` ✅
- `.venv/bin/python -m pytest -q backend/tests` ✅ `42 passed`
- `.venv/bin/python backend/scripts/replay_backtest_gate.py` ✅ `pass` (fallback fixture local com cenários crise/normal/marasmo)
- `.venv/bin/python backend/convert_sources.py --validate` ✅ (`~/news` convertido e validado: 150 fontes)
- `DATABASE_URL=... .venv/bin/python -m app.seeds.seed_sources` ✅ sync executado no banco local
  - resultado: `inserted=146`, `updated=4`, `duplicates_disabled=2`
  - cobertura: `0` URLs da curadoria `~/news` faltando no conjunto `enabled`
- re-sync/normalização posterior ✅
  - resultado: `updated=150`, `duplicate_endpoints_disabled=72`, `normalized_existing=72`
  - banco final: `148` fontes `enabled`, `0` URLs duplicadas ativas
- `.venv/bin/python backend/scripts/audit_sources_live.py --summary-only` ✅ (148 fontes)
  - `141` com `2xx`, `6` com `4xx`, `1` timeout
  - principais problemas atuais detectados: `DOU` (404), `TCU Acórdãos` (404), alguns `403`/bot block (`Fiocruz`, `Mercosul`)

## O que AINDA falta (realmente)

### 1. Dependência de infraestrutura / ambiente (não é bug local)

1. Backtest gate real no CI/CD (com dados reais)
- Falta:
  - ambiente com acesso ao legado `/home/diego/news` (ou benchmark equivalente)
  - `RADAR_DB_URL` válido
  - dataset/DB de benchmark
- Hoje:
  - script roda localmente com fixture e valida thresholds
  - benchmark real ainda depende de DB/dataset/legado acessíveis

2. Métricas de backlog/DLQ de produção
- Falta:
  - RabbitMQ Management plugin/API habilitados no ambiente alvo
  - variáveis de ambiente setadas (`RABBITMQ_MANAGEMENT_URL`, user/pass)
- Hoje:
  - código já suporta probe por management API e fallback por `celery inspect`

3. Hardening em fontes reais (`SPA_HEADLESS` / `SPA_API` / `PDF`)
- Falta:
  - corrigir endpoints quebrados específicos detectados no live audit (ex.: `DOU`, `TCU Acórdãos`)
  - ajustar contratos `metadata.spa_api_contract`, `metadata.spa_api_request`, `metadata.headless_capture` para fontes que exigirem customização
  - tratar fontes com `403`/bot block (headers/estratégia/fallback) nos domínios problemáticos
- Hoje:
  - framework está implementado, perfis foram normalizados, e existe auditoria live para medir erros por fonte

### 2. Pendências backend de produto (sem frontend)

1. Regras editoriais avançadas de `SPLIT`
- Falta:
  - políticas mais sofisticadas (ex.: recomputar/reatribuir summary/lane por docs movidos, guardrails editoriais avançados)
- Hoje:
  - `SPLIT` MVP funcional via `feedback`

2. Calibração final de ranking/merge com benchmark real
- Falta:
  - ajustar thresholds e heurísticas com replay de cenários reais (crise/normal/marasmo)
- Hoje:
  - gate e fixture local existem, mas calibração com produção ainda não foi fechada

## O que NÃO está faltando (já entregue)

- `MERGE`/tombstone + `merge_audit`
- `event_state` persistido
- `QUARANTINE -> EXPIRED`
- `UNVERIFIED_VIRAL` em flags
- endpoints Plantão/Evento/Oceano
- reasons no feed
- CMS Draft endpoint
- feedback API com validação/gating
- testes unitários base (29)

## Comandos para retomar em novo terminal

### Ambiente local
```bash
cd /home/diego/pautanews
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e backend
```

### Validação local
```bash
python3 -m compileall -q backend/app backend/tests backend/scripts
.venv/bin/python -m pytest -q backend/tests
.venv/bin/python backend/scripts/replay_backtest_gate.py
```

### Subir stack (compose)
```bash
docker compose up -d postgres rabbitmq redis api celery-fast celery-heavy celery-deep celery-ops celery-beat
```

### Sincronizar fontes curadas do `~/news` para o banco local (host)
```bash
cd /home/diego/pautanews/backend
DATABASE_URL='postgresql+asyncpg://radar:radar_secret@localhost:5434/radar_news' \
DATABASE_URL_SYNC='postgresql+psycopg://radar:radar_secret@localhost:5434/radar_news' \
../.venv/bin/python -m app.seeds.seed_sources
```

### Auditar fontes reais (status/content-type/sugestões)
```bash
cd /home/diego/pautanews
.venv/bin/python backend/scripts/audit_sources_live.py --concurrency 20 --summary-only
# relatório detalhado em artifacts/source_audit/latest.json
```

### Habilitar backlog real por RabbitMQ Management (se necessário)
Definir no ambiente/`.env`:
```bash
RABBITMQ_MANAGEMENT_URL=http://rabbitmq:15672
RABBITMQ_MANAGEMENT_USER=radar
RABBITMQ_MANAGEMENT_PASSWORD=radar_secret
```

## Próxima ação recomendada (objetiva)

Se quiser fechar o que resta de forma prática:
1. Preparar ambiente de benchmark (`RADAR_DB_URL` + dataset) e rodar `replay_backtest_gate.py` em modo estrito
2. Validar 2–3 fontes reais `SPA_API/HEADLESS/PDF` e ajustar `metadata` por fonte
3. (Opcional, fora deste escopo) Frontend editorial será tratado em etapa separada
