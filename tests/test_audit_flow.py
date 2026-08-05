from __future__ import annotations

from pathlib import Path

import pytest

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave
from vagasscan.config import PROJECT_ROOT, Settings
from vagasscan.database import Database
from vagasscan.file_organizer import OrganizadorArquivos
from vagasscan.models import Candidatura, Vaga
from vagasscan.providers import (
    ProvedorDemonstracao,
    ProvedorHttpConfiguravel,
    ProvedorNaoConfigurado,
)
from vagasscan.reports import GeradorRelatorios
from vagasscan.repositories.candidaturas import CandidaturaRepository
from vagasscan.repositories.vagas import VagaDuplicadaError, VagaRepository
from vagasscan.services.vagas import VagaService


def criar_servico(database: Database, profile_path: Path) -> VagaService:
    return VagaService(
        VagaRepository(database),
        AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json"),
        CalculadoraCompatibilidade(),
        profile_path,
    )


def test_fluxo_de_auditoria_completo_em_ambiente_temporario(
    tmp_path: Path, profile_path: Path
) -> None:
    banco_principal = Database(tmp_path / "principal.db")
    banco_demo = Database(tmp_path / "demonstracao.db")
    banco_principal.initialize()
    banco_demo.initialize()

    demo = criar_servico(banco_demo, profile_path).buscar_e_salvar(ProvedorDemonstracao(), "")
    assert len(demo["cadastradas"]) == 3
    assert VagaRepository(banco_principal).listar() == []

    service = criar_servico(banco_principal, profile_path)
    manual_id, manual = service.cadastrar_e_analisar(
        Vaga(
            "Desenvolvedor Python Júnior",
            "Empresa Auditada",
            "Campinas",
            "Python e SQL obrigatórios. Docker desejável.",
            "híbrido",
            "júnior",
        )
    )
    importada_id, importada = service.cadastrar_e_analisar(
        Vaga(
            "Suporte Técnico Júnior",
            "Não informada",
            "Piracicaba",
            "Atendimento, Windows e suporte ao usuário.",
            "presencial",
            "júnior",
        )
    )
    assert manual_id != importada_id
    assert 0 <= manual.pontuacao <= 100
    assert 0 <= importada.pontuacao <= 100
    assert VagaRepository(banco_principal).listar_requisitos(manual_id)

    with pytest.raises(VagaDuplicadaError):
        service.cadastrar_e_analisar(
            Vaga(
                "DESENVOLVEDOR PYTHON JÚNIOR",
                "empresa auditada",
                "campinas",
                "Outra descrição",
            )
        )

    vagas = VagaRepository(banco_principal)
    vagas.atualizar_status(manual_id, "interessante", "Fluxo auditado")
    candidaturas = CandidaturaRepository(banco_principal)
    candidatura_id = candidaturas.registrar(
        Candidatura(manual_id, "2026-08-05", proxima_acao="Preparar entrevista")
    )
    candidaturas.atualizar_etapa(
        candidatura_id, "entrevista_rh", "Revisar empresa", "2026-08-10"
    )
    assert vagas.obter(manual_id)["status"] == "entrevista_rh"  # type: ignore[index]

    relatorios = GeradorRelatorios(banco_principal)
    resumo = relatorios.resumo()
    assert sum(item["quantidade"] for item in resumo["vagas_por_status"]) == 2
    assert relatorios.exportar_markdown(tmp_path / "relatorio.md").exists()
    assert relatorios.exportar_csv(tmp_path / "relatorio.csv").exists()

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    documento = entrada / "currículo_python.pdf"
    documento.write_text("teste", encoding="utf-8")
    organizador = OrganizadorArquivos(tmp_path / "historico.json")
    movimentos = organizador.planejar(entrada, tmp_path / "Carreira")
    assert organizador.executar(movimentos, simular=True) == 1
    assert documento.exists()
    assert not (tmp_path / "Carreira").exists()

    with pytest.raises(ProvedorNaoConfigurado):
        ProvedorHttpConfiguravel(
            Settings(
                database_path=tmp_path / "api.db",
                demo_database_path=tmp_path / "api-demo.db",
                profile_path=profile_path,
                keywords_path=PROJECT_ROOT / "data" / "keywords.json",
                log_path=tmp_path / "api.log",
            )
        ).buscar("python")
