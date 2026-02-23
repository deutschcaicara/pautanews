# Status / Handoff — Pendências Reais (Fev/2026)

Data: 2026-02-22

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

## Validação local concluída

Executado com `.venv` local:
- `python3 -m compileall -q backend/app backend/tests backend/scripts` ✅
- `.venv/bin/python -m pytest -q backend/tests` ✅ `29 passed`
- `.venv/bin/python backend/scripts/replay_backtest_gate.py` ✅ `skip` (sem `RADAR_DB_URL` / dataset no legado)

## O que AINDA falta (realmente)

### 1. Dependência de infraestrutura / ambiente (não é bug local)

1. Backtest gate real no CI/CD
- Falta:
  - ambiente com acesso ao legado `/home/diego/news` (ou benchmark equivalente)
  - `RADAR_DB_URL` válido
  - dataset/DB de benchmark
- Hoje:
  - script existe e falha/`skip` corretamente sem esses requisitos

2. Métricas de backlog/DLQ de produção
- Falta:
  - RabbitMQ Management plugin/API habilitados no ambiente alvo
  - variáveis de ambiente setadas (`RABBITMQ_MANAGEMENT_URL`, user/pass)
- Hoje:
  - código já suporta probe por management API e fallback por `celery inspect`

3. Hardening em fontes reais (`SPA_HEADLESS` / `SPA_API` / `PDF`)
- Falta:
  - testar em fontes reais e ajustar contratos `metadata.spa_api_contract`, `metadata.spa_api_request`, `metadata.headless_capture`
- Hoje:
  - framework está implementado, mas calibração depende da fonte real

### 2. Pendências de produto/UX (não bloqueiam pipeline)

1. UI “final rica” (polimento)
- Falta:
  - refinamento visual/UX e fluxo editorial mais sofisticado
- Hoje:
  - UI MVP funcional já existe para Plantão/Oceano/Evento com ações

2. Regras editoriais avançadas de `SPLIT`
- Falta:
  - políticas mais sofisticadas (ex.: recomputar/reatribuir summary/lane por docs movidos, guardrails editoriais avançados)
- Hoje:
  - `SPLIT` MVP funcional via `feedback`

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
3. Polir UI (visual/fluxo), se isso for requisito de entrega final
