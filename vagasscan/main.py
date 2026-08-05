from __future__ import annotations

import argparse

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave
from vagasscan.cli import CLI
from vagasscan.config import configure_logging, configure_terminal_utf8, load_settings
from vagasscan.database import Database
from vagasscan.providers import ProvedorDemonstracao
from vagasscan.reports import GeradorRelatorios
from vagasscan.repositories.candidaturas import CandidaturaRepository
from vagasscan.repositories.vagas import VagaRepository
from vagasscan.services.vagas import VagaService


def construir_aplicacao() -> tuple[CLI, VagaService, Database]:
    settings = load_settings()
    configure_logging(settings.log_path)
    database = Database(settings.database_path)
    database.initialize()
    vagas = VagaRepository(database)
    service = VagaService(
        vagas,
        AnalisadorPalavrasChave(settings.keywords_path),
        CalculadoraCompatibilidade(),
        settings.profile_path,
    )
    cli = CLI(
        settings,
        service,
        vagas,
        CandidaturaRepository(database),
        GeradorRelatorios(database),
    )
    return cli, service, database


def main() -> None:
    configure_terminal_utf8()
    parser = argparse.ArgumentParser(description="VagasScan - acompanhe vagas de tecnologia")
    parser.add_argument(
        "--carregar-demo",
        action="store_true",
        help="insere e analisa vagas fictícias, sem misturá-las com fontes reais",
    )
    parser.add_argument(
        "--somente-inicializar", action="store_true", help="cria o banco e encerra"
    )
    args = parser.parse_args()
    cli, service, database = construir_aplicacao()
    if args.carregar_demo:
        settings = load_settings()
        demo_database = Database(settings.demo_database_path)
        demo_database.initialize()
        demo_service = VagaService(
            VagaRepository(demo_database),
            AnalisadorPalavrasChave(settings.keywords_path),
            CalculadoraCompatibilidade(),
            settings.profile_path,
        )
        resultado = demo_service.buscar_e_salvar(ProvedorDemonstracao(), "")
        print(
            f"Demonstração: {len(resultado['cadastradas'])} cadastrada(s), "
            f"{len(resultado['duplicadas'])} duplicada(s), {len(resultado['erros'])} erro(s)."
        )
        print(f"Banco de demonstração: {demo_database.path}")
        return
    if args.somente_inicializar:
        print(f"Banco inicializado em {database.path}")
        return
    cli.executar()


if __name__ == "__main__":
    main()
