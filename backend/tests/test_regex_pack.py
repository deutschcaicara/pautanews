from app.regex_pack import extract_anchors, compute_evidence_score


def test_extracts_normalized_cnpj_cpf_and_links() -> None:
    text = """
    Empresa XPTO CNPJ 12.345.678/0001-99 e CPF 123.456.789-00.
    Veja https://www.gov.br/saude/pt-br/assuntos/noticias/nota e anexo https://exemplo.com/doc.pdf
    Valor R$ 1.234,56 em 22/02/2026 às 14:35.
    """
    anchors = extract_anchors(text)
    pairs = {(a["type"], a["value"]) for a in anchors}
    assert ("CNPJ", "12345678000199") in pairs
    assert ("CPF", "12345678900") in pairs
    assert any(t == "LINK_GOV" for t, _ in pairs)
    assert any(t == "PDF" for t, _ in pairs)
    assert ("VALOR", "BRL:1234.56") in pairs
    assert ("DATA", "2026-02-22") in pairs
    assert ("HORA", "14:35") in pairs


def test_evidence_score_counts_unique_anchors() -> None:
    anchors = [
        {"type": "CNPJ", "value": "123", "ptr": ""},
        {"type": "CNPJ", "value": "123", "ptr": ""},
        {"type": "CNJ", "value": "x", "ptr": ""},
        {"type": "PDF", "value": "https://a/b.pdf", "ptr": ""},
    ]
    score = compute_evidence_score(anchors)
    assert score > 0
    # duplicate CNPJ should not double count
    assert score < 10

