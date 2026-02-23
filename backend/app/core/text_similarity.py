import hashlib
import re
import unicodedata
from typing import Iterable


SIMHASH_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "contra",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "entre",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "pela",
    "pelas",
    "pelo",
    "pelos",
    "por",
    "que",
    "sem",
    "sob",
    "sobre",
    "uma",
    "um",
    "uns",
    "umas",
}

SENTENCE_SPLIT_RE = re.compile(r"(?:\n+|(?<=[\.\!\?])\s+)")


def normalize_fulltext(value: str | None) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonical_text_for_hash(value: str | None) -> str:
    text = normalize_fulltext(value).lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)


def text_sha256(value: str | None) -> str | None:
    normalized = canonical_text_for_hash(value)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _build_simhash_features(value: str | None) -> list[str]:
    corpus = canonical_text_for_hash(value)
    if not corpus:
        return []
    tokens = [token for token in corpus.split() if len(token) >= 3 and token not in SIMHASH_STOPWORDS]
    if not tokens:
        return []
    if len(tokens) < 3:
        return tokens
    shingles = [" ".join(tokens[idx : idx + 3]) for idx in range(len(tokens) - 2)]
    # Keeps some unigram signal to avoid overfitting on very short bodies.
    shingles.extend(tokens[:24])
    return shingles


def compute_simhash64(value: str | None) -> int | None:
    features = _build_simhash_features(value)
    if not features:
        return None
    weights = [0] * 64
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        feature_hash = int.from_bytes(digest, "big", signed=False)
        for bit in range(64):
            if (feature_hash >> bit) & 1:
                weights[bit] += 1
            else:
                weights[bit] -= 1
    simhash = 0
    for bit, weight in enumerate(weights):
        if weight >= 0:
            simhash |= 1 << bit
    return simhash


def simhash_prefix12(simhash: int | None) -> int | None:
    if simhash is None:
        return None
    return int((simhash >> 52) & 0xFFF)


def to_signed_bigint(value: int | None) -> int | None:
    if value is None:
        return None
    normalized = int(value) & ((1 << 64) - 1)
    if normalized >= (1 << 63):
        return normalized - (1 << 64)
    return normalized


def to_unsigned_bigint(value: int | None) -> int | None:
    if value is None:
        return None
    return int(value) & ((1 << 64) - 1)


def hamming_distance64(a: int | None, b: int | None) -> int:
    if a is None or b is None:
        return 64
    return (to_unsigned_bigint(a) ^ to_unsigned_bigint(b)).bit_count()


def split_sentences(value: str | None, *, max_sentences: int = 160) -> list[str]:
    text = normalize_fulltext(value)
    if not text:
        return []
    chunks = SENTENCE_SPLIT_RE.split(text)
    sentences: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        sentence = re.sub(r"\s+", " ", str(chunk or "").strip())
        if len(sentence) < 30:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        sentences.append(sentence[:600])
        if len(sentences) >= max_sentences:
            break
    return sentences


def normalize_sentence(
    sentence: str,
    *,
    stopwords: Iterable[str] | None = None,
    min_token_len: int = 3,
) -> str:
    if not sentence:
        return ""
    stopword_set = {str(token).strip().lower() for token in (stopwords or SIMHASH_STOPWORDS)}
    raw = canonical_text_for_hash(sentence)
    tokens = [token for token in raw.split() if len(token) >= min_token_len and token not in stopword_set]
    return " ".join(tokens).strip()
