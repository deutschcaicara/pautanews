# Plano de Execução por Sprints — Fechar Gaps do Blueprint (Fev/2026)

Baseado em:
- `TASKS_ANALISE_BLUEPRINT_GAPS_FEV2026.md` (backlog priorizado P0–P3)
- `BLUEPRINT_FINAL_Radar_Hard_News_Fev2026.md`

Objetivo:
- Sair de "base promissora com gaps" para "MVP aderente ao blueprint", com foco inicial em P0/P1.

## Regras de execução (para não quebrar o projeto enquanto evolui)
- Ordem obrigatória: `P0 -> P1 -> P2 -> P3`
- Não abrir frente de UI/CMS antes de estabilizar pipeline + estados + SSE mínimo.
- Toda sprint fecha com smoke test local e checklist de aceite.
- PRs pequenos por fatia funcional (evitar mega-PR).

## Estratégia geral (macro)
- Sprint 0: estabilização de runtime/filas/config Celery (P0)
- Sprint 1: FAST PATH confiável + ingestão/scheduler (P1 parte 1)
- Sprint 2: estados + SSE + alertas por transição (P1 parte 2)
- Sprint 3: render/deep pools reais + evidência enriquecida (P2 base técnica)
- Sprint 4: merge/canonicalização/tombstone + deltas (P2 núcleo editorial)
- Sprint 5: APIs MVP + CMS draft + feedback/gating (P2/P3 produto)
- Sprint 6: anti-fragilidade, observabilidade, backtest gate e testes (P1/P2/P3 qualidade/ops)

## Status desta execução (2026-02-22)
- `Sprint 0`: avançada/substancialmente implementada no código (runtime/Celery)
- `Sprint 1`: parcialmente implementada (scheduler por cadence + correções FAST fetch/extract/profile)
- `Sprint 2`: avançada (estado persistido em múltiplos fluxos + SSE por polling robustecido + manutenção de timeout/TTL + gating editorial MVP)
- `Sprint 3`: avançada (fetch/extract com `SPA_HEADLESS` e `PDF` path + `SPA_API` contratual MVP + metadados/snapshot propagados até `Document`)
- `Sprint 4`: avançada (canonicalização por âncora forte + `MERGED`/`merge_audit` + reatribuição de `event_docs` no merge + re-score do canônico pós-merge)
- `Sprint 5`: avançada (endpoints Plantão/Evento/Oceano Azul + CMS Draft MVP + feeds filtrando tombstones/expirados + UI com ações editoriais/filtros/históricos + `SPLIT` MVP)
- `Sprint 6`: avançada (métricas custom + probe de filas com RabbitMQ management opcional + OTel best-effort API/HTTPX/Celery + CI/backtest gate básico)
- Validação local (ambiente com `.venv`): `pytest backend/tests` ✅ (`29 passed`)

## Sprint 0 — Estabilização de Runtime (P0)
Meta:
- Eliminar erros de import, filas/tarefas inválidas e inconsistências básicas de Celery.

Tasks do backlog:
- `#1`, `#2`, `#3`, `#4`, `#5`, `#38` (alinhamento de routes), `#47` (decisão sobre worker `anchors`)

Ordem exata de implementação:
1. Corrigir `draft.py` (imports + `asyncio`) para remover quebra imediata.
2. Decidir estratégia de alertas temporária:
   - criar `backend/app/workers/alerts.py` stub funcional (recomendado), ou
   - desabilitar dispatch em `score.py`.
3. Corrigir fila `nlp`:
   - declarar queue e route no Celery, ou
   - mover `draft` para fila já existente.
4. Alinhar `task_routes` do Celery com nomes reais de tasks.
5. Tratar `workers/anchors.py`:
   - remover do fluxo/registro, ou
   - ajustar assinatura para `event_id`.
6. Ajustar `docker-compose.yml` para refletir as filas realmente usadas nesta fase.

Arquivos-alvo (prováveis):
- `backend/app/workers/draft.py`
- `backend/app/workers/score.py`
- `backend/app/celery_app.py`
- `backend/app/workers/alerts.py` (novo, se escolhido)
- `backend/app/workers/anchors.py` (ou remoção/isolamento)
- `docker-compose.yml`

Aceite da sprint:
- Celery sobe sem task/fila fantasma.
- `score.py` não envia task inexistente.
- Draft worker importa e executa sem erro de import.
- Smoke: disparar `run_scoring` e verificar que não explode por alerta/draft.

## Sprint 1 — FAST PATH Confiável + Ingestão por Fonte (P1 parte 1)
Meta:
- Tornar o pipeline FAST funcional e previsível segundo o contrato de ingestão.

Tasks do backlog:
- `#6`, `#7` (parte FAST), `#14`, `#16`, `#17`, `#18`, `#19`, `#20`, `#34`, `#35`, `#36` (parte fetch limits mínima), `#37`, `#49` (subset de metadados)

Ordem exata de implementação:
1. Normalizar `SourceProfile` carregado do banco:
   - injetar `id`, `tier`, `is_official`, `lang`, `source_domain` canônicos.
2. Definir contrato de `fetch_policy_json`:
   - validar campos mínimos ou enriquecer defaults centralmente.
3. Implementar scheduler por `cadence`:
   - `interval_seconds` primeiro
   - `cron` em seguida (separado, mas ainda na sprint se couber)
4. Melhorar fetch observável:
   - registrar `fetch_attempt` para `304`
   - corrigir `snapshot_hash` em `fetch_attempts`
   - manter ETag/IMS
5. Fortalecer SSRF guard com `getaddrinfo` (compatível com legado).
6. Corrigir versionamento de RSS por item (hash por item).
7. Filtrar/normalizar itens RSS sem `link`.
8. Corrigir inferência de lane usando editoria correta (não `source_id`).
9. Aplicar limites mínimos no fetch:
   - `max_bytes` (corte simples)
   - timeout já existe
   - rate limit/concurrency podem entrar como versão mínima (locks por domínio)
10. Preparar roteamento FAST vs demais pools (sem render/deep completos ainda):
   - pelo menos não hardcode em `extract_fast`.

Arquivos-alvo (prováveis):
- `backend/app/scheduler.py`
- `backend/app/workers/orchestrator.py`
- `backend/app/schemas/source_profile.py`
- `backend/app/workers/fetch.py`
- `backend/app/workers/extract.py`
- `backend/app/workers/organizer.py`
- `backend/app/seeds/seed_sources.py`
- `backend/app/core/taxonomy.py` (se precisar metadata lane)

Aceite da sprint:
- Scheduler não dispara todas as fontes em todo tick.
- `304` aparece em `fetch_attempts`.
- RSS não cria versões falsas em massa.
- Pipeline FAST continua produzindo eventos.

## Sprint 2 — Estados + SSE + Alertas por Transição (P1 parte 2)
Meta:
- Colocar o fluxo editorial real do blueprint em operação: estados, SSE e alerta anti-spam.

Tasks do backlog:
- `#9`, `#10`, `#11`, `#13`, `#24`, `#25`, `#33`, `#45` (parte de transição/gating)

Ordem exata de implementação:
1. Definir serviço utilitário de transição de estado:
   - atualiza `events.status`
   - persiste `event_state`
   - retorna payload para SSE
2. Corrigir `state_engine`:
   - timeout de gating FAST=15s / RENDER=45s
   - separar config de SLO vs timeout de UI/action gating
3. Integrar estados ao pipeline:
   - `organizer` cria/atualiza -> `HYDRATING`
   - timeout -> `PARTIAL_ENRICH`
   - fluxos de ignore/quarantine/expired
4. Implementar SSE real:
   - stream contínuo
   - `EVENT_UPSERT`
   - `EVENT_STATE_CHANGED`
5. Integrar `reasons_json` no feed API (`/api/events` ou novo endpoint Plantão).
6. Implementar alerting worker por transição:
   - usar `EventAlertState`
   - cooldown + hash
7. Integrar `UNVERIFIED_VIRAL` em `flags_json` com critério compatível com blueprint.
8. Implementar TTL de `QUARANTINE -> EXPIRED` (job periódico).
9. Completar `Feedback API` mínimo com validação de evento + transição de estado permitida.

Arquivos-alvo (prováveis):
- `backend/app/state_engine.py`
- `backend/app/models/event.py` (se precisar metadados adicionais)
- `backend/app/main.py` (SSE + feed payload)
- `backend/app/workers/score.py`
- `backend/app/workers/alerts.py`
- `backend/app/api/feedback.py`
- `backend/app/celery_app.py` (scheduler/beat jobs adicionais)

Aceite da sprint:
- `event_state` recebe histórico real.
- SSE envia eventos contínuos (`EVENT_UPSERT`, `EVENT_STATE_CHANGED`).
- Alertas saem por transição, com cooldown.
- `QUARANTINE` pode expirar para `EXPIRED`.

## Sprint 3 — Pools Reais (RENDER/DEEP) + Evidência Enriquecida (P2 base técnica)
Meta:
- Tirar `HEAVY_RENDER_POOL` e `DEEP_EXTRACT_POOL` do papel.

Tasks do backlog:
- `#8`, `#28`, `#29`, `#30`, `#31`, `#36` (restante), `#49` (restante)

Ordem exata de implementação:
1. Refatorar roteamento do fetch por `strategy` e `pool`.
2. Implementar `SPA_API` (preferido) com endpoint JSON/XHR configurado no profile.
3. Integrar `SPA_HEADLESS` com captura de XHR/JSON (não só HTML).
4. Integrar `PDF` para `extract_deep`.
5. Completar `pdf_extractor.py`:
   - texto/tabelas
   - OCR fallback image-only
6. Expandir Golden Regex (máscara/sem máscara, links gov/PDF/DO, horários, normalização).
7. Popular `DocEvidenceFeature` completo (`has_pdf`, `money_count`, `has_table_like`, `evidence_json`).
8. Preencher metadados adicionais de `Document` (published/modif/lang/canonical_url/snapshot_id quando disponível).

Arquivos-alvo (prováveis):
- `backend/app/workers/fetch.py`
- `backend/app/workers/extract.py`
- `backend/app/workers/headless.py`
- `backend/app/workers/pdf_extractor.py`
- `backend/app/regex_pack.py`
- `backend/app/workers/organizer.py`
- `backend/app/models/anchor.py` (se precisar campos adicionais em `evidence_json`)

Aceite da sprint:
- Fonte SPA com `SPA_API` gera documento/evento sem Playwright.
- Fonte SPA com `SPA_HEADLESS` captura payload JSON.
- PDF entra no `DEEP_EXTRACT_POOL` e atualiza evento depois.
- Evidence features ficam mais completos e úteis para `SCORE_OCEANO_AZUL`.

## Sprint 4 — Merge/Canonicalização/TOMBSTONE + Deltas (P2 núcleo editorial)
Meta:
- Implementar `DEFER_MERGE` completo, tombstone e "o que mudou".

Tasks do backlog:
- `#15`, `#21`, `#22`, `#26`, `#27`

Ordem exata de implementação:
1. Corrigir match por âncora para `(anchor_type, anchor_value)`.
2. Implementar job de canonicalização assíncrona (`DEFER_MERGE` real).
3. Persistir `merge_audit` e `canonical_event_id`.
4. Emitir `EVENT_MERGED(A→B)` no SSE.
5. Implementar tombstone/redirecionamento A->B nos endpoints de evento.
6. Implementar pipeline mínimo de `entity_mentions`.
7. Completar `EntityDelta` e integrar `deltas.py` a updates de evento.

Arquivos-alvo (prováveis):
- `backend/app/workers/organizer.py`
- `backend/app/models/merge.py`
- `backend/app/models/entity_mention.py`
- `backend/app/deltas.py`
- `backend/app/main.py` (endpoint de evento + tombstone)
- `backend/app/celery_app.py` (novos jobs de canonicalização)

Aceite da sprint:
- Evento absorvido aponta para canônico sem 404.
- `merge_audit` é gravado.
- SSE emite `EVENT_MERGED(A→B)`.
- Delta estruturado aparece em update de evento.

## Sprint 5 — APIs MVP + CMS Draft + Feedback Editorial (P2/P3 produto)
Meta:
- Entregar API de produto (Plantão/Evento/Oceano Azul) e fluxo editorial Draft-only.

Tasks do backlog:
- `#23`, `#32`, `#42`, `#43`, `#44`, `#45` (restante)

Ordem exata de implementação:
1. Consolidar scoring (incluindo `trust_penalty`, impacto heurístico, `COVERAGE_LAG` temporal real).
2. Expor endpoints MVP:
   - Plantão
   - Evento (timeline, evidências, deltas)
   - Oceano Azul
3. Integrar CMS Draft-only ao fluxo editorial (endpoint/worker).
4. Implementar thresholds por tipo de campo no payload de draft.
5. Completar Feedback API com action gating e transições válidas.
6. (Se houver front) conectar UI aos endpoints e SSE.

Arquivos-alvo (prováveis):
- `backend/app/scoring/plantao.py`
- `backend/app/scoring/oceano.py`
- `backend/app/main.py` (ou routers novos)
- `backend/app/cms.py`
- `backend/app/api/feedback.py`

Aceite da sprint:
- API expõe as 3 visões do blueprint.
- `POST` de draft cria payload Draft-only consistente.
- Ações editoriais viram `feedback_events` e respeitam gating.

## Sprint 6 — Anti-fragilidade, Observabilidade, Backtest Gate e Testes (P1/P2/P3 qualidade/ops)
Meta:
- Operação confiável, auditável e com gate de qualidade para deploy.

Tasks do backlog:
- `#12`, `#40`, `#41`, `#46`, `#50`

Ordem exata de implementação:
1. Implementar `DATA_STARVATION` real (rolling + calendário) com incidente.
2. Adicionar métricas custom do produto (latências por pool/etapa, backlog, DLQ, yield, merges).
3. Adicionar OpenTelemetry (API + workers).
4. Criar suíte de testes mínimos:
   - unitários (regex/scoring/state/taxonomia)
   - integração/smoke (API/SSE/celery flow mínimo)
5. Implementar replay/backtest gate (crise/normal/marasmo), reaproveitando benchmark do legado.
6. Documentar runbooks finais de incidentes (starvation, DLQ, render travado, regressão SLO).

Referências de reuso (legado):
- `/home/diego/news/extractor/utils.py` (SSRF guard e validação de fonte)
- `/home/diego/news/scripts/benchmark/run_story_matching_benchmark.py`
- `/home/diego/news/tests/test_source_taxonomy.py`
- `/home/diego/news/RUNBOOK_OPERACIONAL_BR_MONITOR.md`

Aceite da sprint:
- Métricas e traces ajudam a diagnosticar filas/pools.
- `DATA_STARVATION` gera incidente real.
- Existe gate de replay antes de deploy.
- Testes mínimos rodam local/CI.

## Dependências críticas entre sprints (não pular)
- Sprint 0 antes da 1:
  - sem isso, Celery/worker pode falhar por task/fila/import.
- Sprint 1 antes da 2:
  - estados/SSE precisam de FAST PATH estável e dados corretos.
- Sprint 2 antes da 4:
  - merge/tombstone depende de SSE e state transitions consistentes.
- Sprint 3 antes da 5:
  - Oceano Azul e CMS draft ficam pobres sem deep/render/evidências completas.
- Sprint 6 roda no final, mas métricas básicas podem ser adicionadas incrementalmente.

## Corte de escopo (se precisar acelerar)
- Manter obrigatório no MVP:
  - P0 completo
  - Sprint 1 completa
  - Sprint 2 completa
  - Sprint 4 (merge/tombstone mínimo)
- Pode simplificar inicialmente:
  - UI rica (Sprint 5)
  - OTel completo (Sprint 6), mantendo Prometheus+logs primeiro
  - backtest gate completo (Sprint 6), desde que já exista coleta de `feedback_events`

## Checklist de preparação para começar Sprint 0
- Instalar `pytest` no ambiente de desenvolvimento.
- Criar branch dedicada de estabilização (`sprint0-runtime-stability`).
- Definir política para alertas na Sprint 0:
  - `stub funcional` (recomendado) ou `dispatch desabilitado`.
- Definir política para fila de draft:
  - queue `nlp` explícita ou reaproveitar queue existente.
