from __future__ import annotations

import pytest

from vagasscan.analyzers.modality import classificar_modalidade


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Vaga remota para todo o Brasil", "remoto"),
        ("Modelo híbrido, três dias no escritório", "híbrido"),
        ("Trabalho presencial em Campinas", "presencial"),
        ("A vaga não é remota", "presencial"),
        ("Possibilidade de trabalho remoto", "possivelmente remoto"),
    ],
)
def test_modalidade_inferida_com_contexto(texto: str, esperado: str) -> None:
    modalidade = classificar_modalidade("", "", texto)
    assert modalidade.valor == esperado
    assert modalidade.origem == "VagaScan"
    assert modalidade.inferida is True


def test_modalidade_estruturada_da_fonte_tem_prioridade() -> None:
    modalidade = classificar_modalidade(
        "Vaga presencial",
        "São Paulo",
        "Escritório local",
        item_fonte={"workplace_type": "remote"},
    )
    assert modalidade.valor == "remoto"
    assert modalidade.origem == "fonte"
    assert modalidade.confianca == "alta"
    assert modalidade.inferida is False


def test_contexto_tecnico_remoto_nao_define_modalidade() -> None:
    modalidade = classificar_modalidade(
        "Analista de infraestrutura",
        "Brasil",
        "Acesso remoto a servidores e suporte remoto ao usuário.",
    )
    assert modalidade.valor == "não informada"
    assert modalidade.inferida is False
