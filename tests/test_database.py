from __future__ import annotations

import sqlite3

import pytest

from vagasscan.models import Requisito, Vaga
from vagasscan.repositories.vagas import VagaDuplicadaError, VagaRepository


def criar_vaga(**alteracoes: str) -> Vaga:
    dados = {
        "titulo": "Python Júnior",
        "empresa": "Empresa A",
        "localizacao": "Campinas",
        "descricao": "Python e SQL",
        "link": "https://example.com/job/1",
        "fonte": "teste",
        "identificador_externo": "abc-1",
    }
    dados.update(alteracoes)
    return Vaga(**dados)


def test_cadastro_e_consulta(repository: VagaRepository) -> None:
    vaga_id = repository.criar(criar_vaga())
    salva = repository.obter(vaga_id)
    assert salva is not None
    assert salva["titulo"] == "Python Júnior"


@pytest.mark.parametrize(
    ("alteracoes", "regra"),
    [
        ({"link": "https://outro.test/x"}, "fonte e identificador externo"),
        (
            {"identificador_externo": "diferente", "link": "https://example.com/job/1?utm_source=x"},
            "link normalizado",
        ),
        (
            {"identificador_externo": "diferente", "link": "", "titulo": "  PYTHON júnior "},
            "título, empresa e localização",
        ),
    ],
)
def test_deduplicacao_em_ordem(
    repository: VagaRepository, alteracoes: dict[str, str], regra: str
) -> None:
    repository.criar(criar_vaga())
    with pytest.raises(VagaDuplicadaError, match=regra):
        repository.criar(criar_vaga(**alteracoes))


def test_possivel_duplicata_pode_ser_mantida(repository: VagaRepository) -> None:
    repository.criar(criar_vaga())
    segunda = criar_vaga(identificador_externo="novo", link="")
    vaga_id = repository.criar(segunda, aceitar_possivel_duplicata=True)
    assert vaga_id == 2


def test_atualizacao_status_registra_historico(repository: VagaRepository) -> None:
    vaga_id = repository.criar(criar_vaga())
    repository.atualizar_status(vaga_id, "interessante", "Boa aderência")
    assert repository.obter(vaga_id)["status"] == "interessante"  # type: ignore[index]
    historico = repository.historico(vaga_id)
    assert historico[0]["status_anterior"] == "encontrada"
    assert historico[0]["observacao"] == "Boa aderência"


def test_status_invalido_nao_e_aceito(repository: VagaRepository) -> None:
    vaga_id = repository.criar(criar_vaga())
    with pytest.raises(ValueError, match="Status inválido"):
        repository.atualizar_status(vaga_id, "inventado")


def test_vaga_sem_empresa_e_sem_link_recebe_padrao(repository: VagaRepository) -> None:
    vaga_id = repository.criar(
        criar_vaga(empresa="", link="", identificador_externo="sem-link")
    )
    vaga = repository.obter(vaga_id)
    assert vaga is not None
    assert vaga["empresa"] == "Não informada"
    assert vaga["link"] == ""


@pytest.mark.parametrize("campo", ["titulo", "descricao"])
def test_campos_essenciais_vazios_sao_rejeitados(
    repository: VagaRepository, campo: str
) -> None:
    with pytest.raises(ValueError, match="obrigatóri"):
        repository.criar(criar_vaga(**{campo: "  "}))


def test_analise_atomica_reverte_vaga_se_requisitos_falham(
    repository: VagaRepository,
) -> None:
    repetido = Requisito("Python", "linguagens", True)
    with pytest.raises(sqlite3.IntegrityError):
        repository.criar_analisada(criar_vaga(), [repetido, repetido])
    assert repository.listar() == []


def test_conexoes_de_leitura_sao_fechadas_no_windows(
    repository: VagaRepository,
) -> None:
    repository.criar(criar_vaga())
    repository.listar()
    repository.obter(1)
    caminho = repository.database.path
    renomeado = caminho.with_name("renomeado.db")
    caminho.rename(renomeado)
    renomeado.rename(caminho)
