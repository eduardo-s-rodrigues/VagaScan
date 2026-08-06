from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

import requests

from vagasscan.analyzers.modality import classificar_modalidade, modalidade_corresponde
from vagasscan.config import Settings
from vagasscan.models import ConsultaVagas, ResultadoBusca, Vaga
from vagasscan.providers.base import ErroProvedor, ProvedorNaoConfigurado, ProvedorVagas
from vagasscan.utils.text import normalizar_texto
from vagasscan.utils.validation import url_http_segura

PAISES_ADZUNA = {
    "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb", "in", "it",
    "mx", "nl", "nz", "pl", "sg", "us", "za",
}
ORDENACOES_ADZUNA = {"default", "hybrid", "date", "salary", "relevance"}


class ProvedorAdzuna(ProvedorVagas):
    nome = "adzuna"
    base_url = "https://api.adzuna.com/v1/api/jobs"

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
        return self.consultar(
            ConsultaVagas(
                termo=termo,
                localizacao=localizacao,
                resultados_por_pagina=self.settings.adzuna_results_per_page,
                pais=self.settings.adzuna_country,
            )
        ).vagas

    def consultar(self, consulta: ConsultaVagas) -> ResultadoBusca:
        self._validar(consulta)
        params: dict[str, Any] = {
            "app_id": self.settings.adzuna_app_id,
            "app_key": self.settings.adzuna_app_key,
            "results_per_page": consulta.resultados_por_pagina,
            "what": consulta.termo.strip(),
            "where": consulta.localizacao.strip(),
        }
        if consulta.ordenacao:
            params["sort_by"] = consulta.ordenacao
        if consulta.distancia_km is not None and consulta.localizacao.strip():
            params["distance"] = consulta.distancia_km
        if consulta.tipo_contrato:
            params[consulta.tipo_contrato] = "1"
        if consulta.jornada:
            params[consulta.jornada] = "1"

        url = f"{self.base_url}/{consulta.pais}/search/{consulta.pagina}"
        session = self.session or requests.Session()
        try:
            resposta = self._requisitar(session, url, params)
        finally:
            if self.session is None:
                session.close()

        status = int(getattr(resposta, "status_code", 0))
        if status != 200:
            self._erro_http(status)
        try:
            payload = resposta.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as exc:
            raise ErroProvedor(
                "A Adzuna retornou uma resposta que não é JSON válido.",
                codigo="json",
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ErroProvedor(
                "A Adzuna retornou uma estrutura de dados inesperada.", codigo="estrutura"
            )
        total = self._inteiro_seguro(payload.get("count"), len(payload["results"]))
        vagas: list[Vaga] = []
        erros: list[str] = []
        for indice, item in enumerate(payload["results"], 1):
            if not isinstance(item, dict):
                erros.append(f"Resultado {indice} ignorado por formato inválido.")
                continue
            vagas.append(self._converter(item))
        return ResultadoBusca(
            vagas=vagas,
            pagina=consulta.pagina,
            resultados_por_pagina=consulta.resultados_por_pagina,
            total_aproximado=total,
            erros=erros,
        )

    def _requisitar(self, session: requests.Session, url: str, params: dict[str, Any]) -> Any:
        ultimo_erro: Exception | None = None
        for tentativa in range(self.tentativas):
            try:
                resposta = session.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=self.settings.adzuna_timeout,
                )
            except requests.Timeout as exc:
                ultimo_erro = exc
                if tentativa + 1 < self.tentativas:
                    self.sleeper(0.25)
                    continue
                raise ErroProvedor(
                    "A consulta à Adzuna excedeu o tempo limite.",
                    codigo="timeout",
                    transitorio=True,
                ) from exc
            except requests.RequestException as exc:
                ultimo_erro = exc
                if tentativa + 1 < self.tentativas:
                    self.sleeper(0.25)
                    continue
                raise ErroProvedor(
                    "Não foi possível acessar a Adzuna. Verifique sua conexão.",
                    codigo="conexao",
                    transitorio=True,
                ) from exc
            if int(getattr(resposta, "status_code", 0)) >= 500 and tentativa + 1 < self.tentativas:
                self.sleeper(0.25)
                continue
            return resposta
        raise ErroProvedor(
            "Não foi possível acessar a Adzuna.", codigo="conexao", transitorio=True
        ) from ultimo_erro

    def _validar(self, consulta: ConsultaVagas) -> None:
        if not self.settings.adzuna_app_id or not self.settings.adzuna_app_key:
            raise ProvedorNaoConfigurado(
                "A integração com a Adzuna ainda não está configurada. Preencha "
                "ADZUNA_APP_ID e ADZUNA_APP_KEY no arquivo .env."
            )
        if consulta.pais not in PAISES_ADZUNA:
            raise ErroProvedor("País inválido para a Adzuna.", codigo="validacao")
        if len(consulta.termo.strip()) > 100 or len(consulta.localizacao.strip()) > 100:
            raise ErroProvedor(
                "Termo e localização devem ter no máximo 100 caracteres.",
                codigo="validacao",
            )
        if not 1 <= consulta.pagina <= 100:
            raise ErroProvedor("A página deve ficar entre 1 e 100.", codigo="validacao")
        if not 1 <= consulta.resultados_por_pagina <= 50:
            raise ErroProvedor(
                "A quantidade de resultados deve ficar entre 1 e 50.", codigo="validacao"
            )
        if consulta.ordenacao not in ORDENACOES_ADZUNA:
            raise ErroProvedor("Ordenação inválida.", codigo="validacao")
        if consulta.tipo_contrato not in {"", "permanent", "contract"}:
            raise ErroProvedor("Tipo de contrato inválido.", codigo="validacao")
        if consulta.jornada not in {"", "full_time", "part_time"}:
            raise ErroProvedor("Jornada inválida.", codigo="validacao")
        if consulta.distancia_km is not None and not 1 <= consulta.distancia_km <= 100:
            raise ErroProvedor("A distância deve ficar entre 1 e 100 km.", codigo="validacao")

    @staticmethod
    def _erro_http(status: int) -> None:
        if status == 400:
            raise ErroProvedor(
                "A Adzuna rejeitou os filtros enviados (HTTP 400).", codigo="validacao"
            )
        if status in {401, 403, 410}:
            raise ErroProvedor(
                "A Adzuna recusou as credenciais configuradas.", codigo="autenticacao"
            )
        if status == 404:
            raise ErroProvedor(
                "O recurso solicitado não foi encontrado na Adzuna.",
                codigo="nao_encontrado",
            )
        if status == 429:
            raise ErroProvedor(
                "O limite temporário da Adzuna foi atingido.",
                codigo="limite",
                transitorio=True,
                limite=True,
            )
        if status >= 500:
            raise ErroProvedor(
                "A Adzuna está temporariamente indisponível.",
                codigo="servidor",
                transitorio=True,
            )
        raise ErroProvedor(f"A Adzuna respondeu com HTTP {status}.", codigo="http")

    @classmethod
    def _converter(cls, item: dict[str, Any]) -> Vaga:
        empresa = cls._display_name(item.get("company"), "Não informada")
        local = cls._display_name(item.get("location"), "Não informada")
        titulo = str(item.get("title") or "Título não informado").strip()
        descricao = str(item.get("description") or "Descrição não informada.").strip()
        texto = normalizar_texto(f"{titulo} {local} {descricao}")
        modalidade = classificar_modalidade(
            titulo, local, descricao, item_fonte=item
        )
        nivel = cls._inferir_nivel(texto)
        categoria = item.get("category")
        if isinstance(categoria, dict):
            categoria = categoria.get("label")
        return Vaga(
            titulo=titulo,
            empresa=empresa,
            localizacao=local,
            descricao=descricao,
            modalidade=modalidade.valor,
            nivel=nivel,
            link=url_http_segura(
                item.get("redirect_url") or item.get("url") or item.get("link")
            ),
            fonte="adzuna",
            identificador_externo=str(item.get("id") or "").strip(),
            data_publicacao=str(item.get("created") or "").strip() or None,
            salario_min=cls._numero_seguro(item.get("salary_min")),
            salario_max=cls._numero_seguro(item.get("salary_max")),
            categoria=str(categoria or "").strip(),
            tipo_contrato=str(item.get("contract_type") or "").strip(),
            jornada=str(item.get("contract_time") or "").strip(),
            modalidade_origem=modalidade.origem,
            modalidade_confianca=modalidade.confianca,
            modalidade_inferida=modalidade.inferida,
        )

    @staticmethod
    def _display_name(value: Any, default: str) -> str:
        if isinstance(value, dict):
            value = value.get("display_name") or value.get("name")
        return str(value or default).strip() or default

    @staticmethod
    def _numero_seguro(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and number >= 0 else None

    @staticmethod
    def _inteiro_seguro(value: Any, default: int) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _inferir_modalidade(texto: str) -> str:
        return classificar_modalidade("", "", texto).valor

    @staticmethod
    def _inferir_nivel(texto: str) -> str:
        for termos, nivel in (
            (("estagio", "internship", "intern"), "estágio"),
            (("junior", " jr "), "júnior"),
            (("pleno", "mid-level"), "pleno"),
            (("senior", "sr ", "especialista", "lead"), "sênior"),
        ):
            if any(termo in f" {texto} " for termo in termos):
                return nivel
        return "não informado"

    @staticmethod
    def _eh_remota(vaga: Vaga) -> bool:
        return modalidade_corresponde(vaga.modalidade, "remoto")
