import re
from urllib.parse import urlparse

MEDIA_GROUP_HOST_SUFFIXES: dict[str, tuple[str, ...]] = {
    "google_news": ("news.google.com",),
    "uol": ("uol.com.br", "operamundi.uol.com.br"),
    "globo": ("globo.com",),
    "folha": ("folha.uol.com.br", "redir.folha.com.br"),
    "estadao": ("estadao.com.br",),
    "cnn_brasil": ("cnnbrasil.com.br",),
    "metropoles": ("metropoles.com",),
    "r7": ("r7.com",),
    "terra": ("terra.com.br",),
    "jp": ("jp.com.br",),
    "infomoney": ("infomoney.com.br",),
    "exame": ("exame.com",),
    "forum": ("revistaforum.com.br",),
    "brasil_de_fato": ("brasildefato.com.br",),
    "intercept": ("intercept.com.br",),
    "apublica": ("apublica.org",),
    "nexo": ("nexojornal.com.br",),
    "nodal": ("nodal.am",),
}

MAINSTREAM_MEDIA_GROUPS = {
    "google_news",
    "uol",
    "globo",
    "folha",
    "estadao",
    "cnn_brasil",
    "metropoles",
    "r7",
    "terra",
    "jp",
    "infomoney",
    "exame",
}

GENERIC_SOURCE_GROUPS = {
    "",
    "mainstream",
    "oficial",
    "independente",
    "especializado",
    "outros",
    "legacy",
}

OFFICIAL_HOST_SUFFIXES = (
    "gov.br",
    "senado.leg.br",
    "camara.leg.br",
    "stf.jus.br",
    "stj.jus.br",
    "tse.jus.br",
    "mpf.mp.br",
    "agenciabrasil.ebc.com.br",
    "ibge.gov.br",
    "fiocruz.br",
)

COMPETITOR_HOST_SUFFIXES = (
    "news.google.com",
    "g1.globo.com",
    "globo.com",
    "uol.com.br",
    "folha.uol.com.br",
    "redir.folha.com.br",
    "estadao.com.br",
    "cnnbrasil.com.br",
    "metropoles.com",
    "infomoney.com.br",
    "exame.com",
    "terra.com.br",
    "r7.com",
    "operamundi.uol.com.br",
)

INDEPENDENT_HOST_SUFFIXES = (
    "revistaforum.com.br",
    "brasildefato.com.br",
    "tvtnews.com.br",
    "diariodocentrodomundo.com.br",
    "cartacapital.com.br",
    "apublica.org",
    "intercept.com.br",
    "nexojornal.com.br",
    "poder360.com.br",
    "nodal.am",
)

SPECIALIZED_HOST_SUFFIXES = (
    "jota.info",
    "conjur.com.br",
)

EDITORIAL_LANE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "justica": ("stf", "stj", "tse", "justica", "tribunal", "mpf", "ministerio publico", "operacao"),
    "politica": ("politica", "congresso", "senado", "camara", "planalto", "presidente", "eleicao"),
    "economia": ("economia", "mercado", "bolsa", "selic", "copom", "inflacao", "fiscal", "orcamento"),
    "seguranca": ("seguranca", "policia", "crime", "faccao", "prisao", "violencia"),
    "saude": ("saude", "sus", "hospital", "anvisa", "vacin", "epidemia"),
    "educacao": ("educacao", "mec", "enem", "fies", "sisu", "universidade", "escola", "professor", "aluno"),
    "internacional": ("itamaraty", "onu", "mercosul", "internacional", "g20", "g7"),
    "meio_ambiente": ("meio ambiente", "clima", "amazonia", "desmatamento", "queimada", "ibama", "icmbio", "cop30"),
    "direitos_humanos": ("direitos humanos", "racismo", "violencia policial", "feminicidio", "indigena", "quilombola"),
    "tecnologia": ("tecnologia", "ia", "inteligencia artificial", "chip", "software"),
    "infraestrutura": ("rodovia", "ferrovia", "porto", "aeroporto", "saneamento", "obras", "mobilidade urbana", "energia"),
    "agronegocio": ("agronegocio", "agro", "safra", "conab", "soja", "milho", "pecuaria", "carne"),
    "esportes": ("futebol", "campeonato", "rodada", "gol", "time", "partida", "olimpiada", "olimpíada", "copa"),
    "entretenimento": ("bbb", "reality", "famoso", "celebridade", "novela", "streaming", "serie", "série", "show"),
    "cultura": ("cultura", "filme", "teatro", "musica", "literatura"),
    "opiniao": ("opiniao", "editorial", "coluna", "artigo"),
}

KNOWN_EDITORIAL_LANES = set(EDITORIAL_LANE_KEYWORDS.keys()) | {"hardnews"}


def normalize_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def host_matches_any(host: str, suffixes: tuple[str, ...]) -> bool:
    host_lc = normalize_text(host)
    if not host_lc:
        return False
    for suffix in suffixes:
        suffix_lc = normalize_text(suffix)
        if host_lc == suffix_lc or host_lc.endswith(f".{suffix_lc}"):
            return True
    return False


def infer_source_class(source_name: str, source_url: str, current_class: str = "") -> str:
    normalized_current = normalize_text(current_class)
    if normalized_current in {"primary", "competitor", "independent", "specialized"}:
        return normalized_current

    host = normalize_text(urlparse(str(source_url or "")).hostname or "")
    if host_matches_any(host, OFFICIAL_HOST_SUFFIXES):
        return "primary"
    if host_matches_any(host, SPECIALIZED_HOST_SUFFIXES):
        return "specialized"
    if host_matches_any(host, COMPETITOR_HOST_SUFFIXES):
        return "competitor"
    if host_matches_any(host, INDEPENDENT_HOST_SUFFIXES):
        return "independent"

    norm = normalize_text(f"{source_name} {source_url}")
    if any(token in norm for token in ("poder360", "jota", "conjur")):
        return "specialized"
    if any(token in norm for token in ("uol", "folha", "globo", "g1", "estadao", "cnn brasil", "metropoles", "opera mundi", "r7", "terra")):
        return "competitor"
    if any(token in norm for token in ("revista forum", "brasil de fato", "intercept", "apublica", "nexo", "nodal")):
        return "independent"
    if any(token in norm for token in ("tribunal", "ministerio", "camara", "senado", "prefeitura", "governo")):
        return "primary"
    return "other"


def infer_source_group(
    source_name: str,
    source_url: str,
    source_class: str,
    explicit_group: str = "",
) -> str:
    explicit_group_norm = normalize_text(explicit_group)
    host = normalize_text(urlparse(str(source_url or "")).hostname or "")

    host_group = ""
    host_group_len = -1
    for group, suffixes in MEDIA_GROUP_HOST_SUFFIXES.items():
        for suffix in suffixes:
            suffix_norm = normalize_text(suffix)
            if not suffix_norm:
                continue
            if host == suffix_norm or host.endswith(f".{suffix_norm}"):
                if len(suffix_norm) > host_group_len:
                    host_group = group
                    host_group_len = len(suffix_norm)

    if host_group:
        if explicit_group_norm and explicit_group_norm not in GENERIC_SOURCE_GROUPS and explicit_group_norm != host_group:
            return explicit_group_norm
        return host_group
    if explicit_group_norm:
        return explicit_group_norm

    source_name_norm = normalize_text(source_name)
    keyword_groups = {
        "uol": ("uol", "universo online", "opera mundi", "operamundi"),
        "globo": ("globo", "g1", "valor economico", "oglobo"),
        "folha": ("folha", "folha de s paulo"),
        "estadao": ("estadao", "o estado de s paulo"),
        "cnn_brasil": ("cnn brasil",),
        "metropoles": ("metropoles",),
        "r7": ("r7", "record"),
        "terra": ("terra",),
        "jp": ("jovem pan", "jp.com"),
        "infomoney": ("infomoney",),
        "exame": ("exame",),
        "forum": ("revista forum",),
        "brasil_de_fato": ("brasil de fato",),
        "nodal": ("nodal",),
    }
    for group, tokens in keyword_groups.items():
        if any(token in source_name_norm for token in tokens):
            return group

    source_class_norm = normalize_text(source_class)
    if source_class_norm == "primary":
        return "oficial"
    if source_class_norm == "competitor":
        return "mainstream"
    if source_class_norm == "independent":
        return "independente"
    if source_class_norm == "specialized":
        return "especializado"
    if source_class_norm == "legacy":
        return "legacy"
    return "outros"


def infer_editorial_lane(
    *,
    explicit_lane: str | None = None,
    editoria: str | None = None,
    topic: str | None = None,
    title: str | None = None,
    snippet: str | None = None,
    source_scope: str | None = None,
) -> str:
    lane = normalize_text(explicit_lane)
    if lane in KNOWN_EDITORIAL_LANES:
        return lane

    topic_norm = normalize_text(topic).replace(" ", "_")
    topic_candidate = topic_norm if topic_norm in KNOWN_EDITORIAL_LANES else ""

    editoria_norm = normalize_text(editoria).replace(" ", "_")
    editoria_candidate = editoria_norm if editoria_norm in KNOWN_EDITORIAL_LANES else ""

    text = normalize_text(f"{title or ''} {snippet or ''}")
    lane_hits: dict[str, int] = {}
    for lane_name, keywords in EDITORIAL_LANE_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits > 0:
            lane_hits[lane_name] = hits
    if lane_hits:
        priority_order = {
            "justica": 4,
            "politica": 3,
            "economia": 3,
            "seguranca": 3,
            "saude": 2,
            "educacao": 2,
            "internacional": 2,
            "meio_ambiente": 2,
        }
        return max(
            lane_hits.keys(),
            key=lambda lane_name: (lane_hits[lane_name], priority_order.get(lane_name, 1)),
        )

    if topic_candidate and topic_candidate != "geral":
        return topic_candidate
    if editoria_candidate and editoria_candidate != "geral":
        return editoria_candidate

    scope_norm = normalize_text(source_scope)
    if scope_norm in {"federal", "estadual", "municipal"}:
        return "politica"
    if scope_norm == "internacional":
        return "internacional"
    return "geral"
