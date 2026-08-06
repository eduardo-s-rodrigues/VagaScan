from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from vagasscan.models import ConsultaVagas, Vaga
from vagasscan.providers import ProvedorAdzuna, ProvedorDemonstracao, ProvedorHttpConfiguravel
from vagasscan.utils.validation import url_http_segura

WEB_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=WEB_ROOT / "templates")
templates.env.globals["url_http_segura"] = url_http_segura


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self.clock = clock

    def _bucket(self, scope: str, key: str, window_seconds: int) -> deque[float]:
        now = self.clock()
        bucket = self.events[(scope, key)]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        return bucket

    def blocked(self, scope: str, key: str, limit: int, window_seconds: int) -> bool:
        return len(self._bucket(scope, key, window_seconds)) >= limit

    def record(self, scope: str, key: str, window_seconds: int) -> None:
        self._bucket(scope, key, window_seconds).append(self.clock())

    def allow(self, scope: str, key: str, limit: int, window_seconds: int) -> bool:
        bucket = self._bucket(scope, key, window_seconds)
        if len(bucket) >= limit:
            return False
        bucket.append(self.clock())
        return True

    def reserve(self, rules: list[RateRule]) -> int:
        """Reserva todos os limites de forma atômica ou devolve o tempo de espera."""
        now = self.clock()
        buckets: list[tuple[RateRule, deque[float]]] = []
        waits: list[float] = []
        for rule in rules:
            bucket = self.events[(rule.scope, rule.key)]
            while bucket and bucket[0] <= now - rule.window_seconds:
                bucket.popleft()
            buckets.append((rule, bucket))
            if len(bucket) >= rule.limit:
                waits.append(rule.window_seconds - (now - bucket[0]))
            if rule.cooldown_seconds and bucket:
                remaining = rule.cooldown_seconds - (now - bucket[-1])
                if remaining > 0:
                    waits.append(remaining)
        if waits:
            return max(1, math.ceil(max(waits)))
        for _, bucket in buckets:
            bucket.append(now)
        return 0


@dataclass(frozen=True, slots=True)
class RateRule:
    scope: str
    key: str
    limit: int
    window_seconds: int
    cooldown_seconds: int = 0


class ConsultaLimitadaError(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "Você realizou várias buscas em sequência. "
            f"Tente novamente em {retry_after} segundos."
        )
        self.retry_after = retry_after


def client_key(request: Request) -> str:
    host = request.client.host if request.client else "local"
    secret = request.app.state.client_key_secret
    return hmac.new(secret, host.encode("utf-8"), hashlib.sha256).hexdigest()


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return str(token)


async def validar_csrf(request: Request) -> Any:
    form = await request.form()
    recebido = str(form.get("csrf_token") or "")
    esperado = str(request.session.get("csrf_token") or "")
    if not esperado or not secrets.compare_digest(recebido, esperado):
        raise HTTPException(status_code=403, detail="Formulário expirado ou inválido.")
    return form


def exigir_admin(request: Request) -> None:
    if not request.session.get("admin"):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


def flash(request: Request, message: str, category: str = "success") -> None:
    key = hashlib.sha256(csrf_token(request).encode("utf-8")).hexdigest()
    messages = request.app.state.flash_messages
    if len(messages) >= 1000:
        messages.pop(next(iter(messages)))
    messages[key] = {"message": message, "category": category}


def contexto(request: Request, **values: Any) -> dict[str, Any]:
    token = csrf_token(request)
    flash_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    data = {
        "request": request,
        "settings": request.app.state.settings,
        "authenticated": bool(request.session.get("admin")),
        "private_navigation": request.url.path.startswith("/dashboard"),
        "csrf_token": token,
        "flash": request.app.state.flash_messages.pop(flash_key, None),
    }
    data.update(values)
    return data


def texto_limitado(value: Any, name: str, maximum: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{name} é obrigatório.")
    if len(text) > maximum:
        raise ValueError(f"{name} deve ter no máximo {maximum} caracteres.")
    return text


def inteiro_limitado(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, number))


def consulta_da_requisicao(request: Request) -> ConsultaVagas:
    query = request.query_params
    distancia_raw = str(query.get("distancia") or "").strip()
    distancia = inteiro_limitado(distancia_raw, 5, 1, 100) if distancia_raw else None
    return ConsultaVagas(
        termo=texto_limitado(query.get("termo"), "Termo", 100, required=True),
        localizacao=texto_limitado(query.get("localizacao"), "Localização", 100),
        pagina=inteiro_limitado(query.get("pagina"), 1, 1, 100),
        resultados_por_pagina=inteiro_limitado(
            query.get("resultados_por_pagina"),
            request.app.state.settings.adzuna_results_per_page,
            1,
            50,
        ),
        remoto=str(query.get("remoto") or "").lower() in {"1", "true", "on", "sim"},
        tipo_contrato=str(query.get("tipo_contrato") or ""),
        jornada=str(query.get("jornada") or ""),
        ordenacao=str(query.get("ordenacao") or "relevance"),
        distancia_km=distancia,
        pais=request.app.state.settings.adzuna_country,
    )


def provedor(request: Request, nome: str, *, privado: bool = False) -> Any:
    settings = request.app.state.settings
    if nome == "demonstracao":
        return ProvedorDemonstracao()
    if nome == "http" and privado:
        return ProvedorHttpConfiguravel(settings)
    if nome != "adzuna":
        raise ValueError("Provedor inválido.")
    return ProvedorAdzuna(settings, session=request.app.state.adzuna_session)


def vaga_do_formulario(form: Any, *, fonte: str = "manual") -> Vaga:
    return Vaga(
        titulo=texto_limitado(form.get("titulo"), "Título", 200, required=True),
        empresa=texto_limitado(form.get("empresa"), "Empresa", 200) or "Não informada",
        localizacao=texto_limitado(form.get("localizacao"), "Localização", 200)
        or "Não informada",
        modalidade=texto_limitado(form.get("modalidade"), "Modalidade", 100)
        or "não informada",
        nivel=texto_limitado(form.get("nivel"), "Nível", 100) or "não informado",
        descricao=texto_limitado(
            form.get("descricao"), "Descrição", 20_000, required=True
        ),
        link=url_http_segura(texto_limitado(form.get("link"), "Link", 2048)),
        fonte=fonte,
    )
