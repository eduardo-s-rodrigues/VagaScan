from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave, carregar_perfil
from vagasscan.models import ConsultaVagas, Requisito, ResultadoCompatibilidade, Vaga
from vagasscan.providers.base import ErroProvedor, ProvedorVagas
from vagasscan.repositories.cache import CacheBuscaRepository
from vagasscan.repositories.vagas import VagaDuplicadaError, VagaRepository

LOGGER = logging.getLogger(__name__)


class VagaService:
    def __init__(
        self,
        repository: VagaRepository,
        analisador: AnalisadorPalavrasChave,
        calculadora: CalculadoraCompatibilidade,
        profile_path: Path,
        cache: CacheBuscaRepository | None = None,
        cache_minutes: int = 30,
    ) -> None:
        self.repository = repository
        self.analisador = analisador
        self.calculadora = calculadora
        self.profile_path = profile_path
        self.cache = cache
        self.cache_minutes = cache_minutes

    def analisar_temporaria(
        self, vaga: Vaga
    ) -> tuple[ResultadoCompatibilidade, list[Requisito]]:
        perfil = carregar_perfil(self.profile_path)
        requisitos = self.analisador.extrair(vaga.descricao, perfil["conhecimentos"])
        resultado = self.calculadora.calcular(vaga, requisitos, perfil)
        vaga.compatibilidade = resultado.pontuacao
        return resultado, requisitos

    def cadastrar_e_analisar(
        self, vaga: Vaga, *, aceitar_possivel_duplicata: bool = False
    ) -> tuple[int, ResultadoCompatibilidade]:
        vaga_id, resultado, _ = self._cadastrar_com_requisitos(
            vaga, aceitar_possivel_duplicata=aceitar_possivel_duplicata
        )
        return vaga_id, resultado

    def _cadastrar_com_requisitos(
        self, vaga: Vaga, *, aceitar_possivel_duplicata: bool = False
    ) -> tuple[int, ResultadoCompatibilidade, list[Requisito]]:
        resultado, requisitos = self.analisar_temporaria(vaga)
        vaga_id = self.repository.criar_analisada(
            vaga,
            requisitos,
            aceitar_possivel_duplicata=aceitar_possivel_duplicata,
        )
        LOGGER.info("Vaga cadastrada e analisada: id=%s fonte=%s", vaga_id, vaga.fonte)
        return vaga_id, resultado, requisitos

    def buscar_e_salvar(
        self,
        provedor: ProvedorVagas,
        termo: str | ConsultaVagas,
        localizacao: str = "",
        autorizar_consulta_externa: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        consulta = (
            termo
            if isinstance(termo, ConsultaVagas)
            else ConsultaVagas(termo=termo, localizacao=localizacao)
        )
        resultado_busca = None
        if self.cache and provedor.nome == "adzuna":
            resultado_busca = self.cache.obter(provedor.nome, consulta)
        if resultado_busca is None:
            try:
                if autorizar_consulta_externa:
                    autorizar_consulta_externa()
                resultado_busca = provedor.consultar(consulta)
            except ErroProvedor as exc:
                if self.cache and provedor.nome == "adzuna" and exc.transitorio:
                    resultado_busca = self.cache.obter(
                        provedor.nome, consulta, permitir_expirado=True
                    )
                    if resultado_busca is not None:
                        resultado_busca.erros.append(
                            "A fonte está indisponível; foi usado um cache anterior."
                        )
                if resultado_busca is None:
                    raise
            else:
                if self.cache and provedor.nome == "adzuna":
                    self.cache.salvar(
                        provedor.nome, consulta, resultado_busca, self.cache_minutes
                    )
        vagas = resultado_busca.vagas
        cadastradas: list[int] = []
        duplicadas: list[str] = []
        erros: list[str] = list(resultado_busca.erros)
        itens: list[dict[str, Any]] = []
        for vaga in vagas:
            try:
                vaga_id, analise, requisitos = self._cadastrar_com_requisitos(vaga)
                cadastradas.append(vaga_id)
                itens.append(
                    {
                        "vaga": vaga,
                        "vaga_id": vaga_id,
                        "salva_nova": True,
                        "analise": analise,
                        "requisitos": requisitos,
                    }
                )
            except VagaDuplicadaError as exc:
                duplicadas.append(str(exc))
                analise, requisitos = self.analisar_temporaria(vaga)
                itens.append(
                    {
                        "vaga": vaga,
                        "vaga_id": exc.vaga_id,
                        "salva_nova": False,
                        "analise": analise,
                        "requisitos": requisitos,
                    }
                )
            except (ValueError, TypeError) as exc:
                LOGGER.exception("Falha ao processar vaga do provedor")
                erros.append(f"{vaga.titulo}: {exc}")
        return {
            "recebidas": len(vagas),
            "cadastradas": cadastradas,
            "duplicadas": duplicadas,
            "erros": erros,
            "itens": itens,
            "pagina": resultado_busca.pagina,
            "resultados_por_pagina": resultado_busca.resultados_por_pagina,
            "total_aproximado": resultado_busca.total_aproximado,
            "veio_cache": resultado_busca.veio_cache,
            "cache_desatualizado": resultado_busca.cache_desatualizado,
            "cache_expira_em": resultado_busca.cache_expira_em,
        }

    def analisar_existente(self, vaga_id: int) -> ResultadoCompatibilidade:
        dados = self.repository.obter(vaga_id)
        if not dados:
            raise ValueError(f"Vaga #{vaga_id} não encontrada.")
        perfil = carregar_perfil(self.profile_path)
        requisitos = self.analisador.extrair(dados["descricao"], perfil["conhecimentos"])
        resultado = self.calculadora.calcular(dados, requisitos, perfil)
        self.repository.salvar_analise(vaga_id, resultado.pontuacao, requisitos)
        return resultado

    @staticmethod
    def resultado_como_dict(resultado: ResultadoCompatibilidade) -> dict[str, Any]:
        return asdict(resultado)
