"""MVP UI pages (server-rendered shell + JS fetch/SSE)."""
from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import HTMLResponse

router = APIRouter(tags=["ui"])


BASE_STYLE = """
<style>
:root{
  --bg:#06121d;--bg2:#0b2533;--card:#0f3144;--text:#eaf5fb;--muted:#9ec0d0;
  --line:rgba(255,255,255,.08);--accent:#1dd3b0;--hot:#ff5d5d;--blue:#53b7ff;
}
*{box-sizing:border-box} body{margin:0;font-family:ui-sans-serif,system-ui,sans-serif;color:var(--text);
background:radial-gradient(circle at 10% 0%, #123348 0%, var(--bg) 45%, #040b12 100%)}
.wrap{max-width:1100px;margin:0 auto;padding:24px}
.top{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:18px}
.brand{font-weight:900;letter-spacing:.03em}
.nav a{color:var(--muted);text-decoration:none;padding:8px 10px;border:1px solid var(--line);border-radius:10px}
.nav{display:flex;gap:8px;flex-wrap:wrap}
.grid{display:grid;gap:12px}
.cards{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.card{background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.01));border:1px solid var(--line);border-radius:16px;padding:14px}
.meta{font-size:12px;color:var(--muted);display:flex;gap:8px;flex-wrap:wrap}
.score{font-weight:800;color:var(--accent)}
.hot{border-left:4px solid var(--hot)}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:rgba(255,255,255,.06);font-size:12px}
.anchors{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.anchor{font-size:11px;border:1px solid var(--line);padding:2px 6px;border-radius:999px;color:var(--muted)}
.row{display:flex;gap:12px;align-items:flex-start}
.col{flex:1}
.small{font-size:12px;color:var(--muted)}
pre{white-space:pre-wrap;word-break:break-word;background:#081822;border:1px solid var(--line);padding:12px;border-radius:12px}
button{background:var(--accent);color:#052830;border:none;padding:8px 12px;border-radius:10px;font-weight:700;cursor:pointer}
input{background:#081822;color:var(--text);border:1px solid var(--line);padding:8px 10px;border-radius:10px}
</style>
"""


@router.get("/plantao", include_in_schema=False, response_class=HTMLResponse)
async def plantao_page() -> str:
    return f"""
<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plantão | Radar</title>{BASE_STYLE}</head>
<body><div class="wrap">
  <div class="top"><div class="brand">PLANTÃO</div><div class="nav">
    <a href="/plantao">Plantão</a><a href="/oceano">Oceano Azul</a><a href="/">Dashboard</a>
  </div></div>
  <div class="small" id="status">Conectando SSE...</div>
  <div class="row" style="margin:10px 0 14px">
    <input id="laneFilter" placeholder="lane (ex.: politica)" />
    <input id="statusFilter" placeholder="status (ex.: HOT)" />
    <button id="applyFilter">Aplicar</button>
  </div>
  <div class="grid cards" id="cards"></div>
</div>
<script>
function buildQS(params) {{
  const q = new URLSearchParams();
  Object.entries(params||{{}}).forEach(([k,v])=>{{ if (v !== '' && v !== null && v !== undefined) q.set(k, String(v)); }});
  const s = q.toString();
  return s ? ('?'+s) : '';
}}
async function load() {{
  const lane = document.getElementById('laneFilter').value.trim();
  const status = document.getElementById('statusFilter').value.trim();
  const res = await fetch('/api/plantao'+buildQS({{limit:30,lane,status}}));
  const data = await res.json();
  render(data||[]);
}}
function render(items) {{
  const el = document.getElementById('cards');
  el.innerHTML = items.map(e => `
    <div class="card ${{e.status==='HOT'?'hot':''}}">
      <div class="row"><div class="col"><div class="pill">${{e.lane||'geral'}}</div></div><div class="score">${{Math.round(e.score||0)}}</div></div>
      <h3 style="margin:10px 0 6px;font-size:16px"><a href="/evento/${{e.id}}" style="color:inherit;text-decoration:none">${{e.summary||'Sem resumo'}}</a></h3>
      <div class="meta"><span>${{e.status}}</span><span>OA: ${{Math.round(e.score_oceano_azul||0)}}</span><span>docs: ${{e.doc_count||0}}</span><span>fontes: ${{e.source_count||0}}</span></div>
      <div class="anchors">${{(e.anchors||[]).slice(0,5).map(a=>`<span class='anchor'>${{a.type}}:${{String(a.value).slice(0,18)}}</span>`).join('')}}</div>
      <div class="small" style="margin-top:8px">${{JSON.stringify(e.reasons_json||{{}})}}</div>
    </div>`).join('');
}}
document.getElementById('applyFilter').addEventListener('click', load);
load();
const es = new EventSource('/events/stream');
es.addEventListener('open', ()=> document.getElementById('status').textContent='SSE conectado');
es.addEventListener('error', ()=> document.getElementById('status').textContent='SSE com falha, tentando reconectar...');
es.addEventListener('EVENT_UPSERT', ()=> load());
es.addEventListener('EVENT_STATE_CHANGED', ()=> load());
es.addEventListener('EVENT_MERGED', ()=> load());
</script></body></html>
"""


@router.get("/oceano", include_in_schema=False, response_class=HTMLResponse)
async def oceano_page() -> str:
    return f"""
<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oceano Azul | Radar</title>{BASE_STYLE}</head>
<body><div class="wrap">
  <div class="top"><div class="brand">OCEANO AZUL</div><div class="nav">
    <a href="/plantao">Plantão</a><a href="/oceano">Oceano Azul</a><a href="/">Dashboard</a>
  </div></div>
  <div class="row" style="margin:10px 0 14px">
    <input id="minScore" placeholder="score mínimo" inputmode="decimal" />
    <button id="applyFilter">Aplicar</button>
  </div>
  <div class="grid cards" id="cards"></div>
</div>
<script>
async function load() {{
  const minScore = Number(document.getElementById('minScore').value || 0);
  const res = await fetch('/api/oceano-azul?limit=30&min_score='+encodeURIComponent(String(minScore)));
  const data = await res.json();
  document.getElementById('cards').innerHTML = (data||[]).map(e => `
    <div class="card">
      <div class="row"><div class="pill">${{e.lane||'geral'}}</div><div class="score">${{Math.round(e.score_oceano_azul||0)}}</div></div>
      <h3 style="margin:10px 0 6px;font-size:16px"><a href="/evento/${{e.id}}" style="color:inherit;text-decoration:none">${{e.summary||'Sem resumo'}}</a></h3>
      <div class="meta"><span>Status: ${{e.status}}</span><span>Plantão: ${{Math.round(e.score_plantao||0)}}</span></div>
      <pre>${{JSON.stringify(e.reasons_json||{{}}, null, 2)}}</pre>
    </div>`).join('');
}}
document.getElementById('applyFilter').addEventListener('click', load);
load();
const es = new EventSource('/events/stream');
es.addEventListener('EVENT_UPSERT', ()=> load());
es.addEventListener('EVENT_MERGED', ()=> load());
</script></body></html>
"""


@router.get("/evento/{event_id}", include_in_schema=False, response_class=HTMLResponse)
async def event_page(event_id: int) -> str:
    return f"""
<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evento #{event_id} | Radar</title>{BASE_STYLE}</head>
<body><div class="wrap">
  <div class="top"><div class="brand">EVENTO #{event_id}</div><div class="nav"><a href="/plantao">Plantão</a><a href="/oceano">Oceano Azul</a></div></div>
  <div class="row">
    <div class="col">
      <div class="card"><h3 style="margin-top:0">Detalhes</h3><div id="details"></div></div>
      <div class="card" style="margin-top:12px"><h3 style="margin-top:0">Deltas</h3><pre id="deltas"></pre></div>
      <div class="card" style="margin-top:12px">
        <h3 style="margin-top:0">Ações Editoriais</h3>
        <div class="row" style="align-items:center">
          <button data-action="PAUTAR">Pautar</button>
          <button data-action="SNOOZE">Snooze</button>
          <button data-action="IGNORE">Ignore</button>
        </div>
        <div class="row" style="margin-top:10px;align-items:center">
          <input id="mergeTarget" placeholder="ID canônico p/ merge" inputmode="numeric" />
          <button id="mergeBtn">Merge</button>
        </div>
        <div class="row" style="margin-top:10px;align-items:center">
          <input id="splitDocIds" placeholder="doc_ids p/ split (1,2,3)" />
          <button id="splitBtn">Split</button>
        </div>
        <pre id="actionOut"></pre>
      </div>
      <div class="card" style="margin-top:12px"><h3 style="margin-top:0">Criar Draft CMS</h3><button id="draftBtn">Criar Draft</button><pre id="draftOut"></pre></div>
    </div>
    <div class="col">
      <div class="card"><h3 style="margin-top:0">Docs</h3><div id="docs"></div></div>
      <div class="card" style="margin-top:12px"><h3 style="margin-top:0">Âncoras / Entidades</h3><pre id="anchors"></pre></div>
      <div class="card" style="margin-top:12px"><h3 style="margin-top:0">Histórico de Estado</h3><pre id="states"></pre></div>
      <div class="card" style="margin-top:12px"><h3 style="margin-top:0">Merge Audit</h3><pre id="merges"></pre></div>
      <div class="card" style="margin-top:12px"><h3 style="margin-top:0">Feedback</h3><pre id="feedbacks"></pre></div>
    </div>
  </div>
</div>
<script>
async function load() {{
  const r = await fetch('/api/events/{event_id}');
  const d = await r.json();
  if (d.tombstone) {{
    const meta = d.canonical_event ? ` • ${{d.canonical_event.summary||''}}` : '';
    document.getElementById('details').innerHTML = 'TOMBSTONE → evento canônico <a href="/evento/'+d.canonical_event_id+'">#'+d.canonical_event_id+'</a>' + meta;
    document.getElementById('deltas').textContent = '';
    document.getElementById('docs').innerHTML = '';
    document.getElementById('anchors').textContent = '';
    await loadStateAndMerge();
    return;
  }}
  document.getElementById('details').innerHTML = `<div><b>${{d.event.summary||'Sem resumo'}}</b></div>
    <div class='meta'><span>${{d.event.status}}</span><span>${{d.event.lane||'geral'}}</span><span>P:${{Math.round(d.scores.score_plantao||0)}}</span><span>OA:${{Math.round(d.scores.score_oceano_azul||0)}}</span></div>
    <pre>${{JSON.stringify(d.scores.reasons_json||{{}}, null, 2)}}</pre>`;
  document.getElementById('docs').innerHTML = (d.docs||[]).map(x=>`<div style="padding:8px 0;border-top:1px solid var(--line)"><a href="${{x.url}}" target="_blank" rel="noreferrer">${{x.title||x.url}}</a><div class='small'>v${{x.version_no}} • ${{x.is_primary?'primary':'secondary'}} • ${{x.seen_at}}</div></div>`).join('');
  document.getElementById('anchors').textContent = JSON.stringify({{anchors:d.anchors||[], entities:d.entity_mentions||[]}}, null, 2);
  document.getElementById('deltas').textContent = JSON.stringify(d.deltas||{{}}, null, 2);
  await loadStateAndMerge();
}}
async function loadStateAndMerge() {{
  try {{
    const [f,s,m] = await Promise.all([
      fetch('/api/events/{event_id}/feedback?limit=50').then(r=>r.json()),
      fetch('/api/events/{event_id}/state-history?limit=50').then(r=>r.json()),
      fetch('/api/events/{event_id}/merge-audit?limit=50').then(r=>r.json()),
    ]);
    document.getElementById('feedbacks').textContent = JSON.stringify(f.items||[], null, 2);
    document.getElementById('states').textContent = JSON.stringify(s.items||[], null, 2);
    document.getElementById('merges').textContent = JSON.stringify(m.items||[], null, 2);
  }} catch (e) {{
    document.getElementById('feedbacks').textContent = String(e);
    document.getElementById('states').textContent = String(e);
    document.getElementById('merges').textContent = String(e);
  }}
}}
async function doAction(action, payload) {{
  const r = await fetch('/feedback/{event_id}/action?action='+encodeURIComponent(action), {{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify(payload||{{}})
  }});
  let data = null;
  try {{ data = await r.json(); }} catch (e) {{ data = {{error:String(e)}}; }}
  document.getElementById('actionOut').textContent = JSON.stringify({{ok:r.ok, status:r.status, data}}, null, 2);
  await load();
}}
document.getElementById('draftBtn').addEventListener('click', async () => {{
  const r = await fetch('/cms/draft/{event_id}', {{method:'POST'}});
  document.getElementById('draftOut').textContent = JSON.stringify(await r.json(), null, 2);
}});
document.querySelectorAll('[data-action]').forEach(btn => {{
  btn.addEventListener('click', () => doAction(btn.dataset.action, {{user_id:'ui'}}));
}});
document.getElementById('mergeBtn').addEventListener('click', () => {{
  const target = Number(document.getElementById('mergeTarget').value || 0);
  if (!target) {{
    document.getElementById('actionOut').textContent = JSON.stringify({{error:'Informe target_event_id'}}, null, 2);
    return;
  }}
  doAction('MERGE', {{user_id:'ui', target_event_id: target}});
}});
document.getElementById('splitBtn').addEventListener('click', () => {{
  const raw = document.getElementById('splitDocIds').value || '';
  const doc_ids = raw.split(',').map(x=>Number(String(x).trim())).filter(x=>Number.isInteger(x)&&x>0);
  if (!doc_ids.length) {{
    document.getElementById('actionOut').textContent = JSON.stringify({{error:'Informe doc_ids (ex: 10,11)'}}, null, 2);
    return;
  }}
  doAction('SPLIT', {{user_id:'ui', doc_ids}});
}});
load();
const es = new EventSource('/events/stream');
es.addEventListener('EVENT_UPSERT', (ev)=>{{ try{{const p=JSON.parse(ev.data); if (String(p.id)==='{event_id}') load();}}catch(e){{}} }});
es.addEventListener('EVENT_STATE_CHANGED', (ev)=>{{ try{{const p=JSON.parse(ev.data); if (String(p.event_id)==='{event_id}') load();}}catch(e){{}} }});
es.addEventListener('EVENT_MERGED', (ev)=>{{ try{{const p=JSON.parse(ev.data); if (String(p.from_event_id)==='{event_id}'||String(p.to_event_id)==='{event_id}') load();}}catch(e){{}} }});
</script></body></html>
"""
