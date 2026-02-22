"""Golden Regex Arsenal — Blueprint §10.

Extracts normalized anchors (CNPJ, CNJ, PL, SEI etc.) from text.
"""
import re
from typing import Dict, List, Any

# Regex patterns per Blueprint §10
PATTERNS = {
    "CNPJ": r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
    "CPF": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "CNJ": r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b",
    "SEI": r"\b\d{5}\.\d{6}/\d{4}-\d{2}\b",
    "TCU": r"Acórdão\s+(\d+/\d+)",
    "PL": r"(?:PL|PEC|PLP)\s+\d+(?:/\d+)?",
    "ATO": r"(?:Portaria|Decreto|Resolução)\s+(?:nº\s+)?\d+/\d+",
    "VALOR": r"R\$\s*[\d.]+(?:,\d{2})?",
}

def extract_anchors(text: str) -> List[Dict[str, Any]]:
    """Apply regex pack to extract normalized anchors."""
    anchors = []
    for anchor_type, pattern in PATTERNS.items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            anchors.append({
                "type": anchor_type,
                "value": match.group(0),
                "ptr": text[max(0, match.start()-20) : min(len(text), match.end()+20)]
            })
    return anchors

def compute_evidence_score(anchors: List[Dict[str, Any]]) -> float:
    """Heuristic evidence scoring based on anchors found."""
    score = 0.0
    weights = {
        "CNPJ": 1.0, "CNJ": 1.5, "SEI": 1.0, "TCU": 2.0,
        "PL": 1.0, "ATO": 0.5, "VALOR": 0.2
    }
    for anchor in anchors:
        score += weights.get(anchor["type"], 0.1)
    return min(score, 10.0)
