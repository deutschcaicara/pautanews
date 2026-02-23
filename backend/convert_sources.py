import yaml
from pathlib import Path
from urllib.parse import urlparse

# Path to legacy sources
legacy_sources_path = Path("/home/diego/news/bootstrap/config/sources.yaml")

with open(legacy_sources_path, "r") as f:
    data = yaml.safe_dump(yaml.safe_load(f), default_flow_style=False)
    # Actually just load it
    f.seek(0)
    sources_data = yaml.safe_load(f)

sources = sources_data.get("sources", [])
print(f"Total sources found: {len(sources)}")

# Map priority to tier
priority_map = {"S0": 1, "S1": 2, "S2": 3}

# Map type to strategy
type_map = {"rss": "RSS", "watch": "HTML"}

converted = []
for s in sources:
    name = s.get("name")
    url = s.get("url")
    stype = s.get("type")
    editoria = s.get("editoria")
    priority = s.get("priority", "S2")
    
    tier = priority_map.get(priority, 3)
    strategy = type_map.get(stype, "HTML")
    domain = urlparse(url).hostname if url else "unknown"
    
    source_id = name.lower().replace(" ", "_").replace("-", "_")
    
    # Policy JSON structure
    policy = {
        "source_id": source_id,
        "source_domain": domain,
        "tier": tier,
        "pool": "FAST_POOL",
        "strategy": strategy,
        "endpoints": {"feed" if strategy == "RSS" else "latest": url},
        "cadence": {"interval_seconds": 600 if tier == 1 else 1800 if tier == 2 else 3600},
        "limits": {"rate_limit_req_per_min": 5},
    }
    
    converted.append({
        "domain": domain,
        "name": name,
        "tier": tier,
        "is_official": ".gov.br" in domain or ".leg.br" in domain or ".jus.br" in domain,
        "fetch_policy_json": policy
    })

print(f"Sample source: {converted[0]}")
