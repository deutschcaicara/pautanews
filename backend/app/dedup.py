"""Deduplication and similarity logic — Blueprint §11 / §19.

Implements SimHash for near-duplicates and BM25-like comparison for same-event detection.
"""
from __future__ import annotations

import re
import math
import hashlib
from typing import List, Set, Dict

def get_tokens(text: str) -> List[str]:
    """Basic tokenization for similarity algorithms."""
    # Lowercase and remove non-alphanumeric
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text.split()

class SimHash:
    """SimHash implementation for near-duplicate detection (§11.1)."""
    
    def __init__(self, text: str, hash_bits: int = 64):
        self.hash_bits = hash_bits
        self.hash = self._compute_simhash(text)

    def _compute_simhash(self, text: str) -> int:
        tokens = get_tokens(text)
        if not tokens:
            return 0
            
        v = [0] * self.hash_bits
        for token in tokens:
            # MD5 for stability across environments
            token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)
            for i in range(self.hash_bits):
                bit = (token_hash >> i) & 1
                if bit:
                    v[i] += 1
                else:
                    v[i] -= 1
        
        fingerprint = 0
        for i in range(self.hash_bits):
            if v[i] > 0:
                fingerprint |= (1 << i)
        return fingerprint

    def similarity(self, other: SimHash) -> float:
        """Calculate bit similarity (1 - Hamming distance / bits)."""
        x = self.hash ^ other.hash
        hamming_distance = bin(x).count('1')
        return 1.0 - (hamming_distance / self.hash_bits)

def check_event_similarity(text1: str, text2: str) -> float:
    """Lightweight similarity check (Jaccard on tokens) for same-event grouping (§11.2)."""
    set1 = set(get_tokens(text1))
    set2 = set(get_tokens(text2))
    
    if not set1 or not set2:
        return 0.0
        
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union
