"""Golden Regex Arsenal — Blueprint §10.

Extracts normalized anchors (CNPJ, CNJ, PL, SEI etc.) from text.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Any

# Regex patterns per Blueprint §10 + Legacy Intelligence
PATTERNS = {
    "CNPJ": r"\b(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})\b",
    "CPF": r"\b(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})\b",
    "CNJ": r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b",
    "SEI": r"\b\d{5}\.\d{6}/\d{4}-\d{2}\b",
    "TCU": r"Acórdão\s+(\d+/\d+)",
    "PL": r"\b(?:PL|PEC|PLP|PLR)\s+\d+(?:/\d+)?\b",
    "ATO": r"\b(?:Portaria|Decreto|Resolução|Instrução Normativa)\s+(?:nº\s+)?\d+/\d+\b",
    "VALOR": r"R\$\s*[\d.]+(?:,\d{2})?\b",
    "DATA": r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    "HORA": r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b",
}
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)

HARDNEWS_KEYWORDS = {
    "stf", "stj", "tse", "congresso", "senado", "camara", "governo", "presidente",
    "ministerio", "policia federal", "operacao", "prisao", "decreto", "portaria",
    "licitacao", "justica", "fiscal", "selic", "copom", "anvisa", "sus", "itamaraty",
    "mercosul", "onu", "planalto", "pgr", "agu", "tcu", "cgu"
}

SOFT_NOISE_KEYWORDS = {
    "bbb", "big brother", "famoso", "celebridade", "entretenimento", "fofoca",
    "setlist", "show", "reality", "carnaval", "futebol", "gol", "horoscopo", "loteria"
}

def extract_anchors(text: str) -> List[Dict[str, Any]]:
    """Apply regex pack to extract normalized anchors."""
    anchors = []
    text_lc = text.lower()
    seen = set()

    def _normalize(anchor_type: str, raw_value: str) -> str:
        value = str(raw_value or "").strip()
        if anchor_type in {"CNPJ", "CPF"}:
            return re.sub(r"\D+", "", value)
        if anchor_type == "VALOR":
            cleaned = value.upper().replace("R$", "").strip().replace(".", "").replace(",", ".")
            try:
                return f"BRL:{float(cleaned):.2f}"
            except Exception:
                return value
        if anchor_type == "DATA":
            m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", value)
            if m:
                d, mo, y = m.groups()
                year = int(y)
                if year < 100:
                    year += 2000
                try:
                    return datetime(year, int(mo), int(d)).strftime("%Y-%m-%d")
                except Exception:
                    return value
        if anchor_type in {"PL", "ATO", "TCU"}:
            return re.sub(r"\s+", " ", value.upper()).strip()
        if anchor_type in {"LINK_GOV", "PDF"}:
            return value.rstrip(".,;)]}>").lower()
        return value

    # 1. Structural Anchors
    for anchor_type, pattern in PATTERNS.items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            normalized_value = _normalize(anchor_type, match.group(0))
            dedup_key = (anchor_type, normalized_value, match.start())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            anchors.append({
                "type": anchor_type,
                "value": normalized_value,
                "ptr": text[max(0, match.start()-30) : min(len(text), match.end()+30)]
            })

    # 1b. Link anchors (.gov / PDF / anexos) — minimum blueprint coverage
    for match in URL_RE.finditer(text):
        raw_url = match.group(0)
        normalized_url = _normalize("LINK_GOV", raw_url)
        if ".gov." in normalized_url or normalized_url.endswith(".gov.br") or ".leg.br" in normalized_url or ".jus.br" in normalized_url:
            anchors.append({
                "type": "LINK_GOV",
                "value": normalized_url,
                "ptr": text[max(0, match.start()-30) : min(len(text), match.end()+30)]
            })
        if ".pdf" in normalized_url:
            anchors.append({
                "type": "PDF",
                "value": _normalize("PDF", raw_url),
                "ptr": text[max(0, match.start()-30) : min(len(text), match.end()+30)]
            })
            
    # 2. HardNews Signals (Keywords)
    for kw in HARDNEWS_KEYWORDS:
        if kw in text_lc:
            # We don't save every keyword as an anchor to avoid bloat, 
            # but we could save them as 'SIGNAL' type for scoring
            pass

    return anchors

def compute_evidence_score(anchors: List[Dict[str, Any]]) -> float:
    """Heuristic evidence scoring based on anchors found (§10)."""
    score = 0.0
    weights = {
        "CNPJ": 1.5, "CNJ": 2.0, "SEI": 1.2, "TCU": 2.0,
        "PL": 1.5, "ATO": 1.0, "VALOR": 0.5, "DATA": 0.2, "HORA": 0.2,
        "LINK_GOV": 0.8, "PDF": 1.2, "CPF": 1.2
    }
    seen_values = set()
    for anchor in anchors:
        if anchor["value"] not in seen_values:
            score += weights.get(anchor["type"], 0.1)
            seen_values.add(anchor["value"])
            
    return min(score, 15.0) # Scaled up evidence score
