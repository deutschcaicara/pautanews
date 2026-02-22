# BLUEPRINT TÉCNICO FINAL (TRAVADO) — Radar de Pautas de HARD NEWS + OCEANO AZUL (Fev/2026)

## 0) Contrato semântico (VOCABULÁRIO FIXO)
Este documento **proíbe sinonímia** no código e na documentação. Use exatamente estes termos:

- **Plantão**: fluxo principal de **hard news em tempo real** (rápido, acionável).
- **Oceano Azul**: fluxo de **pauta por evidência determinística** (documentos/atos/IDs), com “janela de furo” e/ou ganho factual.
- **SCORE_PLANTAO**: pontuação para ranqueamento do Plantão (substitui qualquer termo como “hotness”).
- **SCORE_OCEANO_AZUL**: pontuação para ranqueamento do Oceano Azul (substitui “anomaly/ocean score”).
- **EVIDENCE_MULTIPLIER**: multiplicador baseado em evidências/âncoras determinísticas (PDF/DO/SEI/CNJ/CNPJ etc.).
- **COVERAGE_LAG**: atraso de cobertura por fontes Tier‑1 após evidência aparecer.
- **REASONS_CODES**: chaves estáveis em JSON para explicar o score e as transições.
- **UNVERIFIED_VIRAL**: flag de “explodindo / não verificado” (nunca “confirmado”).
- **DEFER_MERGE**: regra de “tolerar split no início; canonicalizar depois”.
- **TOMBSTONE**: evento absorvido (merge tardio) + broadcast de limpeza (UI/Slack).
- **DATA_STARVATION**: alarme de “200 OK mas yield de âncoras/evidências ~0”.

---

## 1) Objetivo do produto
Sistema assíncrono que capta, normaliza, compara e pontua eventos factuais em tempo real para uma redação.

### 1.1 Saídas (duas vias)
- **Plantão (HARD NEWS):** detectar o que está **explodindo agora** e entregar cards acionáveis em segundos.
- **Oceano Azul (EVIDÊNCIA):** detectar fatos com **prova determinística** ainda subcobertos por Tier‑1.

### 1.2 SLOs (P95, end‑to‑end)
- Trigger rápido → evento visível no Plantão (UI): **≤ 60s**
- Baseline RSS → evento visível no Plantão: **≤ 120s**
- Oficiais/PDF (deep extract) → update no evento/Oceano Azul: **≤ 5 min** quando aplicável  
*(Deep Extract pode continuar rodando; o update aparece assim que pronto.)*

---

## 2) Invariantes (não negociáveis)
- Event‑driven, assíncrono, **CPU‑first**.
- LLM pesado **proibido** no Fast Path.
- Versionamento obrigatório (documentos, estados, merges).
- Evidência determinística > similaridade textual.
- Alertas **somente** por transição de estado (anti‑spam).
- Operação ética/auditável:
  - User‑Agent institucional + ETag/If‑Modified‑Since/Last‑Modified
  - **sem bypass hostil de WAF / proxies residenciais / evasão**

---

## 3) Non‑goals (VETADO no MVP base)
- Embeddings/pgvector (Fase 2; feature flag).
- Autopublish no CMS (sempre Draft).
- OCR como padrão (OCR apenas se PDF image‑only).
- Qualquer LLM no caminho crítico.
- “Search cluster” dedicado (OpenSearch etc.) no MVP (só se métricas exigirem).

---

## 4) Stack travada do MVP (SEM OPÇÕES)
- **Python 3.11+**
- **API:** FastAPI + Uvicorn
- **Mensageria/Workers:** **RabbitMQ + Celery**
- **Banco canônico:** PostgreSQL 15+
- **Redis (recomendado):** locks leves / rate‑limit / cooldown (não é fonte da verdade)
- **Real‑time:** SSE (Server‑Sent Events) na API
- **HTTP fetch:** httpx (async)
- **Parse HTML:** selectolax
- **Extração texto:** trafilatura
- **Headless SPA:** Playwright (Python)
- **PDF:** pypdf + pdfplumber
- **OCR (último recurso):** pytesseract
- **Observabilidade:** OpenTelemetry + Prometheus metrics

---

## 5) Arquitetura macro (processos)
No MVP, tudo pode rodar como processos Celery + 1 API:

1) **API Service**
   - endpoints Plantão/Evento/Oceano Azul
   - SSE (eventos em tempo real)
   - integração CMS (Draft‑only)
2) **Scheduler**
   - lê `sources.fetch_policy_json`
   - agenda jobs por cadência/tier/pool
3) **Workers FAST_POOL**
4) **Workers HEAVY_RENDER_POOL**
5) **Workers DEEP_EXTRACT_POOL**
6) **Scoring + State Engine** (pode ser parte de workers)

---

## 6) Contrato de ingestão (Source Profile DSL) — obrigatório
Config por fonte em `sources.fetch_policy_json` (JSON). Nada hardcoded.

### 6.1 Campos mínimos
- `source_id`, `source_domain`
- `tier` (1..3), `is_official` (bool), `lang`
- `pool`: `FAST_POOL | HEAVY_RENDER_POOL | DEEP_EXTRACT_POOL`
- `strategy`: `RSS | HTML | API | SPA_API | SPA_HEADLESS | PDF`
- `endpoints`: `{ feed | latest | search | api }`
- `headers`: incluir User‑Agent institucional
- `cadence`: `{ cron | interval_seconds }`
- `limits`: `{ rate_limit_req_per_min, concurrency_per_domain, timeout_seconds, max_bytes }`
- `observability`: `{ starvation_window_hours, yield_keys, baseline_rolling, calendar_profile }`

### 6.2 Regras SPA (fixas)
- **SPA_API**: capturar endpoint JSON/XHR configurado no profile (preferido).
- **SPA_HEADLESS**: Playwright apenas como fallback, bloqueando assets e capturando XHR/JSON.

### 6.3 Anti‑fragilidade: DATA_STARVATION (fixo)
Se fonte Oficial/Tier‑1 retorna HTTP 200 continuamente e yield de âncoras/evidências colapsa para ~0 por janela:
- abrir incidente “DATA_STARVATION: possível quebra de layout/API”
- baseline de yield = **rolling + calendário** (dias úteis/horários), nunca fixo.

---

## 7) Pools / filas Celery (separação de esteiras)
Filas mínimas:
- `fetch_fast`, `fetch_render`, `fetch_deep`
- `extract_fast`, `extract_deep`
- `organize`, `score`, `alerts`
- `retry`, `dead_letter`

SLAs internos:
- FAST_POOL: fetch+extract ≤ 2s quando possível
- RENDER_POOL: ≤ 15s (concorrência por domínio limitada)
- DEEP_POOL: background (minutos/horas), nunca bloqueia Plantão

---

## 8) Modelo de dados (canônico) — mínimo MVP
Tabelas mínimas:
- `sources(id, domain, tier, is_official, fetch_policy_json, enabled, created_at, updated_at)`
- `fetch_attempts(id, source_id, url, status_code, error_class, latency_ms, bytes, attempted_at, pool, snapshot_hash)`
- `snapshots(id, url, fetched_at, headers_json, body_ref, content_hash, snapshot_hash)`
- `documents(id, url, canonical_url, title, author, published_at, modified_at, clean_text, lang, content_hash, version_no, snapshot_id, created_at)`
- `doc_anchors(id, doc_id, anchor_type, anchor_value, evidence_ptr, confidence)`
- `doc_evidence_features(doc_id, evidence_score, has_pdf, has_official_domain, anchors_count, money_count, has_table_like, evidence_json)`
- `entity_mentions(id, doc_id, entity_key, label, span_json, evidence_ptr, confidence)`
- `events(id, created_at, updated_at, canonical_event_id NULL, status, flags_json, first_seen_at, last_seen_at)`
- `event_docs(event_id, doc_id, source_id, seen_at, is_primary)`
- `event_scores(event_id, SCORE_PLANTAO, SCORE_OCEANO_AZUL, reasons_json, computed_at)`
- `event_state(event_id, status, status_reason, updated_at)`
- `event_alert_state(event_id, last_alert_hash, last_alert_at, cooldown_until)`
- `alerts(id, event_id, channel, payload_json, sent_at, status)`
- `merge_audit(id, from_event_id, to_event_id, reason_code, evidence_json, created_at)`
- `feedback_events(id, event_id, action, actor, payload_json, created_at)`

Índices mínimos:
- `doc_anchors(anchor_type, anchor_value)`
- `events(status, last_seen_at)`
- `event_scores(SCORE_PLANTAO)` e `event_scores(SCORE_OCEANO_AZUL)`
- `pg_trgm` em `documents.clean_text` e `documents.title`

---

## 9) Pipeline (do fetch ao evento)
### 9.1 FAST PATH (Plantão não espera DEEP/RENDER)
1) Fetch (httpx) com ETag/IMS + SSRF guard + rate‑limit + circuit breaker + snapshot
2) Extract (trafilatura) → document versionado
3) Golden Regex (âncoras/evidence features) no texto disponível
4) Event Builder cria/atualiza evento (associação leve)
5) Scoring mínimo: SCORE_PLANTAO + reasons_json mínimo
6) Estado → `HYDRATING` e emitir SSE `EVENT_UPSERT` no Plantão

### 9.2 HEAVY_RENDER_POOL (SPA)
- `SPA_API`: chamar endpoint JSON e extrair dados/texto
- `SPA_HEADLESS`: Playwright bloqueando assets e capturando XHR/JSON

### 9.3 DEEP_EXTRACT_POOL (PDF/DO/SEI)
- baixar com max_bytes/timeout
- extrair texto/tabelas (pypdf/pdfplumber)
- OCR somente se image‑only
- atualizar documento/evento; recalcular scores; gerar update

---

## 10) Golden Regex Arsenal (mínimo obrigatório)
Extrair/normalizar:
- CNPJ/CPF (com/sem máscara)
- CNJ/processo, SEI, TCU/acórdão
- PL/PEC
- atos (portaria/decreto/resolução) n/ano
- valores R$ (normalizar)
- datas/horários (normalizar)
- links .gov / PDF / DO / anexos
Persistir `doc_anchors` + `doc_evidence_features(evidence_score)`.

---

## 11) Organização do evento (dedup + DEFER_MERGE)
- Near‑duplicate: SimHash/MinHash
- Same‑event (probabilístico): BM25/TF‑IDF + entidades + janela (+ geo quando houver)
- Merge hard: **somente** por âncora determinística igual
- **DEFER_MERGE:** tolerar splits nos primeiros minutos; canonicalização assíncrona

Canonicalização:
- set `canonical_event_id` no evento absorvido
- registrar `merge_audit`
- emitir `EVENT_MERGED(A→B)` (TOMBSTONE)

---

## 12) Scoring (dual) + reasons_json (contrato estável)
### 12.1 SCORE_PLANTAO
- tier_weight
- velocity (docs/min + aceleração)
- diversidade de fontes
- impacto heurístico (sinal fraco, nunca gatilho isolado)
- trust_penalty
- decay exponencial

### 12.2 SCORE_OCEANO_AZUL
- EVIDENCE_MULTIPLIER (âncoras fortes + PDF/DO)
- COVERAGE_LAG (Tier‑1 ainda não cobriu)
- trust_penalty (reduzido quando evidência forte)

`reasons_json`: usar REASONS_CODES estáveis (ex.: `PLANTAO_VELOCITY_SPIKE`, `OCEANO_EVIDENCE_PDF`, `OCEANO_COVERAGE_LAG`).

---

## 13) Máquina de estados + Action Gating + Override
### 13.1 Enum de estados (fixo)
`NEW, HYDRATING, PARTIAL_ENRICH, FAILED_ENRICH, QUARANTINE, HOT, MERGED, IGNORED, EXPIRED`

### 13.2 Action Gating
Em `HYDRATING`:
- bloqueado: “PAUTAR_VERIFICADO (schema completo)” e “MERGE_MANUAL”
- permitido: abrir fontes, copiar link+headline, monitorar, snooze, ignorar

Timeout por pool:
- FAST: 15s
- RENDER: 45s
Estourou timeout → `PARTIAL_ENRICH` (UI destrava e permite “PAUTAR_NAO_VERIFICADO”).

### 13.3 QUARANTINE + TTL
- QUARANTINE é estado real (zona cinzenta).
- TTL configurável (padrão 15 min).  
Se TTL expira sem ação humana → `EXPIRED` (ou “IGNORED_BY_TIMEOUT” se preferir manter separado).

### 13.4 Override UNVERIFIED_VIRAL (anti‑boato)
Exibir no Plantão como UNVERIFIED_VIRAL somente se:
- velocity extrema AND (tier alto OR diversidade alta OR evidência mínima)
Ação: **PAUTAR_NAO_VERIFICADO** (Draft minimalista; sem schema SEO automático).

### 13.5 Alertas
- Somente por transição de estado + cooldown.

---

## 14) Contrato real‑time (SSE) + TOMBSTONE
Eventos SSE:
- `EVENT_UPSERT`
- `EVENT_STATE_CHANGED`
- `EVENT_MERGED(A→B)`

TOMBSTONE:
- UI remove card A e destaca B
- redirecionamento A → B (sem 404)
- Slack/Teams: follow‑up no thread (opcional MVP, mas contrato pronto)

---

## 15) Deltas estruturados (“o que mudou”)
JSON por evento:
- `AnchorDelta`
- `ValueDelta` (R$, contagens)
- `EntityDelta` (NER, confidence)
- `TemporalDelta` (agenda)

TemporalDelta:
- persistir UTC no banco
- front converte TZ
- suporta anulação/adiamento (previous_time/new_time)

---

## 16) UI (MVP)
- **Plantão:** cards ranqueados por SCORE_PLANTAO; reasons; fontes; mini‑timeline; ações (monitorar/snooze/ignorar/pautar).
- **Evento:** timeline; evidências; comparação factual por fonte; deltas.
- **Oceano Azul:** ranking por SCORE_OCEANO_AZUL; evidência destacada; lag Tier‑1; filtros.

---

## 17) CMS (Draft‑only)
- POST cria Draft
- Conteúdo: timeline + evidências + proveniência + NewsArticle básico
- Threshold de confiança configurável por tipo de campo (pessoa/data/valor)
- Plugins fora do MVP: Trends, FactCheck schema

---

## 18) Feedback + Backtest gate
- Toda ação editorial gera `feedback_event`.
- Recalibração pesada roda em batch (fora do clique).
- Gate de deploy: replay em dias de crise/normal/marasmo; falhar se ruído sobe em marasmo ou SLO degrada.

---

## 19) Observabilidade e Runbooks
Métricas:
- latência por pool/etapa, backlog filas, DLQ
- erros por domínio, 4xx/5xx, timeouts
- yield de âncoras/evidence_score por fonte
- merges e falsos merges (via feedback)
- incidentes DATA_STARVATION
Runbooks:
- fonte bloqueando, starvation, DLQ crescendo, render pool travando, regressão de SLO
