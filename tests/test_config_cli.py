from __future__ import annotations

from pathlib import Path

import pytest

from vagasscan.cli import CLI, perguntar_data, perguntar_texto_longo
from vagasscan.config import Settings, configure_terminal_utf8, load_settings
from vagasscan.providers import ProvedorVagas


def test_configuracao_funciona_sem_arquivo_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for nome in (
        "VAGASSCAN_DATABASE",
        "VAGASSCAN_PROFILE",
        "VAGASSCAN_KEYWORDS",
        "VAGASSCAN_LOG",
        "JOB_API_URL",
        "JOB_API_TOKEN",
        "JOB_API_TIMEOUT",
    ):
        monkeypatch.delenv(nome, raising=False)
    configuracao = load_settings(tmp_path / "nao-existe.env")
    assert configuracao.api_url == ""
    assert configuracao.api_token == ""
    assert configuracao.database_path.name == "vagasscan.db"


@pytest.mark.parametrize("valor", ["nan", "inf", "0", "-5", "texto"])
def test_timeout_invalido_volta_ao_padrao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv("JOB_API_TIMEOUT", valor)
    assert load_settings(tmp_path / "nao-existe.env").api_timeout == 10


def test_limites_de_busca_tem_defaults_e_faixas_seguras(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nomes = (
        "VAGASSCAN_PUBLIC_SEARCH_COOLDOWN_SECONDS",
        "VAGASSCAN_PUBLIC_SEARCH_LIMIT_PER_HOUR",
        "VAGASSCAN_ADMIN_SEARCH_LIMIT_PER_HOUR",
    )
    for nome in nomes:
        monkeypatch.delenv(nome, raising=False)
    configuracao = load_settings(tmp_path / "nao-existe.env")
    assert configuracao.public_search_cooldown_seconds == 15
    assert configuracao.public_search_limit_per_hour == 30
    assert configuracao.admin_search_limit_per_hour == 100

    monkeypatch.setenv(nomes[0], "999")
    monkeypatch.setenv(nomes[1], "0")
    monkeypatch.setenv(nomes[2], "9000")
    limitada = load_settings(tmp_path / "nao-existe.env")
    assert limitada.public_search_cooldown_seconds == 300
    assert limitada.public_search_limit_per_hour == 1
    assert limitada.admin_search_limit_per_hour == 5000


def test_pergunta_data_repete_ate_receber_data_valida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respostas = iter(["31/12/2026", "2026-02-30", "2026-12-31"])
    monkeypatch.setattr("builtins.input", lambda _: next(respostas))
    assert perguntar_data("Data") == "2026-12-31"


def test_texto_longo_aceita_varias_linhas(monkeypatch: pytest.MonkeyPatch) -> None:
    respostas = iter(["Primeira linha", "Python e SQL", "FIM"])
    monkeypatch.setattr("builtins.input", lambda _: next(respostas))
    assert perguntar_texto_longo("Descrição") == "Primeira linha\nPython e SQL"


def test_texto_longo_pode_ser_cancelado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "0")
    assert perguntar_texto_longo("Descrição") is None


def test_configuracao_utf8_tolera_streams_de_teste() -> None:
    configure_terminal_utf8()


def test_cli_encerra_com_ctrl_c(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = object.__new__(CLI)
    cli.acoes = {}

    def interromper(_: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interromper)
    cli.executar()
    assert "Operação cancelada. Até logo!" in capsys.readouterr().out


def test_cli_explica_indisponibilidade_sem_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configuracao = Settings(
        database_path=tmp_path / "db.sqlite",
        demo_database_path=tmp_path / "demo.sqlite",
        profile_path=tmp_path / "perfil.json",
        keywords_path=tmp_path / "keywords.json",
        log_path=tmp_path / "log.txt",
    )

    class ServicoMinimo:
        def buscar_e_salvar(
            self, provedor: ProvedorVagas, termo: str, localizacao: str = ""
        ) -> dict[str, object]:
            provedor.buscar(termo, localizacao)
            return {}

    cli = object.__new__(CLI)
    cli.settings = configuracao
    cli.vaga_service = ServicoMinimo()
    respostas = iter(["2", "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(respostas))
    cli.buscar_vagas()
    saida = capsys.readouterr().out
    assert "A fonte não pôde ser consultada" in saida
    assert "cadastro manual" in saida


def test_cli_adzuna_sem_credenciais_volta_ao_menu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = object.__new__(CLI)
    cli.settings = Settings(
        database_path=tmp_path / "db.sqlite",
        demo_database_path=tmp_path / "demo.sqlite",
        profile_path=tmp_path / "perfil.json",
        keywords_path=tmp_path / "keywords.json",
        log_path=tmp_path / "log.txt",
    )
    monkeypatch.setattr("builtins.input", lambda _: "1")
    cli.buscar_vagas()
    saida = capsys.readouterr().out
    assert "Adzuna ainda não está configurada" in saida
    assert "demonstração continuam disponíveis" in saida


def test_cli_com_banco_vazio_exibe_mensagem(capsys: pytest.CaptureFixture[str]) -> None:
    CLI._mostrar_lista([])
    assert "Nenhuma vaga encontrada" in capsys.readouterr().out


def test_cli_rejeita_indice_de_status_negativo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class VagasFalsas:
        atualizado = False

        def atualizar_status(self, *args: object, **kwargs: object) -> None:
            self.atualizado = True

    cli = object.__new__(CLI)
    cli.vagas = VagasFalsas()
    respostas = iter(["1", "-1"])
    monkeypatch.setattr("builtins.input", lambda _: next(respostas))
    cli.atualizar_status()
    assert "Status inválido" in capsys.readouterr().out
    assert cli.vagas.atualizado is False
