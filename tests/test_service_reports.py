from __future__ import annotations

from pathlib import Path

import pytest

from vagasscan.database import Database
from vagasscan.models import Candidatura, ConsultaVagas, ResultadoBusca, Vaga
from vagasscan.providers.base import ProvedorVagas
from vagasscan.reports import GeradorRelatorios
from vagasscan.repositories.candidaturas import CandidaturaRepository
from vagasscan.services.vagas import VagaService


def test_fluxo_cadastro_analise_candidatura_relatorio(
    service: VagaService, database: object, tmp_path: Path
) -> None:
    vaga_id, resultado = service.cadastrar_e_analisar(
        Vaga(
            titulo="Backend Python Júnior",
            empresa="Teste",
            localizacao="Remoto no Brasil",
            modalidade="remoto",
            nivel="júnior",
            descricao="Python, SQL e FastAPI. Docker desejável.",
        )
    )
    assert vaga_id == 1
    assert resultado.pontuacao > 0
    candidaturas = CandidaturaRepository(database)  # type: ignore[arg-type]
    candidaturas.registrar(
        Candidatura(vaga_id=vaga_id, proxima_acao="Enviar mensagem", data_proxima_acao="2026-08-10")
    )
    gerador = GeradorRelatorios(database)  # type: ignore[arg-type]
    resumo = gerador.resumo()
    assert resumo["vagas_por_fonte"] == [{"nome": "manual", "quantidade": 1}]
    assert any(item["nome"] == "Python" for item in resumo["tecnologias_mais_pedidas"])
    assert resumo["proximas_acoes"][0]["proxima_acao"] == "Enviar mensagem"
    markdown = gerador.exportar_markdown(tmp_path / "relatorio.md")
    csv = gerador.exportar_csv(tmp_path / "relatorio.csv")
    assert "# Relatório VagasScan" in markdown.read_text(encoding="utf-8")
    assert "Backend Python Júnior" in csv.read_text(encoding="utf-8-sig")


def test_banco_vazio_e_exportacao_sem_resultados(database: Database, tmp_path: Path) -> None:
    gerador = GeradorRelatorios(database)
    resumo = gerador.resumo()
    assert resumo["vagas_por_status"] == []
    assert resumo["media_compatibilidade"] == 0
    assert "nenhum registro" in gerador.formatar_terminal()
    markdown = gerador.exportar_markdown(tmp_path / "vazio.md")
    csv = gerador.exportar_csv(tmp_path / "vazio.csv")
    assert "Média de compatibilidade" in markdown.read_text(encoding="utf-8")
    assert csv.read_text(encoding="utf-8-sig").splitlines()[0].startswith("id;titulo")


def test_exportacao_nao_sobrescreve_sem_autorizacao(
    database: Database, tmp_path: Path
) -> None:
    gerador = GeradorRelatorios(database)
    destino = tmp_path / "existente.md"
    destino.write_text("conteúdo do usuário", encoding="utf-8")
    with pytest.raises(FileExistsError, match="já existe"):
        gerador.exportar_markdown(destino)
    assert destino.read_text(encoding="utf-8") == "conteúdo do usuário"
    gerador.exportar_markdown(destino, sobrescrever=True)
    assert destino.read_text(encoding="utf-8").startswith("# Relatório VagasScan")


def test_csv_neutraliza_formula_vinda_de_texto_externo(
    service: VagaService, database: Database, tmp_path: Path
) -> None:
    service.cadastrar_e_analisar(Vaga("=2+2", "@empresa", "Campinas", "Python"))
    destino = GeradorRelatorios(database).exportar_csv(tmp_path / "seguro.csv")
    conteudo = destino.read_text(encoding="utf-8-sig")
    assert "'=2+2" in conteudo
    assert "'@empresa" in conteudo


def test_filtro_modalidade_consulta_no_maximo_paginas_extras_controladas(
    service: VagaService,
) -> None:
    class ProvedorPaginado(ProvedorVagas):
        nome = "adzuna"

        def buscar(self, termo: str, localizacao: str = "") -> list[Vaga]:
            return []

        def consultar(self, consulta: ConsultaVagas) -> ResultadoBusca:
            if consulta.pagina == 1:
                vagas = [
                    Vaga(
                        f"Presencial {indice}",
                        "Empresa",
                        "Campinas",
                        "Python e SQL",
                        modalidade="presencial",
                        identificador_externo=f"p-{indice}",
                        fonte="adzuna",
                    )
                    for indice in range(20)
                ]
            else:
                vagas = [
                    Vaga(
                        f"Remota {indice}",
                        "Empresa",
                        "Brasil",
                        "Python e SQL",
                        modalidade="remoto",
                        identificador_externo=f"r-{indice}",
                        fonte="adzuna",
                    )
                    for indice in range(2)
                ]
            return ResultadoBusca(
                vagas=vagas,
                pagina=consulta.pagina,
                resultados_por_pagina=20,
                total_aproximado=40,
            )

    autorizacoes: list[bool] = []
    resultado = service.buscar_e_salvar(
        ProvedorPaginado(),
        ConsultaVagas(termo="python", modalidade="remoto"),
        autorizar_consulta_externa=lambda: autorizacoes.append(True),
    )
    assert resultado["recebidas"] == 22
    assert resultado["quantidade_analisada"] == 22
    assert resultado["paginas_analisadas"] == 2
    assert resultado["recebidas"] > len(resultado["itens"]) == 2
    assert len(autorizacoes) == 2
