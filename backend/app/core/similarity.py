"""Similarity Engine — Blueprint §10.2 and §11.1.

Implements SimHash 64-bit for near-duplicate detection and clustering.
Ported and refined from legacy text_similarity.py.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Iterable, List, Optional

SIMHASH_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "contra", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "na", "nas", "no", "nos", "o", "os", "ou", "para", "pela",
    "pelas", "pelo", "pelos", "por", "que", "sem", "sob", "sobre", "uma", "um",
    "uns", "umas", "daquele", "daquela", "este", "esta", "isso", "esse", "essa"
}

def normalize_text(value: str | None) -> str:
    """Basic normalization for hashing."""
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)

def _build_features(text: str | None) -> List[str]:
    """Tokenize and create 3-shingles for SimHash."""
    norm = normalize_text(text)
    if not norm:
        return []
        
    tokens = [t for t in norm.split() if len(t) >= 3 and t not in SIMHASH_STOPWORDS]
    if not tokens:
        return []
        
    # Shingles provide better structural similarity than just bag of words
    shingles = [" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)]
    # Also include unigrams to ensure some signal for very short texts
    shingles.extend(tokens[:30]) 
    
    return shingles

def compute_simhash64(text: str | None) -> Optional[int]:
    """Compute 64-bit SimHash of the given text."""
    features = _build_features(text)
    if not features:
        return None
        
    v = [0] * 64
    for feature in features:
        # Use blake2b for stable 64-bit hash
        h = int.from_bytes(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big")
        for i in range(64):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1
                
    simhash = 0
    for i in range(64):
        if v[i] >= 0:
            simhash |= (1 << i)
            
    return simhash

def hamming_distance64(a: Optional[int], b: Optional[int]) -> int:
    """Compute Hamming distance between two 64-bit hashes."""
    if a is None or b is None:
        return 64
    # Compute XOR and count set bits
    return (a ^ b).bit_count()

def is_near_duplicate(a: Optional[int], b: Optional[int], threshold: int = 12) -> bool:
    """Determine if two hashes are near-duplicates based on threshold."""
    if a is None or b is None:
        return False
    return hamming_distance64(a, b) <= threshold
