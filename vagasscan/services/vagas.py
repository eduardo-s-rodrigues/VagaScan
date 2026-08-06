from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave, carregar_perfil
from vagasscan.analyzers.modality import modalidade_corresponde
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
        max_extra_pages_for_filter: int = 2,
    ) -> None:
        self.repository = repository
        self.analisador = analisador
        self.calculadora = calculadora
        self.profile_path = profile_path
        self.cache = cache
        self.cache_minutes = cache_minutes
        self.max_extra_pages_for_filter = max(0, min(max_extra_pages_for_filter, 2))

    def analisar_temporaria(
        self, vaga: Vaga
    ) -> tuple[ResultadoCompatibilidade, list[Requisito]]:
        perfil = carregar_perfil(self.profile_path)
        requisitos = self.analisador.extrair(vaga.descricao, perfil["conhecimentos"])
        resultado = self.calculadora.calcular(vaga, requisitos, perfil)
        vaga.compatibilidade = resultado.pontuacao
        vaga.confianca_analise = resultado.confianca
        vaga.requisitos_identificados = resultado.requisitos_identificados
        return resultado, requisitos

    def _consultar_uma_pagina(
        self,
        provedor: ProvedorVagas,
        consulta: ConsultaVagas,
        autorizar_consulta_externa: Callable[[], None] | None,
    ):
        resultado = None
        if self.cache and provedor.nome == "adzuna":
            resultado = self.cache.obter(provedor.nome, consulta)
        if resultado is not None:
            return resultado
        try:
            if autorizar_consulta_externa:
                autorizar_consulta_externa()
            resultado = provedor.consultar(consulta)
        except ErroProvedor as exc:
            if self.cache and provedor.nome == "adzuna" and exc.transitorio:
                resultado = self.cache.obter(
                    provedor.nome, consulta, permitir_expirado=True
                )
                if resultado is not None:
                    resultado.erros.append(
                        "A fonte está indisponível; foi usado um cache anterior."
                    )
            if resultado is None:
                raise
        else:
            if self.cache and provedor.nome == "adzuna":
                self.cache.salvar(provedor.nome, consulta, resultado, self.cache_minutes)
        return resultado

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
        resultado_busca = self._consultar_uma_pagina(
            provedor, consulta, autorizar_consulta_externa
        )
        resultados_busca = [resultado_busca]
        vagas_analisadas = list(resultado_busca.vagas)
        filtro_modalidade = consulta.modalidade or ("remoto" if consulta.remoto else "")
        vagas_filtradas = [
            vaga
            for vaga in vagas_analisadas
            if modalidade_corresponde(vaga.modalidade, filtro_modalidade)
        ]
        erros_busca_adicional: list[str] = []
        if filtro_modalidade and provedor.nome == "adzuna":
            for deslocamento in range(1, self.max_extra_pages_for_filter + 1):
                if len(vagas_filtradas) >= consulta.resultados_por_pagina:
                    break
                anterior = resultados_busca[-1]
                if not anterior.vagas or len(anterior.vagas) < consulta.resultados_por_pagina:
                    break
                proxima = replace(consulta, pagina=consulta.pagina + deslocamento)
                try:
                    pagina_extra = self._consultar_uma_pagina(
                        provedor, proxima, autorizar_consulta_externa
                    )
                except (ErroProvedor, RuntimeError):
                    erros_busca_adicional.append(
                        "Páginas adicionais não puderam ser consultadas; "
                        "os resultados disponíveis foram mantidos."
                    )
                    break
                resultados_busca.append(pagina_extra)
                vagas_analisadas.extend(pagina_extra.vagas)
                vagas_filtradas.extend(
                    vaga
                    for vaga in pagina_extra.vagas
                    if modalidade_corresponde(vaga.modalidade, filtro_modalidade)
                )
        vagas = vagas_filtradas if filtro_modalidade else vagas_analisadas
        vagas = vagas[: consulta.resultados_por_pagina]
        cadastradas: list[int] = []
        duplicadas: list[str] = []
        erros: list[str] = [
            erro for pagina_resultado in resultados_busca for erro in pagina_resultado.erros
        ]
        erros.extend(erros_busca_adicional)
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
            "recebidas": len(vagas_analisadas),
            "cadastradas": cadastradas,
            "duplicadas": duplicadas,
            "erros": erros,
            "itens": itens,
            "pagina": resultado_busca.pagina,
            "resultados_por_pagina": resultado_busca.resultados_por_pagina,
            "total_aproximado": resultado_busca.total_aproximado,
            "veio_cache": all(item.veio_cache for item in resultados_busca),
            "usou_cache": any(item.veio_cache for item in resultados_busca),
            "usou_api": any(not item.veio_cache for item in resultados_busca),
            "cache_desatualizado": any(
                item.cache_desatualizado for item in resultados_busca
            ),
            "cache_expira_em": resultado_busca.cache_expira_em,
            "cache_criado_em": resultado_busca.cache_criado_em,
            "paginas_analisadas": len(resultados_busca),
            "quantidade_analisada": len(vagas_analisadas),
        }

    def analisar_existente(self, vaga_id: int) -> ResultadoCompatibilidade:
        dados = self.repository.obter(vaga_id)
        if not dados:
            raise ValueError(f"Vaga #{vaga_id} não encontrada.")
        perfil = carregar_perfil(self.profile_path)
        requisitos = self.analisador.extrair(dados["descricao"], perfil["conhecimentos"])
        resultado = self.calculadora.calcular(dados, requisitos, perfil)
        self.repository.salvar_analise(
            vaga_id,
            resultado.pontuacao,
            requisitos,
            confianca=resultado.confianca,
            requisitos_identificados=resultado.requisitos_identificados,
        )
        return resultado

    @staticmethod
    def resultado_como_dict(resultado: ResultadoCompatibilidade) -> dict[str, Any]:
        return asdict(resultado)
