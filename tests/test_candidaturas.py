from __future__ import annotations

import pytest

from vagasscan.database import Database
from vagasscan.models import Candidatura, Vaga
from vagasscan.repositories.candidaturas import CandidaturaRepository
from vagasscan.repositories.vagas import VagaRepository


def criar_vaga(repository: VagaRepository) -> int:
    return repository.criar(Vaga("Python Júnior", "Empresa", "Campinas", "Python"))


@pytest.mark.parametrize("data", ["31/12/2026", "2026-02-30", "texto", ""])
def test_data_de_candidatura_invalida_e_rejeitada(database: Database, data: str) -> None:
    vaga_id = criar_vaga(VagaRepository(database))
    repository = CandidaturaRepository(database)
    with pytest.raises(ValueError, match="Data da candidatura"):
        repository.registrar(Candidatura(vaga_id=vaga_id, data_candidatura=data))
    assert repository.listar() == []


def test_data_de_proxima_acao_invalida_e_rejeitada(database: Database) -> None:
    vaga_id = criar_vaga(VagaRepository(database))
    with pytest.raises(ValueError, match="Data da próxima ação"):
        CandidaturaRepository(database).registrar(
            Candidatura(vaga_id=vaga_id, data_proxima_acao="amanhã")
        )


def test_etapa_invalida_e_rejeitada(database: Database) -> None:
    vaga_id = criar_vaga(VagaRepository(database))
    with pytest.raises(ValueError, match="Etapa"):
        CandidaturaRepository(database).registrar(
            Candidatura(vaga_id=vaga_id, etapa="conversa informal")
        )


def test_registro_e_atualizacao_sincronizam_status_atomicamente(database: Database) -> None:
    vagas = VagaRepository(database)
    vaga_id = criar_vaga(vagas)
    candidaturas = CandidaturaRepository(database)
    candidatura_id = candidaturas.registrar(
        Candidatura(vaga_id=vaga_id, data_proxima_acao="2026-08-10")
    )
    assert vagas.obter(vaga_id)["status"] == "candidatura_enviada"  # type: ignore[index]
    candidaturas.atualizar_etapa(
        candidatura_id, "entrevista_rh", "Preparar respostas", "2026-08-12"
    )
    assert vagas.obter(vaga_id)["status"] == "entrevista_rh"  # type: ignore[index]
    assert [item["status_novo"] for item in vagas.historico(vaga_id)] == [
        "entrevista_rh",
        "candidatura_enviada",
    ]


def test_segunda_candidatura_para_mesma_vaga_tem_erro_claro(database: Database) -> None:
    vaga_id = criar_vaga(VagaRepository(database))
    candidaturas = CandidaturaRepository(database)
    candidaturas.registrar(Candidatura(vaga_id=vaga_id))
    with pytest.raises(ValueError, match="já possui"):
        candidaturas.registrar(Candidatura(vaga_id=vaga_id))
