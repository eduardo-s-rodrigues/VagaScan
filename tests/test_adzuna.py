from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from vagasscan.config import Settings
from vagasscan.models import ConsultaVagas
from vagasscan.providers import ErroProvedor, ProvedorAdzuna, ProvedorNaoConfigurado


def settings(tmp_path: Path, **changes: Any) -> Settings:
    values: dict[str, Any] = {
        "database_path": tmp_path / "main.db",
        "demo_database_path": tmp_path / "demo.db",
        "profile_path": tmp_path / "profile.json",
        "keywords_path": tmp_path / "keywords.json",
        "log_path": tmp_path / "app.log",
        "adzuna_app_id": "id-seguro",
        "adzuna_app_key": "chave-super-secreta",
    }
    values.update(changes)
    return Settings(**values)


class Response:
    def __init__(self, payload: Any = None, status: int = 200, *, invalid_json: bool = False):
        self.payload = payload
        self.status_code = status
        self.invalid_json = invalid_json

    def json(self) -> Any:
        if self.invalid_json:
            raise requests.exceptions.JSONDecodeError("inválido", "<html>", 0)
        return self.payload


class Session:
    def __init__(self, response: Any):
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def payload() -> dict[str, Any]:
    return {
        "count": 81,
        "results": [
            {
                "id": "adz-1",
                "title": "Python Júnior Remoto",
                "description": "Python, SQL e home office.",
                "redirect_url": "https://www.adzuna.com.br/details/1",
                "url": "https://alternativa.invalid/1",
                "company": {"display_name": "Empresa API"},
                "location": {"display_name": "Remoto no Brasil"},
                "created": "2026-08-05T10:00:00Z",
                "contract_type": "permanent",
                "contract_time": "full_time",
                "salary_min": 3500,
                "salary_max": 5000,
                "category": {"label": "IT Jobs"},
            }
        ],
    }


def test_credenciais_ausentes(tmp_path: Path) -> None:
    provider = ProvedorAdzuna(settings(tmp_path, adzuna_app_id="", adzuna_app_key=""))
    with pytest.raises(ProvedorNaoConfigurado, match="ADZUNA_APP_ID"):
        provider.buscar("python")


def test_busca_monta_endpoint_parametros_e_converte(tmp_path: Path) -> None:
    session = Session(Response(payload()))
    provider = ProvedorAdzuna(settings(tmp_path), session=session)  # type: ignore[arg-type]
    result = provider.consultar(
        ConsultaVagas(
            termo="python",
            localizacao="Campinas",
            pagina=3,
            resultados_por_pagina=10,
            remoto=True,
            tipo_contrato="permanent",
            jornada="full_time",
            ordenacao="date",
            distancia_km=25,
            pais="br",
        )
    )
    url, request = session.calls[0]
    assert url.endswith("/br/search/3")
    assert request["params"] == {
        "app_id": "id-seguro",
        "app_key": "chave-super-secreta",
        "results_per_page": 10,
        "what": "python",
        "where": "Campinas",
        "sort_by": "date",
        "distance": 25,
        "permanent": "1",
        "full_time": "1",
    }
    assert "Authorization" not in request["headers"]
    assert result.total_aproximado == 81
    vaga = result.vagas[0]
    assert vaga.identificador_externo == "adz-1"
    assert vaga.link == "https://www.adzuna.com.br/details/1"
    assert vaga.empresa == "Empresa API"
    assert vaga.localizacao == "Remoto no Brasil"
    assert vaga.salario_min == 3500
    assert vaga.salario_max == 5000
    assert vaga.categoria == "IT Jobs"
    assert vaga.tipo_contrato == "permanent"
    assert vaga.jornada == "full_time"
    assert vaga.fonte == "adzuna"


def test_campos_opcionais_e_resultado_vazio(tmp_path: Path) -> None:
    minimal = {"results": [{"id": "2"}, "inválido"]}
    provider = ProvedorAdzuna(
        settings(tmp_path), session=Session(Response(minimal))  # type: ignore[arg-type]
    )
    result = provider.consultar(ConsultaVagas(termo="python"))
    assert result.vagas[0].titulo == "Título não informado"
    assert result.vagas[0].empresa == "Não informada"
    assert result.erros == ["Resultado 2 ignorado por formato inválido."]

    empty = ProvedorAdzuna(
        settings(tmp_path), session=Session(Response({"count": 0, "results": []}))  # type: ignore[arg-type]
    )
    assert empty.buscar("python") == []


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 429, 500, 503])
def test_erros_http_sao_seguros(tmp_path: Path, status: int) -> None:
    provider = ProvedorAdzuna(
        settings(tmp_path),
        session=Session(Response({}, status)),  # type: ignore[arg-type]
        sleeper=lambda _: None,
    )
    with pytest.raises(ErroProvedor) as caught:
        provider.buscar("python")
    message = str(caught.value)
    assert "chave-super-secreta" not in message
    assert "id-seguro" not in message
    if status == 429:
        assert caught.value.limite is True
    if status >= 500:
        assert caught.value.transitorio is True


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (requests.Timeout("chave-super-secreta"), "tempo limite"),
        (requests.ConnectionError("chave-super-secreta"), "conexão"),
    ],
)
def test_erros_de_rede_nao_expoem_segredo(
    tmp_path: Path, response: Exception, expected: str
) -> None:
    provider = ProvedorAdzuna(
        settings(tmp_path),
        session=Session(response),  # type: ignore[arg-type]
        sleeper=lambda _: None,
    )
    with pytest.raises(ErroProvedor) as caught:
        provider.buscar("python")
    assert expected in str(caught.value)
    assert "chave-super-secreta" not in str(caught.value)


def test_json_e_estrutura_invalidos(tmp_path: Path) -> None:
    invalid_json = ProvedorAdzuna(
        settings(tmp_path), session=Session(Response(invalid_json=True))  # type: ignore[arg-type]
    )
    with pytest.raises(ErroProvedor, match="JSON válido"):
        invalid_json.buscar("python")
    invalid_structure = ProvedorAdzuna(
        settings(tmp_path), session=Session(Response({"items": []}))  # type: ignore[arg-type]
    )
    with pytest.raises(ErroProvedor, match="estrutura"):
        invalid_structure.buscar("python")


@pytest.mark.parametrize(
    "changes",
    [
        {"pagina": 0},
        {"resultados_por_pagina": 51},
        {"pais": "xx"},
        {"distancia_km": 101},
        {"ordenacao": "inventada"},
        {"tipo_contrato": "freelance"},
        {"jornada": "flex"},
        {"termo": "x" * 101},
        {"localizacao": "x" * 101},
    ],
)
def test_filtros_invalidos_nao_fazem_chamada(tmp_path: Path, changes: dict[str, Any]) -> None:
    session = Session(Response(payload()))
    provider = ProvedorAdzuna(settings(tmp_path), session=session)  # type: ignore[arg-type]
    query = ConsultaVagas(termo="python")
    for key, value in changes.items():
        setattr(query, key, value)
    with pytest.raises(ErroProvedor):
        provider.consultar(query)
    assert session.calls == []
