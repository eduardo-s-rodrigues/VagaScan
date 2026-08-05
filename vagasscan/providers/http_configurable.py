from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import requests

from vagasscan.config import Settings
from vagasscan.models import Vaga
from vagasscan.providers.base import ErroProvedor, ProvedorNaoConfigurado, ProvedorVagas


class ProvedorHttpConfiguravel(ProvedorVagas):
    """Cliente genérico para uma URL real informada pelo usuário; não presume API específica."""

    nome = "http_configuravel"

    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self.settings = settings
        self.session = session

    def buscar(self, termo: str, localizacao: str = "") -> list[Vaga]:
        if not self.settings.api_url:
            raise ProvedorNaoConfigurado("JOB_API_URL não está configurada.")
        partes_url = urlsplit(self.settings.api_url)
        if partes_url.scheme not in {"http", "https"} or not partes_url.hostname:
            raise ProvedorNaoConfigurado("JOB_API_URL deve ser uma URL HTTP ou HTTPS válida.")
        if partes_url.username or partes_url.password:
            raise ProvedorNaoConfigurado(
                "JOB_API_URL não pode conter usuário ou senha; use JOB_API_TOKEN."
            )
        if self.settings.api_requires_token and not self.settings.api_token:
            raise ProvedorNaoConfigurado("JOB_API_TOKEN é obrigatório para este provedor.")
        headers = {"Accept": "application/json"}
        if self.settings.api_token:
            valor = self.settings.api_token
            if (
                self.settings.api_token_header.lower() == "authorization"
                and not valor.lower().startswith("bearer ")
            ):
                valor = f"Bearer {valor}"
            headers[self.settings.api_token_header] = valor
        session = self.session or requests.Session()
        try:
            resposta = session.get(
                self.settings.api_url,
                params={"q": termo, "location": localizacao},
                headers=headers,
                timeout=self.settings.api_timeout,
            )
        except requests.Timeout as exc:
            raise ErroProvedor("O provedor excedeu o tempo limite.") from exc
        except requests.RequestException as exc:
            raise ErroProvedor(
                "Não foi possível acessar o provedor. Verifique a internet e a configuração."
            ) from exc
        finally:
            if self.session is None:
                session.close()
        if resposta.status_code == 429:
            raise ErroProvedor("Limite de requisições do provedor atingido (HTTP 429).")
        try:
            resposta.raise_for_status()
        except requests.RequestException as exc:
            raise ErroProvedor(f"O provedor respondeu com HTTP {resposta.status_code}.") from exc
        try:
            payload = resposta.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise ErroProvedor("O provedor retornou uma resposta que não é JSON válido.") from exc
        itens = self._obter_itens(payload)
        return [self._converter(item) for item in itens]

    @staticmethod
    def _obter_itens(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            itens = payload
        elif isinstance(payload, dict):
            itens = next(
                (
                    payload[chave]
                    for chave in ("results", "items", "jobs")
                    if isinstance(payload.get(chave), list)
                ),
                None,
            )
            if itens is None:
                raise ErroProvedor(
                    "JSON inválido: esperada uma lista ou a chave results/items/jobs."
                )
        else:
            raise ErroProvedor("JSON inválido: formato principal não reconhecido.")
        if not all(isinstance(item, dict) for item in itens):
            raise ErroProvedor("JSON inválido: cada vaga deve ser um objeto.")
        return itens

    def _converter(self, item: dict[str, Any]) -> Vaga:
        titulo = str(item.get("title") or item.get("titulo") or "").strip()
        descricao = str(item.get("description") or item.get("descricao") or "").strip()
        if not titulo or not descricao:
            raise ErroProvedor("JSON inválido: uma vaga não possui título ou descrição.")
        empresa = item.get("company") or item.get("empresa") or "Não informada"
        if isinstance(empresa, dict):
            empresa = empresa.get("display_name") or empresa.get("name") or "Não informada"
        local = item.get("location") or item.get("localizacao") or "Não informada"
        if isinstance(local, dict):
            local = local.get("display_name") or local.get("name") or "Não informada"
        return Vaga(
            titulo=titulo,
            empresa=str(empresa),
            localizacao=str(local),
            modalidade=str(item.get("modality") or item.get("modalidade") or "não informada"),
            nivel=str(item.get("level") or item.get("nivel") or "não informado"),
            descricao=descricao,
            link=str(item.get("url") or item.get("link") or ""),
            fonte=self.nome,
            identificador_externo=str(item.get("id") or item.get("external_id") or ""),
            data_publicacao=str(
                item.get("created")
                or item.get("published_at")
                or item.get("data_publicacao")
                or ""
            )
            or None,
        )
