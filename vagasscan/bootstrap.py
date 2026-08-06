from __future__ import annotations

from dataclasses import dataclass

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave
from vagasscan.config import Settings
from vagasscan.database import Database
from vagasscan.reports import GeradorRelatorios
from vagasscan.repositories.cache import CacheBuscaRepository
from vagasscan.repositories.candidaturas import CandidaturaRepository
from vagasscan.repositories.vagas import VagaRepository
from vagasscan.services.profile import PerfilService
from vagasscan.services.vagas import VagaService


@dataclass(slots=True)
class AppContext:
    settings: Settings
    database: Database
    vagas: VagaRepository
    candidaturas: CandidaturaRepository
    relatorios: GeradorRelatorios
    vaga_service: VagaService
    perfil_service: PerfilService


def criar_contexto(settings: Settings, *, publico: bool = False) -> AppContext:
    database = Database(
        settings.public_database_path if publico else settings.database_path
    )
    database.initialize()
    profile_path = settings.public_profile_path if publico else settings.profile_path
    vagas = VagaRepository(database)
    cache = CacheBuscaRepository(database)
    return AppContext(
        settings=settings,
        database=database,
        vagas=vagas,
        candidaturas=CandidaturaRepository(database),
        relatorios=GeradorRelatorios(database),
        vaga_service=VagaService(
            vagas,
            AnalisadorPalavrasChave(settings.keywords_path),
            CalculadoraCompatibilidade(),
            profile_path,
            cache=cache,
            cache_minutes=settings.adzuna_cache_minutes,
            max_extra_pages_for_filter=settings.max_extra_pages_for_filter,
        ),
        perfil_service=PerfilService(profile_path),
    )
