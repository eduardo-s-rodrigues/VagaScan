from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalizar_texto(texto: str) -> str:
    """Remove acentos, normaliza espaços e converte o texto para minúsculas."""
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"\s+", " ", sem_acentos).strip().lower()


def normalizar_url(url: str) -> str:
    """Remove rastreadores e diferenças cosméticas sem alterar o destino principal."""
    if not url.strip():
        return ""
    try:
        partes = urlsplit(url.strip())
        parametros = sorted(
            (chave, valor)
            for chave, valor in parse_qsl(partes.query, keep_blank_values=True)
            if not chave.lower().startswith("utm_") and chave.lower() not in {"ref", "source"}
        )
        caminho = partes.path.rstrip("/") or "/"
        return urlunsplit(
            (partes.scheme.lower(), partes.netloc.lower(), caminho, urlencode(parametros), "")
        )
    except ValueError:
        return url.strip().rstrip("/").lower()
