from __future__ import annotations

import argparse
import getpass

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave
from vagasscan.bootstrap import criar_contexto
from vagasscan.cli import CLI
from vagasscan.config import configure_logging, configure_terminal_utf8, load_settings
from vagasscan.database import Database
from vagasscan.models import ConsultaVagas
from vagasscan.providers import ErroProvedor, ProvedorAdzuna, ProvedorDemonstracao
from vagasscan.repositories.vagas import VagaRepository
from vagasscan.security import gerar_hash_senha, gerar_segredo_sessao
from vagasscan.services.vagas import VagaService


def construir_aplicacao() -> tuple[CLI, VagaService, Database]:
    settings = load_settings()
    configure_logging(settings.log_path)
    context = criar_contexto(settings)
    cli = CLI(
        settings,
        context.vaga_service,
        context.vagas,
        context.candidaturas,
        context.relatorios,
    )
    return cli, context.vaga_service, context.database


def _carregar_demo() -> None:
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


def _gerar_hash() -> None:
    senha = getpass.getpass("Senha administrativa (mínimo 12 caracteres): ")
    confirmacao = getpass.getpass("Confirme a senha: ")
    if senha != confirmacao:
        raise SystemExit("As senhas não coincidem.")
    try:
        print(gerar_hash_senha(senha))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _testar_adzuna(termo: str) -> None:
    settings = load_settings()
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        print(
            "A integração com a Adzuna ainda não está configurada. Preencha "
            "ADZUNA_APP_ID e ADZUNA_APP_KEY no arquivo .env."
        )
        return
    provedor = ProvedorAdzuna(settings, tentativas=1)
    try:
        resultado = provedor.consultar(
            ConsultaVagas(
                termo=termo[:100],
                pagina=1,
                resultados_por_pagina=min(5, settings.adzuna_results_per_page),
                pais=settings.adzuna_country,
            )
        )
    except ErroProvedor as exc:
        print(f"A consulta real à Adzuna falhou: {exc}")
        return
    print("Consulta real à Adzuna realizada (sem persistência e sem cache).")
    print(f"Quantidade recebida: {len(resultado.vagas)}")
    for vaga in resultado.vagas:
        print(f"- {vaga.titulo} | {vaga.empresa} | {vaga.localizacao}")


def main() -> None:
    configure_terminal_utf8()
    parser = argparse.ArgumentParser(description="VagaScan - acompanhe vagas de tecnologia")
    parser.add_argument("--carregar-demo", action="store_true")
    parser.add_argument("--somente-inicializar", action="store_true")
    subparsers = parser.add_subparsers(dest="comando")
    subparsers.add_parser("web", help="inicia a interface web")
    testar = subparsers.add_parser("testar-adzuna", help="faz uma consulta real opcional")
    testar.add_argument("--termo", default="python")
    subparsers.add_parser("gerar-hash-senha", help="gera um hash administrativo scrypt")
    subparsers.add_parser("gerar-segredo-sessao", help="gera um segredo aleatório")
    args = parser.parse_args()

    if args.comando == "gerar-hash-senha":
        _gerar_hash()
        return
    if args.comando == "gerar-segredo-sessao":
        print(gerar_segredo_sessao())
        return
    if args.comando == "testar-adzuna":
        _testar_adzuna(args.termo)
        return
    if args.comando == "web":
        import uvicorn

        settings = load_settings()
        uvicorn.run(
            "vagasscan.web.app:app",
            host=settings.host,
            port=settings.port,
            reload=settings.environment == "development",
            access_log=False,
        )
        return

    cli, _, database = construir_aplicacao()
    if args.carregar_demo:
        _carregar_demo()
        return
    if args.somente_inicializar:
        print(f"Banco inicializado em {database.path}")
        return
    cli.executar()


if __name__ == "__main__":
    main()
