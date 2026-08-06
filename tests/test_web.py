from __future__ import annotations

import base64
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vagasscan.config import PROJECT_ROOT, Settings
from vagasscan.security import gerar_hash_senha
from vagasscan.web.app import create_app


class Response:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "count": 1,
            "results": [
                {
                    "id": "web-adzuna-1",
                    "title": "<script>alert(1)</script> Python Júnior",
                    "description": "Python, SQL e FastAPI. Docker desejável.",
                    "redirect_url": "https://www.adzuna.com.br/details/1",
                    "company": {"display_name": "Empresa Web"},
                    "location": {"display_name": "Remoto no Brasil"},
                }
            ],
        }


class Session:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *args: Any, **kwargs: Any) -> Response:
        self.calls += 1
        return Response()


@pytest.fixture
def web_settings(tmp_path: Path) -> Settings:
    profile = tmp_path / "profile.json"
    public_profile = tmp_path / "profile_public.json"
    content = (PROJECT_ROOT / "data" / "profile.json").read_text(encoding="utf-8")
    profile.write_text(content, encoding="utf-8")
    public_profile.write_text(
        (PROJECT_ROOT / "data" / "profile_public.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return Settings(
        database_path=tmp_path / "main.db",
        demo_database_path=tmp_path / "demo.db",
        public_database_path=tmp_path / "public.db",
        profile_path=profile,
        public_profile_path=public_profile,
        keywords_path=PROJECT_ROOT / "data" / "keywords.json",
        log_path=tmp_path / "web.log",
        adzuna_app_id="app-id-test",
        adzuna_app_key="app-key-super-secreta",
        admin_username="admin",
        admin_password_hash=gerar_hash_senha("Senha web muito segura 123!"),
        session_secret="segredo-de-sessao-testes-" * 3,
    )


def csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


def login(client: TestClient) -> None:
    token = csrf(client.get("/login").text)
    response = client.post(
        "/login",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "Senha web muito segura 123!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def session_payload(client: TestClient) -> dict[str, Any]:
    cookie = client.cookies.get("vagasscan_session")
    assert cookie
    encoded = cookie.split(".", 1)[0]
    decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4))
    return json.loads(decoded)


def test_home_health_headers_e_protecao_privada(web_settings: Settings) -> None:
    with TestClient(create_app(web_settings, adzuna_session=Session())) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "Encontre, analise e acompanhe" in home.text
        assert client.get("/health").json() == {"status": "ok"}
        assert "frame-ancestors 'none'" in home.headers["content-security-policy"]
        assert "strict-transport-security" not in home.headers
        protected = client.get("/dashboard", follow_redirects=False)
        assert protected.status_code == 303
        assert protected.headers["location"] == "/login"
        assert "app-key-super-secreta" not in home.text
    with TestClient(
        create_app(web_settings, adzuna_session=Session()),
        base_url="https://testserver",
    ) as secure_client:
        assert "strict-transport-security" in secure_client.get("/").headers


def test_busca_publica_atribuicao_escape_cache_e_isolamento(
    web_settings: Settings,
) -> None:
    session = Session()
    with TestClient(create_app(web_settings, adzuna_session=session)) as client:
        first = client.get("/buscar?termo=python&provedor=adzuna")
        assert first.status_code == 200
        assert "Vagas fornecidas pela Adzuna" in first.text
        assert "Jobs by" in first.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in first.text
        assert "<script>alert(1)</script>" not in first.text
        second = client.get("/buscar?termo=python&provedor=adzuna")
        assert "Resultado vindo do cache" in second.text
        assert session.calls == 1
        assert len(client.app.state.public.vagas.listar()) == 1
        assert client.app.state.private.vagas.listar() == []
        detail = client.get("/vagas/1")
        assert detail.status_code == 200
        assert "Abrir vaga original" in detail.text


def test_analise_publica_nao_salva_e_valida_tamanho(web_settings: Settings) -> None:
    with TestClient(create_app(web_settings, adzuna_session=Session())) as client:
        token = csrf(client.get("/analisar").text)
        result = client.post(
            "/analisar",
            data={"csrf_token": token, "descricao": "Python, SQL e comunicação."},
        )
        assert result.status_code == 200
        assert "Compatibilidade estimada" in result.text
        assert client.app.state.public.vagas.listar() == []
        token = csrf(result.text)
        too_long = client.post(
            "/analisar", data={"csrf_token": token, "descricao": "x" * 20_001}
        )
        assert too_long.status_code == 400


def test_login_csrf_dashboard_cadastro_logout(web_settings: Settings) -> None:
    with TestClient(create_app(web_settings, adzuna_session=Session())) as client:
        bad_csrf = client.post("/login", data={"username": "admin", "password": "x"})
        assert bad_csrf.status_code == 403
        token = csrf(client.get("/login").text)
        invalid = client.post(
            "/login",
            data={"csrf_token": token, "username": "admin", "password": "senha errada"},
        )
        assert invalid.status_code == 401
        login(client)
        assert set(session_payload(client)) == {"admin", "csrf_token"}
        assert client.get("/dashboard").status_code == 200

        form_page = client.get("/dashboard/vagas/nova")
        created = client.post(
            "/dashboard/vagas/nova",
            data={
                "csrf_token": csrf(form_page.text),
                "titulo": "Backend Python",
                "empresa": "Empresa",
                "localizacao": "Campinas",
                "descricao": "Python, SQL e Git.",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        assert created.headers["location"] == "/dashboard/vagas/1"
        detail = client.get("/dashboard/vagas/1")
        assert detail.status_code == 200
        status = client.post(
            "/dashboard/vagas/1/status",
            data={"csrf_token": csrf(detail.text), "status": "interessante"},
            follow_redirects=False,
        )
        assert status.status_code == 303
        client.get("/dashboard/vagas/1")
        assert set(session_payload(client)) == {"admin", "csrf_token"}

        candidaturas = client.get("/dashboard/candidaturas")
        candidatura = client.post(
            "/dashboard/candidaturas",
            data={
                "csrf_token": csrf(candidaturas.text),
                "vaga_id": "1",
                "data_candidatura": "2026-08-05",
                "etapa": "candidatura_enviada",
                "proxima_acao": "Aguardar retorno",
            },
            follow_redirects=False,
        )
        assert candidatura.status_code == 303
        assert client.get("/dashboard/relatorios").status_code == 200

        profile = client.get("/dashboard/perfil")
        saved_profile = client.post(
            "/dashboard/perfil",
            data={
                "csrf_token": csrf(profile.text),
                "areas_desejadas": "Backend",
                "conhecimentos": "Python\nSQL",
                "experiencias": "Projeto pessoal",
                "localidades_desejadas": "Campinas",
                "modalidades_desejadas": "Remoto",
                "idiomas": "Português",
                "niveis_desejados": "Júnior",
                "formacao": "ADS",
                "nivel_profissional": "Júnior",
                "experiencia_anos": "1",
            },
            follow_redirects=False,
        )
        assert saved_profile.status_code == 303
        assert list(web_settings.profile_path.parent.glob("profile.json.bak-*"))

        page = client.get("/dashboard")
        logout = client.post(
            "/logout", data={"csrf_token": csrf(page.text)}, follow_redirects=False
        )
        assert logout.status_code == 303
        assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_login_limita_cinco_falhas_sem_contar_sucesso(web_settings: Settings) -> None:
    with TestClient(create_app(web_settings, adzuna_session=Session())) as client:
        for _ in range(5):
            page = client.get("/login")
            response = client.post(
                "/login",
                data={
                    "csrf_token": csrf(page.text),
                    "username": "admin",
                    "password": "incorreta",
                },
            )
            assert response.status_code == 401
        page = client.get("/login")
        blocked = client.post(
            "/login",
            data={
                "csrf_token": csrf(page.text),
                "username": "admin",
                "password": "Senha web muito segura 123!",
            },
        )
        assert blocked.status_code == 401
        assert "Muitas tentativas" in blocked.text
        limiter_keys = [key for _, key in client.app.state.rate_limiter.events]
        assert "testclient" not in limiter_keys


def test_public_demo_desativada_e_credenciais_ausentes(
    web_settings: Settings,
) -> None:
    disabled = replace(web_settings, public_demo=False)
    with TestClient(create_app(disabled, adzuna_session=Session())) as client:
        assert client.get("/").status_code == 200
        assert client.get("/buscar?termo=python").status_code == 403


def test_web_nao_expoe_credencial_em_erro(web_settings: Settings) -> None:
    missing = replace(web_settings, adzuna_app_id="", adzuna_app_key="")
    with TestClient(create_app(missing, adzuna_session=Session())) as client:
        response = client.get("/buscar?termo=python")
        assert response.status_code == 400
        assert "ADZUNA_APP_ID" in response.text
        assert "app-key-super-secreta" not in response.text
