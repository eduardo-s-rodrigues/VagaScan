from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave, carregar_perfil
from vagasscan.models import ResultadoCompatibilidade, Vaga
from vagasscan.providers.base import ProvedorVagas
from vagasscan.repositories.vagas import VagaDuplicadaError, VagaRepository

LOGGER = logging.getLogger(__name__)


class VagaService:
    def __init__(
        self,
        repository: VagaRepository,
        analisador: AnalisadorPalavrasChave,
        calculadora: CalculadoraCompatibilidade,
        profile_path: Path,
    ) -> None:
        self.repository = repository
        self.analisador = analisador
        self.calculadora = calculadora
        self.profile_path = profile_path

    def cadastrar_e_analisar(
        self, vaga: Vaga, *, aceitar_possivel_duplicata: bool = False
    ) -> tuple[int, ResultadoCompatibilidade]:
        perfil = carregar_perfil(self.profile_path)
        requisitos = self.analisador.extrair(vaga.descricao, perfil["conhecimentos"])
        resultado = self.calculadora.calcular(vaga, requisitos, perfil)
        vaga.compatibilidade = resultado.pontuacao
        vaga_id = self.repository.criar_analisada(
            vaga,
            requisitos,
            aceitar_possivel_duplicata=aceitar_possivel_duplicata,
        )
        LOGGER.info("Vaga cadastrada e analisada: id=%s fonte=%s", vaga_id, vaga.fonte)
        return vaga_id, resultado

    def buscar_e_salvar(
        self, provedor: ProvedorVagas, termo: str, localizacao: str = ""
    ) -> dict[str, Any]:
        vagas = provedor.buscar(termo, localizacao)
        cadastradas: list[int] = []
        duplicadas: list[str] = []
        erros: list[str] = []
        for vaga in vagas:
            try:
                vaga_id, _ = self.cadastrar_e_analisar(vaga)
                cadastradas.append(vaga_id)
            except VagaDuplicadaError as exc:
                duplicadas.append(str(exc))
            except (ValueError, TypeError) as exc:
                LOGGER.exception("Falha ao processar vaga do provedor")
                erros.append(f"{vaga.titulo}: {exc}")
        return {
            "recebidas": len(vagas),
            "cadastradas": cadastradas,
            "duplicadas": duplicadas,
            "erros": erros,
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
