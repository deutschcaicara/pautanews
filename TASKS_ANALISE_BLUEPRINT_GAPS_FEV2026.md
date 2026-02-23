# Análise de Aderência ao Blueprint (Fev/2026) — Problemas para Virar Tasks

Data da análise: 2026-02-22

Escopo analisado:
- Projeto atual: `/home/diego/pautanews`
- Blueprint: `BLUEPRINT_FINAL_Radar_Hard_News_Fev2026.md`
- Referência de legado (somente ideias/reuso compatível): `/home/diego/news`

Status desta entrega:
- Apenas análise (sem correções funcionais)
- Arquivo preparado para virar backlog de implementação

## Método usado
- Leitura do blueprint e extração de checklist por seção.
- Revisão do backend (API, workers, scoring, estado, schema/migrations, compose).
- Verificação rápida de integridade:
  - `python3 -m compileall -q backend/app` ✅
  - `pytest -q` ❌ (`pytest` não instalado no ambiente atual)
- Inspeção seletiva do legado `/home/diego/news` para reaproveitamento seguro.

## Resumo executivo
- O projeto já tem boa base estrutural para o MVP (FastAPI + Celery + Postgres + Redis + schema canônico em grande parte + scoring dual + enum de estados + regex + SimHash).
- Porém, há gaps críticos que impedem aderência real ao blueprint:
  - tarefas/filas inexistentes e import quebrado (runtime),
  - scheduler sem respeitar `cadence`,
  - SSE/TOMBSTONE ainda stub,
  - state machine/action gating não integrada,
  - render/deep pools não implementados de fato,
  - observabilidade/anti-fragilidade (`DATA_STARVATION`) ainda placeholder,
  - regras de merge/DEFER_MERGE incompletas.

## O que já está bem encaminhado (não é task prioritária)
- Stack base alinhada (FastAPI, Celery, RabbitMQ, Postgres, Redis): `backend/pyproject.toml`, `docker-compose.yml`
- Modelo de dados canônico MVP em grande parte presente: `backend/app/models/*.py`, `backend/alembic/versions/6fc6b6f59c87_initial_schema.py`
- Índices `pg_trgm` em `documents.title/clean_text`: `backend/app/models/document.py`
- Scoring dual (`SCORE_PLANTAO`, `SCORE_OCEANO_AZUL`) e `reasons_json`: `backend/app/models/score.py`, `backend/app/scoring/*.py`
- Enum de estados com vocabulário do blueprint: `backend/app/models/event.py`
- SimHash e taxonomia (já portados do legado): `backend/app/core/similarity.py`, `backend/app/core/taxonomy.py`

## Backlog de tasks (priorizado)

## Status de execução (2026-02-22, após implementação incremental)
- `Feito/avançado`: P0 quase completo; boa parte de P1/P2/P3 em modo MVP funcional.
- `Parcial`: observabilidade (métricas custom + probe de fila + OTel opcional API/HTTPX/Celery), `DATA_STARVATION` (rolling+calendário heurístico, ainda não baseline de produção persistido), render/deep, scoring avançado, feedback/gating.
- `Feito nesta rodada`: merge/tombstone com reatribuição de `event_docs` e dedupe; `MERGE` manual via Feedback API; SSE polling sem perda por timestamp igual; CI workflow backend; correção do path do `replay_backtest_gate.py`; correção de bug lógico no `fetch` (persistência/extract que não executava por indentação); `SPA_API` contratual MVP + propagação de `snapshot_id`/metadados até `Document`; request configurável para `API/SPA_API` (GET/POST/params/json/headers); filtros de captura XHR no `SPA_HEADLESS`; re-score automático do canônico após merge; `headless`/PDF com imports/fallbacks mais robustos; feeds/rankings filtrando tombstones/expirados por padrão; UI MVP enriquecida com ações editoriais, histórico de estado/merge/feedback e filtros; feed Plantão com `doc_count/source_count`.
- `Pendente forte`: backtest gate acoplado ao CI com dataset/legado/DB acessíveis; hardening final de render/deep em fontes reais; métricas broker/DLQ em produção dependem plugin/infra habilitados (código/compose já preparados); regras editoriais avançadas de `SPLIT` (MVP funcional via `feedback`).
- `Validação local concluída`: `.venv` criada, dependências instaladas, `pytest backend/tests` => `29 passed`.

## P0 — Bloqueadores / Bugs de runtime

1. Corrigir import quebrado em `draft.py` (`EventDoc` importado do módulo errado)
- Problema:
  - `EventDoc` é definido em `backend/app/models/event.py`, mas está sendo importado de `backend/app/models/document.py`.
- Evidência:
  - `backend/app/workers/draft.py:16`
- Impacto:
  - Worker de draft quebra ao importar/executar.
- Task:
  - Ajustar import para `from app.models.event import EventDoc`.

2. Corrigir uso de `asyncio` não importado em `_async_run_drafting` quando Gemini estiver ativo
- Problema:
  - `_async_run_drafting()` usa `asyncio.to_thread(...)`, mas `asyncio` só é importado localmente dentro de `run_drafting()`.
- Evidência:
  - `backend/app/workers/draft.py:37`
  - `backend/app/workers/draft.py:80`
- Impacto:
  - Com `GEMINI_API_KEY` configurada, gera `NameError` e falha o draft.
- Task:
  - Importar `asyncio` no módulo (top-level) ou no escopo de `_async_run_drafting`.

3. Criar/registrar worker de alertas ou remover dispatch até implementação
- Problema:
  - `score.py` envia `app.workers.alerts.run_alerts`, mas não existe `backend/app/workers/alerts.py`.
- Evidência:
  - `backend/app/workers/score.py:110`
  - `backend/app/celery_app.py:64`
  - `backend/app/workers` (arquivo ausente)
- Impacto:
  - Erro de task inexistente em produção.
- Task:
  - Implementar `alerts.py` mínimo com cooldown por transição de estado (Blueprint §13.5), ou desabilitar dispatch temporariamente.

4. Declarar fila `nlp` ou rotear `draft` para fila existente
- Problema:
  - `score.py` envia draft para queue `nlp`, mas `nlp` não está declarada em `celery.conf.task_queues`.
- Evidência:
  - `backend/app/workers/score.py:121`
  - `backend/app/celery_app.py:33`
- Impacto:
  - Roteamento inconsistente / dependência de auto-criação de fila fora do contrato do blueprint.
- Task:
  - Adicionar fila explícita (`nlp`) com route, ou mover draft para `score`/`organize`/nova fila documentada.

5. Corrigir worker `anchors` que chama `run_scoring` com assinatura incompatível
- Problema:
  - `anchors.run_anchor_extraction` chama `run_scoring` com `[doc_id, evidence_score]`, mas `run_scoring` aceita só `event_id`.
- Evidência:
  - `backend/app/workers/anchors.py:33`
  - `backend/app/workers/score.py:25`
- Impacto:
  - Se esse worker for ativado, quebra imediatamente.
- Task:
  - Remover worker placeholder do fluxo/registro ou reimplementar com contrato correto.

## P1 — Aderência crítica ao blueprint (arquitetura/pipeline)

6. Implementar scheduler real respeitando `cadence` por fonte
- Problema:
  - `orchestrator_fetches` dispara todas as fontes a cada minuto; `schedule_fetches()` está `pass`.
- Evidência:
  - `backend/app/workers/orchestrator.py:18`
  - `backend/app/workers/orchestrator.py:25`
  - `backend/app/scheduler.py:38`
- Blueprint:
  - §5 (Scheduler) e §6.1 (`cadence`)
- Impacto:
  - Sobrecarga, viola contrato de ingestão por fonte, risco operacional.
- Task:
  - Implementar decisão por `interval_seconds`/`cron` + persistência de último disparo por fonte.

7. Aplicar pools reais no pipeline (FAST / RENDER / DEEP) em vez de tratar tudo como `extract_fast`
- Problema:
  - `fetch.py` sempre envia para `extract_fast` independentemente da estratégia/pool.
- Evidência:
  - `backend/app/workers/fetch.py:162`
  - `backend/app/workers/fetch.py:165`
- Blueprint:
  - §7 e §9
- Impacto:
  - `HEAVY_RENDER_POOL` e `DEEP_EXTRACT_POOL` existem só nominalmente.
- Task:
  - Roteamento por `profile.pool` + `profile.strategy` para `extract_fast` / `extract_deep` / render path.

8. Implementar estratégias `SPA_API`, `SPA_HEADLESS` e `PDF` no fetch/extract real
- Problema:
  - `fetch.py` não usa `StrategyType` para comportamento específico.
  - `headless.py` e `pdf_extractor.py` existem, mas estão desacoplados do fluxo.
- Evidência:
  - `backend/app/workers/fetch.py:20`
  - `backend/app/workers/fetch.py:64`
  - `backend/app/workers/headless.py:16`
  - `backend/app/workers/pdf_extractor.py:17`
- Blueprint:
  - §6.2, §9.2, §9.3
- Task:
  - Implementar branching por estratégia:
    - `SPA_API`: endpoint JSON/XHR configurado
    - `SPA_HEADLESS`: Playwright + captura XHR/JSON
    - `PDF`: download + `extract_deep`

9. Implementar SSE real com contrato `EVENT_UPSERT`, `EVENT_STATE_CHANGED`, `EVENT_MERGED` (TOMBSTONE)
- Problema:
  - SSE é placeholder e responde um único `ping`.
- Evidência:
  - `backend/app/main.py:367`
  - `backend/app/main.py:369`
- Blueprint:
  - §14
- Impacto:
  - UI realtime do Plantão não existe; sem limpeza via tombstone.
- Task:
  - Implementar stream contínuo (SSE), publisher de eventos e contrato de mensagens.

10. Integrar máquina de estados ao pipeline (estado atual está “solto”)
- Problema:
  - `state_engine.py` existe, mas não é chamado no fluxo `organize/score/feedback`.
  - `event_state` não é persistido em nenhum ponto.
- Evidência:
  - `backend/app/state_engine.py:16`
  - ausência de uso de `EventState` em `backend/app` (somente modelo)
- Blueprint:
  - §13
- Impacto:
  - Sem `HYDRATING/PARTIAL_ENRICH/QUARANTINE/...` efetivos; gating e alertas ficam inválidos.
- Task:
  - Registrar transições em `event_state`, atualizar `events.status` via state engine, emitir SSE por transição.

11. Corrigir timeout de action gating (usando SLO incorreto em vez de 15s/45s)
- Problema:
  - `state_engine` usa `SLO_FAST_PATH_S` e `SLO_RENDER_PATH_S` (60/120) para timeout de hidratação.
- Evidência:
  - `backend/app/state_engine.py:32`
  - `backend/app/config.py:31`
- Blueprint:
  - §13.2 (FAST=15s, RENDER=45s)
- Task:
  - Separar configs de SLO end-to-end e timeout de action gating.

12. Implementar `DATA_STARVATION` de verdade (rolling + calendário) e integrar ao fetch/extract
- Problema:
  - `YieldMonitor` é placeholder; `update_yield()` e `check_starvation()` não fazem nada.
- Evidência:
  - `backend/app/health.py:20`
  - `backend/app/health.py:25`
- Blueprint:
  - §6.3 e §19
- Task:
  - Persistir baseline por fonte (rolling + calendário), detectar colapso de yield com HTTP 200 e abrir incidente/alerta.

13. Implementar alertas por transição de estado + cooldown (em vez de threshold direto de score)
- Problema:
  - `score.py` dispara alertas por score > 70, sem usar `EventAlertState`, sem transição, sem cooldown real.
- Evidência:
  - `backend/app/workers/score.py:108`
  - `backend/app/models/alert.py:33` (modelo existe, sem uso)
- Blueprint:
  - §2, §13.5
- Task:
  - Alerting worker com hash/cooldown em `event_alert_state`, gatilho por `EVENT_STATE_CHANGED`.

## P1 — Bugs de semântica de dados / risco de regressão

14. Corrigir versionamento de documentos RSS (hash atual do feed inteiro causa versões falsas)
- Problema:
  - `extract.py` repassa o `content_hash` do feed bruto para cada item RSS.
  - `organizer.py` usa esse hash para versionar documento por `url`.
- Evidência:
  - `backend/app/workers/extract.py:18`
  - `backend/app/workers/extract.py:66`
  - `backend/app/workers/organizer.py:40`
  - `backend/app/workers/organizer.py:46`
- Impacto:
  - Mudança em qualquer item do feed pode versionar todos os itens indevidamente.
- Task:
  - Calcular hash por item RSS (ex.: `title+link+summary/content`) antes de enviar para organização.

15. Corrigir merge por âncora para considerar `anchor_type` + `anchor_value` (evitar falso merge)
- Problema:
  - Query de match por âncora filtra só `anchor_value`, não `anchor_type`.
- Evidência:
  - `backend/app/workers/organizer.py:95`
  - `backend/app/workers/organizer.py:101`
- Blueprint:
  - §11 (merge hard por âncora determinística igual)
- Impacto:
  - Pode juntar eventos distintos com valores coincidentes em tipos diferentes.
- Task:
  - Fazer match em pares `(anchor_type, anchor_value)` e registrar evidência de merge.

16. Corrigir perda de `is_official` no `SourceProfile` vindo do seed
- Problema:
  - `seed_sources.py` salva `is_official` na tabela `sources`, mas não injeta no `fetch_policy_json`.
  - `get_active_source_profiles()` não reconcilia com a coluna DB.
- Evidência:
  - `backend/app/seeds/seed_sources.py:79`
  - `backend/app/seeds/seed_sources.py:84`
  - `backend/app/scheduler.py:27`
  - `backend/app/schemas/source_profile.py:57`
- Impacto:
  - `profile.is_official` tende a `False` em pipeline/organizer, distorcendo evidência e scoring.
- Task:
  - Injetar `is_official`, `tier`, `lang`, etc. no profile validado a partir da coluna canônica do banco.

17. Corrigir `FetchAttempt.snapshot_hash` (atualmente grava `content_hash`, não `snapshot_hash`)
- Problema:
  - Campo `snapshot_hash` de `fetch_attempts` recebe `content_hash`.
- Evidência:
  - `backend/app/workers/fetch.py:130`
  - `backend/app/workers/fetch.py:141`
  - `backend/app/workers/fetch.py:156`
- Blueprint:
  - §8 (`fetch_attempts.snapshot_hash`)
- Task:
  - Popular `fetch_attempts.snapshot_hash` com o hash do snapshot salvo; se não houver snapshot, deixar `NULL`.

18. Registrar `fetch_attempt` mesmo em resposta 304
- Problema:
  - `return` antecipado em `304 Not Modified` antes da persistência do attempt.
- Evidência:
  - `backend/app/workers/fetch.py:114`
- Blueprint:
  - §8 (`fetch_attempts` para observabilidade)
- Impacto:
  - Observabilidade fica cega para fontes com caching funcional.
- Task:
  - Persistir attempt (status 304, latência, bytes=0) antes de retornar.

19. Corrigir inferência de `lane` usando `profile.source_id` como se fosse editoria
- Problema:
  - `infer_editorial_lane()` recebe `editoria=profile.source_id`.
- Evidência:
  - `backend/app/workers/organizer.py:54`
  - `backend/app/workers/organizer.py:57`
- Impacto:
  - Lanes menos precisas; perda de sinal editorial disponível no seed (`legacy_editoria`).
- Task:
  - Usar `metadata.legacy_editoria` do profile ou coluna própria; manter `source_id` só como ID lógico.

20. Validar/filtrar itens RSS sem `link` para evitar quebra em `Document.url`
- Problema:
  - `extract.py` aceita `entry.get("link")` possivelmente `None`, mas `Document.url` é obrigatório.
- Evidência:
  - `backend/app/workers/extract.py:38`
  - `backend/app/models/document.py:17` (campo `url` não nulo)
- Task:
  - Descartar/normalizar item sem URL antes de enviar para organização.

## P2 — Gaps fortes de blueprint (MVP incompleto)

21. Implementar canonicalização assíncrona + `DEFER_MERGE` completo + `merge_audit`
- Problema:
  - Há “linkagem” de docs em evento existente, mas não existe merge tardio entre eventos, nem tombstone real.
  - `MergeAudit` nunca é persistido.
- Evidência:
  - `backend/app/workers/organizer.py` (sem uso de `MergeAudit`)
  - `backend/app/models/merge.py`
- Blueprint:
  - §11 e §14
- Task:
  - Criar job de canonicalização: `canonical_event_id`, `merge_audit`, SSE `EVENT_MERGED(A→B)`.

22. Implementar `TOMBSTONE` e redirecionamento `A -> B`
- Problema:
  - `canonical_event_id` existe, mas API/UI não tratam eventos absorvidos.
- Evidência:
  - `backend/app/models/event.py:32`
  - ausência de endpoint/event handling no `backend/app/main.py`
- Blueprint:
  - §14
- Task:
  - API deve retornar tombstone/redirecionamento ao consultar evento merged.

23. Completar `SCORE_PLANTAO` e `SCORE_OCEANO_AZUL` com `trust_penalty`, impacto e lag temporal real
- Problema:
  - Scoring atual cobre base, mas faltam componentes explícitos do blueprint.
- Evidência:
  - `backend/app/scoring/plantao.py`
  - `backend/app/scoring/oceano.py`
- Blueprint:
  - §12.1 e §12.2
- Task:
  - Adicionar:
  - `trust_penalty`
  - impacto heurístico fraco (Plantão)
  - `COVERAGE_LAG` temporal (não só booleano “tem/ não tem Tier-1”)

24. Implementar `UNVERIFIED_VIRAL` integrado a flags/event_state/UI
- Problema:
  - Função de checagem existe, mas não é usada; critério também não inclui condição de tier/evidência conforme blueprint.
- Evidência:
  - `backend/app/state_engine.py:47`
- Blueprint:
  - §13.4
- Task:
  - Aplicar override no state/scoring; persistir em `events.flags_json`; expor no feed.

25. Implementar QUARANTINE + TTL -> EXPIRED
- Problema:
  - Existe enum e config TTL, mas não há mecanismo para expiração automática.
- Evidência:
  - `backend/app/models/event.py` (estados)
  - `backend/app/config.py:41`
  - `backend/app/state_engine.py:40`
- Blueprint:
  - §13.3
- Task:
  - Job de sweep por TTL + transição para `EXPIRED` com `event_state`.

26. Completar contrato de deltas estruturados (`EntityDelta` + persistência/uso)
- Problema:
  - `deltas.py` só gera anchor/value/temporal e não é usado no pipeline.
- Evidência:
  - `backend/app/deltas.py:39`
- Blueprint:
  - §15
- Task:
  - Implementar `EntityDelta`, padronizar payload e persistir/expor nos updates de evento.

27. Implementar `entity_mentions` no pipeline
- Problema:
  - Tabela existe, mas não é preenchida.
- Evidência:
  - `backend/app/models/entity_mention.py`
  - ausência de uso em `backend/app/workers`
- Blueprint:
  - §8 e §15 (`EntityDelta`)
- Task:
  - Extrair NER/heurística mínima e persistir `entity_mentions`.

28. Completar Golden Regex Arsenal (sem máscara, horários, links .gov/PDF/DO, normalização)
- Problema:
  - Regex atual cobre subset e sem normalização robusta.
- Evidência:
  - `backend/app/regex_pack.py:9`
- Blueprint:
  - §10
- Task:
  - Adicionar:
  - CNPJ/CPF sem máscara
  - horários
  - links `.gov`, PDF, DO, anexos
  - normalização de moeda/data/hora

29. Usar `DocEvidenceFeature` completo (`has_pdf`, `money_count`, `has_table_like`, `evidence_json`)
- Problema:
  - Organizer só preenche `evidence_score`, `anchors_count`, `has_official_domain`.
- Evidência:
  - `backend/app/workers/organizer.py:82`
  - `backend/app/models/anchor.py:39`
- Blueprint:
  - §8 e §10
- Task:
  - Popular features restantes a partir de texto/URL/PDF parser.

30. Implementar DEEP_EXTRACT real (PDF + tabela + OCR fallback)
- Problema:
  - `pdf_extractor.py` tem fallback OCR com `pass`.
- Evidência:
  - `backend/app/workers/pdf_extractor.py:37`
- Blueprint:
  - §9.3
- Task:
  - Completar OCR fallback para PDFs image-only e integrar com `extract_deep`.

31. Implementar `SPA_HEADLESS` com captura XHR/JSON (não apenas HTML renderizado)
- Problema:
  - `headless.py` retorna `page.content()` mas não captura XHR/JSON.
- Evidência:
  - `backend/app/workers/headless.py:34`
- Blueprint:
  - §6.2 e §9.2
- Task:
  - Instrumentar listeners de network response/request e extrair payloads JSON.

32. Completar API MVP do produto (Plantão / Evento / Oceano Azul)
- Problema:
  - Só existe `/api/events` genérico + dashboard HTML.
- Evidência:
  - `backend/app/main.py`
- Blueprint:
  - §5 (API Service) e §16 (UI MVP)
- Task:
  - Endpoints mínimos:
  - Feed Plantão (reasons, fontes, timeline)
  - Detalhe de evento
  - Ranking Oceano Azul

33. Expor `reasons_json` no feed Plantão
- Problema:
  - `/api/events` retorna score e anchors, mas não retorna `reasons_json`.
- Evidência:
  - `backend/app/main.py` (`/api/events`)
- Blueprint:
  - §12 e §16 (cards com reasons)
- Task:
  - Join com `event_scores` e incluir `reasons_json` no payload.

## P2 — Contrato de ingestão / segurança / operação

34. Tornar `Source Profile DSL` realmente obrigatório nos campos mínimos (ou normalizar defaults no load)
- Problema:
  - Muitos campos mínimos do blueprint estão virando defaults implícitos (`headers`, `observability`, `is_official`, `lang`) em vez de contrato explícito.
- Evidência:
  - `backend/app/schemas/source_profile.py:57`
  - `backend/app/seeds/seed_sources.py:63`
- Blueprint:
  - §6.1
- Task:
  - Definir política:
  - ou exigir campos explícitos no JSON
  - ou aplicar normalização de perfil centralizada e persistir profile enriquecido

35. Garantir User-Agent institucional por profile (sem depender de ausência de header)
- Problema:
  - `SourceProfile.headers` default vazio; seed não preenche `headers`.
- Evidência:
  - `backend/app/schemas/source_profile.py:62`
  - `backend/app/seeds/seed_sources.py:63`
- Blueprint:
  - §2 e §6.1
- Task:
  - Injetar `User-Agent` institucional no seed/normalizador e validar presença.

36. Implementar rate-limit / concurrency per domain / max_bytes / circuit breaker no fetch
- Problema:
  - Campos existem no DSL, mas `fetch.py` usa só `timeout_seconds`.
- Evidência:
  - `backend/app/schemas/source_profile.py:36`
  - `backend/app/workers/fetch.py:98`
- Blueprint:
  - §6.1 e §9.1
- Task:
  - Aplicar limites via Redis/semáforos e streaming com corte por `max_bytes`.

37. Melhorar SSRF guard (IPv6/múltiplos resolves/consistência com legado)
- Problema:
  - `is_ssrf_safe()` usa `socket.gethostbyname()` (IPv4 single result) e é mais fraco que abordagem do legado.
- Evidência:
  - `backend/app/workers/fetch.py:26`
  - Referência legado: `/home/diego/news/extractor/utils.py:2103`
- Blueprint:
  - §2 (SSRF guard)
- Task:
  - Migrar para validação com `getaddrinfo` e bloqueio de qualquer resolve privado/local.

## P2 — Observabilidade / stack / deploy

38. Corrigir `task_routes` do Celery (prefixos não correspondem aos nomes reais)
- Problema:
  - Rotas apontam para `app.workers.fetch_fast.*`, `extract_fast.*`, etc., mas tasks reais estão em `app.workers.fetch.run_fetch`, `app.workers.extract.run_extraction`, etc.
- Evidência:
  - `backend/app/celery_app.py:56`
  - `backend/app/workers/fetch.py:51`
  - `backend/app/workers/extract.py:17`
- Impacto:
  - Config enganosa e potencial erro de roteamento ao remover `queue=` explícito.
- Task:
  - Alinhar `task_routes` com nomes reais ou padronizar módulos/tasks.

39. Alinhar `docker-compose` com a separação de esteiras do blueprint
- Problema:
  - `celery-heavy` mistura `fetch_render` com `extract_deep`; `celery-deep` consome `nlp` não declarada; filas `retry/dead_letter` sem consumidores.
- Evidência:
  - `docker-compose.yml:103`
  - `docker-compose.yml:125`
  - `backend/app/celery_app.py:47`
- Blueprint:
  - §7
- Task:
  - Reorganizar workers por pool/fila e documentar afinidade por esteira.

40. Adicionar OpenTelemetry ao stack e instrumentação básica
- Problema:
  - Blueprint exige OpenTelemetry + Prometheus; projeto tem Prometheus endpoint, mas não há OTel no `pyproject`.
- Evidência:
  - `backend/pyproject.toml`
  - `backend/app/main.py:353`
- Blueprint:
  - §4 e §19
- Task:
  - Adicionar dependências/config OTel (API + workers) com trace IDs em logs.

41. Instrumentar métricas operacionais do blueprint (latências por pool, backlog, DLQ, yield etc.)
- Problema:
  - Existe endpoint `/metrics`, mas sem métricas de domínio do produto.
- Evidência:
  - `backend/app/main.py:353`
  - `backend/app/health.py` (placeholders)
- Blueprint:
  - §19
- Task:
  - Métricas custom:
  - latência por etapa/pool
  - backlog filas/DLQ
  - yield de âncoras/evidence por fonte
  - merges/falsos merges
  - incidentes `DATA_STARVATION`

## P3 — Produto / UX / CMS / feedback (MVP incompleto, mas não bloqueia base)

42. Implementar UI MVP do blueprint (Plantão/Evento/Oceano Azul) além do dashboard placeholder
- Problema:
  - UI atual é dashboard estático/operacional, não a UI editorial descrita.
- Evidência:
  - `backend/app/main.py` (dashboard HTML)
- Blueprint:
  - §16
- Task:
  - Criar telas/rotas com cards, reasons, fontes, timeline, ações e ranking Oceano Azul.

43. Implementar ação de CMS Draft (endpoint/worker integrado ao evento)
- Problema:
  - `cms.py` é utilitário isolado; não há endpoint nem pipeline de criação de draft por ação editorial.
- Evidência:
  - `backend/app/cms.py`
- Blueprint:
  - §17
- Task:
  - Endpoint/worker para “POST cria Draft” com payload derivado do evento canônico.

44. Implementar thresholds por tipo de campo no CMS Draft
- Problema:
  - CMS usa só um `confidence` único (<0.7) e não thresholds por campo/tipo.
- Evidência:
  - `backend/app/cms.py:37`
- Blueprint:
  - §17
- Task:
  - Thresholds separados (pessoa/data/valor/etc.) e marcação granular no draft.

45. Completar Feedback API (validação de evento, mapeamento de ação -> estado, action gating)
- Problema:
  - Endpoint grava feedback, mas não valida existência do evento nem aplica transições.
- Evidência:
  - `backend/app/api/feedback.py:32`
  - `backend/app/api/feedback.py:43`
- Blueprint:
  - §13 e §18
- Task:
  - Criar schema de request/response, validar evento, aplicar gating por estado e registrar `event_state`.

46. Implementar backtest gate / replay de deploy (crise/normal/marasmo)
- Problema:
  - Nenhum replay/backtest gate foi implementado no projeto atual.
- Evidência:
  - Ausente no `backend/app`
- Blueprint:
  - §18
- Task:
  - Pipeline de benchmark/replay antes de deploy com critérios de falha.

## P3 — Qualidade de código / manutenção

47. Remover/alinhar código placeholder duplicado (`workers/anchors.py`) com pipeline real
- Problema:
  - Extração de âncoras acontece em `organizer.py`; `anchors.py` ficou paralelo e desatualizado.
- Evidência:
  - `backend/app/workers/anchors.py`
  - `backend/app/workers/organizer.py`
- Task:
  - Decidir arquitetura final (anchor worker separado ou inline) e apagar/atualizar o outro caminho.

48. Padronizar execução async em tasks Celery (evitar `get_event_loop().run_until_complete`)
- Problema:
  - Vários workers sync usam `asyncio.get_event_loop()`; isso é frágil em processos/threads de worker.
- Evidência:
  - `backend/app/workers/orchestrator.py:22`
  - `backend/app/workers/fetch.py:57`
  - `backend/app/workers/score.py:28`
  - `backend/app/workers/draft.py:38`
  - `backend/app/cms.py:52`
- Task:
  - Trocar para `asyncio.run(...)` (ou pool/runner dedicado) e padronizar helper.

49. Preencher campos de `Document` que hoje ficam subutilizados (`published_at`, `modified_at`, `lang`, `canonical_url`, `snapshot_id`)
- Problema:
  - Schema está pronto, mas pipeline persiste só subset mínimo.
- Evidência:
  - `backend/app/models/document.py`
  - `backend/app/workers/organizer.py:63`
- Blueprint:
  - §8
- Task:
  - Popular metadados a partir do extract/feedparser/trafilatura/snapshot.

50. Criar testes mínimos de contrato para o novo backend (API, scoring, state engine, taxonomia)
- Problema:
  - Projeto atual não traz suíte de testes equivalente ao legado.
- Evidência:
  - ausência de pasta `tests/` neste repositório
  - `pytest` indisponível no ambiente (execução não realizada)
- Task:
  - Criar testes unitários e smoke tests de API/worker.

## Reuso do projeto antigo (`/home/diego/news`) — sugestões compatíveis com o blueprint

1. Reuso imediato (baixo risco)
- `source_taxonomy` e testes:
  - Já foi portado quase integralmente para `backend/app/core/taxonomy.py`
  - Reaproveitar suíte: `/home/diego/news/tests/test_source_taxonomy.py`
- Similaridade (SimHash):
  - Base já portada para `backend/app/core/similarity.py`
  - Referência: `/home/diego/news/extractor/text_similarity.py`

2. Reuso recomendado (médio risco, grande valor)
- SSRF/safe URL validation mais robusta:
  - `/home/diego/news/extractor/utils.py:2103`
- Heurísticas de validação de fonte/quality:
  - constantes e scoring em `/home/diego/news/extractor/utils.py:1968`
  - regras de avaliação em `/home/diego/news/extractor/utils.py:2962`
- Backtest/benchmark de matching (ótimo ponto de partida para §18):
  - `/home/diego/news/scripts/benchmark/run_story_matching_benchmark.py`

3. Reuso operacional
- Runbook base para incidentes/ops (adaptar ao novo stack e vocabulário):
  - `/home/diego/news/RUNBOOK_OPERACIONAL_BR_MONITOR.md`

## Sequência sugerida de execução (para depois)
- Fase 1 (estabilização): tasks P0 + P1 (runtime, scheduler, filas, state/SSE mínimo)
- Fase 2 (pipeline real): render/deep, `DATA_STARVATION`, merge/tombstone, scoring completo
- Fase 3 (produto): APIs MVP/UI/CMS/feedback/backtest gate
- Fase 4 (observabilidade e hardening): OTel, métricas, runbooks, testes
