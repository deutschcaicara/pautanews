# TASKS (Backlog técnico) — MVP Radar HARD NEWS + OCEANO AZUL (Fev/2026)
**Regra:** preservar SLO do Plantão e anti‑fragilidade de ingestão. Vetado: embeddings/LLMs/autopublish.

## M0 — Infra e repo
- T0.1: Docker Compose (Postgres, RabbitMQ, Redis opcional, API, Celery workers).
  - Aceite: sobe local com 1 comando.
- T0.2: Observabilidade base (Prometheus metrics + logs JSON).
  - Aceite: painel latência/filas/yield/STARVATION.

## M1 — Data model
- T1.1: Migrações Postgres com tabelas mínimas (sources, snapshots, documents, anchors, events, scores, state, alerts, merge_audit, feedback).
  - Aceite: migração limpa + seeds de exemplo.

## M2 — Source Profile DSL + Scheduler
- T2.1: Validador do sources.fetch_policy_json (schema + defaults seguros).
  - Aceite: rejeita profile inválido.
- T2.2: Scheduler agenda jobs por pool (FAST/RENDER/DEEP) e por tier.
  - Aceite: jobs caem nas filas corretas.

## M3 — FAST_POOL (FAST PATH Plantão)
- T3.1: Fetch robusto (ETag/IMS, SSRF guard, rate‑limit, circuit breaker, snapshot).
- T3.2: Extract (trafilatura) + versioning documents.
- T3.3: Criar/atualizar evento e emitir SSE EVENT_UPSERT ≤ 60s.
  - Aceite: P95 end‑to‑end ≤ 60s em fontes simples.

## M4 — Golden Regex Arsenal + evidence_score
- T4.1: Regex pack (CNPJ/CPF/CNJ/SEI/TCU/PL/atos/valores/datas/links .gov/PDF).
- T4.2: Persistir doc_anchors + doc_evidence_features(evidence_score).
  - Aceite: testes com fixtures reais.

## M5 — HEAVY_RENDER_POOL (SPA)
- T5.1: SPA_API fetch (XHR JSON) quando configurado.
- T5.2: Playwright fallback bloqueando assets + concorrência por domínio.
  - Aceite: não degrada FAST_POOL.

## M6 — DEEP_EXTRACT_POOL (PDF/OCR sob demanda)
- T6.1: pdf extract (pypdf/pdfplumber) + OCR só image‑only.
- T6.2: Update silencioso do evento + recálculo scores.
  - Aceite: background não degrada SLO.

## M7 — Event Builder + DEFER_MERGE + TOMBSTONE
- T7.1: Near‑duplicate (SimHash/MinHash).
- T7.2: Same‑event (BM25/TF‑IDF + janela + entidades).
- T7.3: Merge hard só por âncora; DEFER_MERGE; canonical_event_id + merge_audit.
- T7.4: EVENT_MERGED(A→B) + redirect canônico.
  - Aceite: UI auto‑limpa e link antigo não quebra.

## M8 — Scoring (SCORE_PLANTAO / SCORE_OCEANO_AZUL) + REASONS_CODES
- T8.1: SCORE_PLANTAO + reasons.
- T8.2: SCORE_OCEANO_AZUL + reasons.
  - Aceite: reasons aparecem no Plantão.

## M9 — Estados + gating + QUARANTINE + UNVERIFIED_VIRAL
- T9.1: enum estados + transições.
- T9.2: gating HYDRATING + timeout por pool → PARTIAL_ENRICH.
- T9.3: QUARANTINE estado real + TTL.
- T9.4: UNVERIFIED_VIRAL override anti‑boato → PAUTAR_NAO_VERIFICADO.
  - Aceite: sem spam; sem boato automático.

## M10 — Deltas estruturados
- T10.1: Anchor/Value/Entity/Temporal Delta (UTC no banco).
  - Aceite: tela Evento mostra “o que mudou” sem diff textual.

## M11 — CMS Draft‑only
- T11.1: POST cria Draft com timeline/evidências/proveniência + NewsArticle básico.
- T11.2: thresholds configuráveis por tipo de campo.
  - Aceite: nunca autopublish; campos fracos exigem revisão.

## M12 — Anti‑fragilidade (DATA_STARVATION)
- T12.1: baseline rolling + calendário.
- T12.2: alertas DATA_STARVATION + painel saúde de fontes.
  - Aceite: 200 OK + yield ~0 gera incidente.

## M13 — Feedback + Backtest gate
- T13.1: capturar feedback_events (ignorar/snooze/pautar/merge/split).
- T13.2: batch recalibration fora do clique.
- T13.3: replay datasets (crise/normal/marasmo) + gate CI.
  - Aceite: deploy bloqueia se ruído sobe em marasmo ou SLO degrada.
