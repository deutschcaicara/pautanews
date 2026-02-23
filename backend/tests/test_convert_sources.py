from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "convert_sources.py"
_SPEC = importlib.util.spec_from_file_location("convert_sources", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
conv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(conv)


def test_convert_legacy_source_row_rss_generates_fast_pool_profile() -> None:
    item = conv.convert_legacy_source_row(
        {
            "name": "Senado - RSS Noticias",
            "type": "rss",
            "url": "https://www12.senado.leg.br/noticias/rss",
            "editoria": "politica",
            "priority": "S0",
        }
    )
    assert item is not None
    policy = item["fetch_policy_json"]
    assert policy["strategy"] == "RSS"
    assert policy["pool"] == "FAST_POOL"
    assert "feed" in policy["endpoints"]
    assert policy["metadata"]["legacy_editoria"] == "politica"


def test_convert_legacy_source_row_pdf_uses_deep_pool() -> None:
    item = conv.convert_legacy_source_row(
        {
            "name": "DOU PDF",
            "type": "watch",
            "url": "https://example.com/diario.pdf",
            "priority": "S1",
        }
    )
    assert item is not None
    policy = item["fetch_policy_json"]
    assert policy["strategy"] == "PDF"
    assert policy["pool"] == "DEEP_EXTRACT_POOL"


def test_convert_legacy_source_row_api_like_url_uses_api_strategy() -> None:
    item = conv.convert_legacy_source_row(
        {
            "name": "TCU - Acórdãos",
            "type": "watch",
            "url": "https://pesquisa.apps.tcu.gov.br/rest/publico/base/acordao/pesquisa",
            "priority": "S0",
            "editoria": "economia",
        }
    )
    assert item is not None
    policy = item["fetch_policy_json"]
    assert policy["strategy"] == "API"
    assert policy["pool"] == "FAST_POOL"
    assert "api" in policy["endpoints"]
    assert "api_contract" in policy["metadata"]


def test_convert_legacy_source_row_dou_uses_spa_headless_override() -> None:
    item = conv.convert_legacy_source_row(
        {
            "name": "Diário Oficial da União",
            "type": "watch",
            "url": "https://www.in.gov.br/leitura-digital",
            "priority": "S0",
            "editoria": "politica",
        }
    )
    assert item is not None
    policy = item["fetch_policy_json"]
    assert policy["strategy"] == "SPA_HEADLESS"
    assert policy["pool"] == "HEAVY_RENDER_POOL"
    assert "headless_capture" in policy["metadata"]


def test_convert_legacy_sources_preserves_same_domain_distinct_endpoints() -> None:
    converted = conv.convert_legacy_sources(
        [
            {"name": "A", "type": "watch", "url": "https://x.example.com/a", "priority": "S2"},
            {"name": "B", "type": "watch", "url": "https://x.example.com/b", "priority": "S0"},
        ]
    )
    assert len(converted) == 2


def test_convert_legacy_sources_deduplicates_same_source_url() -> None:
    converted = conv.convert_legacy_sources(
        [
            {"name": "A", "type": "watch", "url": "https://x.example.com/a", "priority": "S2"},
            {"name": "A", "type": "watch", "url": "https://x.example.com/a", "priority": "S2"},
        ]
    )
    assert len(converted) == 1


def test_validate_converted_profiles_passes_for_basic_rows() -> None:
    converted = conv.convert_legacy_sources(
        [
            {
                "name": "Planalto - Noticias",
                "type": "rss",
                "url": "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias/RSS",
                "editoria": "politica",
                "priority": "S0",
            }
        ]
    )
    errors = conv.validate_converted_profiles(converted)
    assert errors == []
