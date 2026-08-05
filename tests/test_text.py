from vagasscan.utils.text import normalizar_texto, normalizar_url


def test_normalizar_texto_remove_acentos_espacos_e_caixa() -> None:
    assert normalizar_texto("  Análise   de DADOS  ") == "analise de dados"


def test_normalizar_url_remove_rastreadores_e_fragmento() -> None:
    url = "HTTPS://EXAMPLE.COM/vaga/?utm_source=x&id=10#detalhes"
    assert normalizar_url(url) == "https://example.com/vaga?id=10"


def test_normalizar_url_ordena_parametros_para_deduplicacao() -> None:
    primeira = normalizar_url("https://example.com/vaga?b=2&a=1")
    segunda = normalizar_url("https://example.com/vaga?a=1&b=2")
    assert primeira == segunda
