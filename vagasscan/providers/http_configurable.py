from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

import requests

from vagasscan.config import Settings
from vagasscan.models import ConsultaVagas, ResultadoBusca, Vaga
from vagasscan.providers.base import ErroProvedor, ProvedorNaoConfigurado, ProvedorVagas
from vagasscan.utils.validation import url_http_segura


class ProvedorHttpConfiguravel(ProvedorVagas):
    """Cliente genérico: envia apenas q/location e não presume contrato de fornecedor."""

    nome = "http_configuravel"

    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        tentativas: int = 2,
    ) -> None:
        self.settings = settings
        self.session = session
        self.sleeper = sleeper
        self.tentativas = max(1, min(tentativas, 2))

    def buscar(self, termo: str, localizacao: str = "") -> list[Vaga]:
        return self.consultar(ConsultaVagas(termo=termo, localizacao=localizacao)).vagas

    def consultar(self, consulta: ConsultaVagas) -> ResultadoBusca:
        self._validar_configuracao()
        if len(consulta.termo.strip()) > 100 or len(consulta.localizacao.strip()) > 100:
            raise ErroProvedor(
                "Termo e localização devem ter no máximo 100 caracteres.",
                codigo="validacao",
            )
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
            resposta = self._requisitar(session, consulta, headers)
        finally:
            if self.session is None:
                session.close()
        status = int(getattr(resposta, "status_code", 0))
        if status == 400:
            raise ErroProvedor(
                "O provedor rejeitou os parâmetros enviados (HTTP 400).",
                codigo="validacao",
            )
        if status == 429:
            raise ErroProvedor(
                "Limite de requisições do provedor atingido (HTTP 429).",
                codigo="limite",
                transitorio=True,
                limite=True,
            )
        if status in {401, 403}:
            raise ErroProvedor(
                f"O provedor recusou a credencial configurada (HTTP {status}).",
                codigo="autenticacao",
            )
        if status in {404, 410}:
            raise ErroProvedor(
                f"O recurso configurado não está disponível (HTTP {status}).",
                codigo="nao_encontrado",
            )
        if status >= 500:
            raise ErroProvedor(
                f"O provedor está temporariamente indisponível (HTTP {status}).",
                codigo="servidor",
                transitorio=True,
            )
        try:
            resposta.raise_for_status()
        except requests.RequestException as exc:
            raise ErroProvedor(f"O provedor respondeu com HTTP {status}.", codigo="http") from exc
        try:
            payload = resposta.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as exc:
            raise ErroProvedor(
                "O provedor retornou uma resposta que não é JSON válido.", codigo="json"
            ) from exc
        itens = self._obter_itens(payload)
        vagas = [self._converter(item) for item in itens]
        total = len(vagas)
        if isinstance(payload, dict):
            with suppress(TypeError, ValueError):
                total = max(0, int(payload.get("count", payload.get("total", total))))
        return ResultadoBusca(
            vagas=vagas,
            pagina=consulta.pagina,
            resultados_por_pagina=consulta.resultados_por_pagina,
            total_aproximado=total,
        )

    def _requisitar(
        self, session: requests.Session, consulta: ConsultaVagas, headers: dict[str, str]
    ) -> Any:
        for tentativa in range(self.tentativas):
            try:
                resposta = session.get(
                    self.settings.api_url,
                    params={"q": consulta.termo, "location": consulta.localizacao},
                    headers=headers,
                    timeout=self.settings.api_timeout,
                )
            except requests.Timeout as exc:
                if tentativa + 1 < self.tentativas:
                    self.sleeper(0.25)
                    continue
                raise ErroProvedor(
                    "O provedor excedeu o tempo limite.",
                    codigo="timeout",
                    transitorio=True,
                ) from exc
            except requests.RequestException as exc:
                if tentativa + 1 < self.tentativas:
                    self.sleeper(0.25)
                    continue
                raise ErroProvedor(
                    "Não foi possível acessar o provedor. Verifique a internet e a configuração.",
                    codigo="conexao",
                    transitorio=True,
                ) from exc
            if (
                int(getattr(resposta, "status_code", 0)) >= 500
                and tentativa + 1 < self.tentativas
            ):
                self.sleeper(0.25)
                continue
            return resposta
        raise ErroProvedor(
            "Não foi possível acessar o provedor.",
            codigo="conexao",
            transitorio=True,
        )

    def _validar_configuracao(self) -> None:
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
                    "JSON inválido: esperada uma lista ou a chave results/items/jobs.",
                    codigo="estrutura",
                )
        else:
            raise ErroProvedor(
                "JSON inválido: formato principal não reconhecido.", codigo="estrutura"
            )
        if not all(isinstance(item, dict) for item in itens):
            raise ErroProvedor("JSON inválido: cada vaga deve ser um objeto.", codigo="estrutura")
        return itens

    def _converter(self, item: dict[str, Any]) -> Vaga:
        titulo = str(item.get("title") or item.get("titulo") or "").strip()
        descricao = str(item.get("description") or item.get("descricao") or "").strip()
        if not titulo or not descricao:
            raise ErroProvedor(
                "JSON inválido: uma vaga não possui título ou descrição.", codigo="estrutura"
            )
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
            link=url_http_segura(
                item.get("redirect_url") or item.get("url") or item.get("link")
            ),
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
