from __future__ import annotations

import json
from pathlib import Path

import pytest

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave
from vagasscan.config import PROJECT_ROOT
from vagasscan.database import Database
from vagasscan.repositories.vagas import VagaRepository
from vagasscan.services.vagas import VagaService


@pytest.fixture
def database(tmp_path: Path) -> Database:
    banco = Database(tmp_path / "teste.db")
    banco.initialize()
    return banco


@pytest.fixture
def repository(database: Database) -> VagaRepository:
    return VagaRepository(database)


@pytest.fixture
def profile_path(tmp_path: Path) -> Path:
    perfil = json.loads((PROJECT_ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
    destino = tmp_path / "profile.json"
    destino.write_text(json.dumps(perfil, ensure_ascii=False), encoding="utf-8")
    return destino


@pytest.fixture
def service(repository: VagaRepository, profile_path: Path) -> VagaService:
    return VagaService(
        repository,
        AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json"),
        CalculadoraCompatibilidade(),
        profile_path,
    )
