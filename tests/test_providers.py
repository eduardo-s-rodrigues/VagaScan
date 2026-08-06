from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from vagasscan.config import Settings
from vagasscan.providers import (
    ErroProvedor,
    ProvedorDemonstracao,
    ProvedorHttpConfiguravel,
    ProvedorNaoConfigurado,
)


def settings(tmp_path: Path, **changes: Any) -> Settings:
    data: dict[str, Any] = {
        "database_path": tmp_path / "db.sqlite",
        "demo_database_path": tmp_path / "demo.sqlite",
        "profile_path": tmp_path / "profile.json",
        "keywords_path": tmp_path / "keywords.json",
        "log_path": tmp_path / "log.txt",
    }
    data.update(changes)
    return Settings(**data)


class RespostaInvalida:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        raise requests.exceptions.JSONDecodeError("inválido", "<html>", 0)


class SessaoFalsa:
    def __init__(self, resposta: Any) -> None:
        self.resposta = resposta

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self.resposta


class SessaoTimeout:
    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise requests.Timeout("token-secreto-nao-deve-aparecer")


class SessaoSequencial:
    def __init__(self, respostas: list[Any]) -> None:
        self.respostas = iter(respostas)
        self.calls = 0

    def get(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        return next(self.respostas)


class RespostaHttpErro:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        raise requests.HTTPError(f"HTTP {self.status_code}")


class RespostaJson:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return [{"title": "Estágio Python", "description": "Python", "id": "1"}]


def test_resposta_invalida_do_provedor(tmp_path: Path) -> None:
    provedor = ProvedorHttpConfiguravel(
        settings(tmp_path, api_url="https://api.example.test/jobs"),
        session=SessaoFalsa(RespostaInvalida()),  # type: ignore[arg-type]
    )
    with pytest.raises(ErroProvedor, match="não é JSON válido"):
        provedor.buscar("python")


def test_execucao_sem_credenciais_externas(tmp_path: Path) -> None:
    provedor = ProvedorHttpConfiguravel(settings(tmp_path))
    with pytest.raises(ProvedorNaoConfigurado, match="JOB_API_URL"):
        provedor.buscar("python")
    assert ProvedorDemonstracao().buscar("Python")


def test_token_obrigatorio_ausente(tmp_path: Path) -> None:
    provedor = ProvedorHttpConfiguravel(
        settings(tmp_path, api_url="https://api.example.test/jobs", api_requires_token=True)
    )
    with pytest.raises(ProvedorNaoConfigurado, match="JOB_API_TOKEN"):
        provedor.buscar("python")


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_erro_http_e_traduzido(tmp_path: Path, status: int) -> None:
    provedor = ProvedorHttpConfiguravel(
        settings(tmp_path, api_url="https://api.example.test/jobs"),
        session=SessaoFalsa(RespostaHttpErro(status)),  # type: ignore[arg-type]
        sleeper=lambda _: None,
    )
    with pytest.raises(ErroProvedor, match=f"HTTP {status}"):
        provedor.buscar("python")


def test_http_repete_uma_vez_em_erro_5xx(tmp_path: Path) -> None:
    session = SessaoSequencial([RespostaHttpErro(503), RespostaJson()])
    waits: list[float] = []
    provedor = ProvedorHttpConfiguravel(
        settings(tmp_path, api_url="https://api.example.test/jobs"),
        session=session,  # type: ignore[arg-type]
        sleeper=waits.append,
    )
    assert provedor.buscar("python")[0].titulo == "Estágio Python"
    assert session.calls == 2
    assert waits == [0.25]


def test_limite_de_requisicoes_tem_mensagem_especifica(tmp_path: Path) -> None:
    provedor = ProvedorHttpConfiguravel(
        settings(tmp_path, api_url="https://api.example.test/jobs"),
        session=SessaoFalsa(RespostaHttpErro(429)),  # type: ignore[arg-type]
    )
    with pytest.raises(ErroProvedor, match="Limite de requisições"):
        provedor.buscar("python")


def test_timeout_nao_expoe_token(tmp_path: Path) -> None:
    provedor = ProvedorHttpConfiguravel(
        settings(
            tmp_path,
            api_url="https://api.example.test/jobs",
            api_token="token-super-secreto",
        ),
        session=SessaoTimeout(),  # type: ignore[arg-type]
    )
    with pytest.raises(ErroProvedor) as erro:
        provedor.buscar("python")
    assert "tempo limite" in str(erro.value)
    assert "token-super-secreto" not in str(erro.value)


def test_url_com_credenciais_e_rejeitada(tmp_path: Path) -> None:
    provedor = ProvedorHttpConfiguravel(
        settings(tmp_path, api_url="https://usuario:senha@api.example.test/jobs")
    )
    with pytest.raises(ProvedorNaoConfigurado, match="não pode conter usuário ou senha"):
        provedor.buscar("python")


def test_vaga_sem_empresa_e_link_recebe_valores_seguros(tmp_path: Path) -> None:
    provedor = ProvedorHttpConfiguravel(
        settings(tmp_path, api_url="https://api.example.test/jobs"),
        session=SessaoFalsa(RespostaJson()),  # type: ignore[arg-type]
    )
    vaga = provedor.buscar("python")[0]
    assert vaga.empresa == "Não informada"
    assert vaga.link == ""
