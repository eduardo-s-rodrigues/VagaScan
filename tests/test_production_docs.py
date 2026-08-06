from __future__ import annotations

from pathlib import Path

import pytest

from vagasscan.config import PROJECT_ROOT, load_settings


def test_novas_variaveis_tem_defaults_e_limites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VAGASSCAN_MAX_EXTRA_PAGES_FOR_FILTER", raising=False)
    monkeypatch.delenv("VAGASSCAN_SAVED_JOBS_LIMIT", raising=False)
    settings = load_settings(tmp_path / "ausente.env")
    assert settings.max_extra_pages_for_filter == 2
    assert settings.saved_jobs_limit == 200

    monkeypatch.setenv("VAGASSCAN_MAX_EXTRA_PAGES_FOR_FILTER", "99")
    monkeypatch.setenv("VAGASSCAN_SAVED_JOBS_LIMIT", "9999")
    limited = load_settings(tmp_path / "ausente.env")
    assert limited.max_extra_pages_for_filter == 2
    assert limited.saved_jobs_limit == 500


def test_volume_railway_e_variaveis_estao_documentados() -> None:
    deploy = (PROJECT_ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for text in (
        "/app/data",
        "VAGASSCAN_DATABASE=/app/data/vagasscan.db",
        "VAGASSCAN_PUBLIC_DATABASE=/app/data/vagasscan_public.db",
        "VAGASSCAN_DEMO_DATABASE=/app/data/vagasscan_demo.db",
        "VAGASSCAN_LOG=/app/data/vagasscan.log",
        "Backup e restauração",
        "PostgreSQL",
        "um único processo",
    ):
        assert text in deploy
    assert "VAGASSCAN_MAX_EXTRA_PAGES_FOR_FILTER=2" in env_example
    assert "VAGASSCAN_SAVED_JOBS_LIMIT=200" in env_example


def test_templates_publicos_nao_contem_nomes_de_segredos() -> None:
    templates = PROJECT_ROOT / "vagasscan" / "web" / "templates"
    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in templates.glob("*.html")
    )
    assert "ADZUNA_APP_ID" not in public_text
    assert "ADZUNA_APP_KEY" not in public_text
    assert "VAGASSCAN_SESSION_SECRET" not in public_text


def test_guia_documenta_regra_completa_de_confianca() -> None:
    guide = (PROJECT_ROOT / "GUIA_DE_ESTUDO.md").read_text(encoding="utf-8")
    for text in (
        "Regra completa da compatibilidade",
        "Regra completa da confiança",
        "um ou dois requisitos",
        "menos 15 pontos",
        "alta exige pelo menos seis",
    ):
        assert text in guide
