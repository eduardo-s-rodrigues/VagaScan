from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit


def validar_data_iso(valor: str | None, nome_campo: str, *, opcional: bool = False) -> str | None:
    """Valida uma data civil no formato AAAA-MM-DD e devolve o valor normalizado."""
    if valor is None or not str(valor).strip():
        if opcional:
            return None
        raise ValueError(f"{nome_campo} é obrigatória.")
    texto = str(valor).strip()
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError as exc:
        raise ValueError(f"{nome_campo} inválida. Use AAAA-MM-DD.") from exc


def url_http_segura(valor: str | None) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    try:
        partes = urlsplit(texto)
    except ValueError:
        return ""
    if partes.scheme not in {"http", "https"} or not partes.hostname:
        return ""
    if partes.username or partes.password:
        return ""
    return texto
