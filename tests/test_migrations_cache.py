from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave
from vagasscan.database import Database
from vagasscan.models import ConsultaVagas, ResultadoBusca, Vaga
from vagasscan.providers.base import ErroProvedor, ProvedorVagas
from vagasscan.repositories.cache import CacheBuscaRepository
from vagasscan.repositories.vagas import VagaRepository
from vagasscan.services.vagas import VagaService

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProvedorTransitorio(ProvedorVagas):
    nome = "adzuna"

    def buscar(self, termo: str, localizacao: str = "") -> list[Vaga]:
        raise ErroProvedor(
            "Fonte temporariamente indisponível.",
            codigo="transiente",
            transitorio=True,
        )


def test_migracao_preserva_banco_legado(tmp_path: Path) -> None:
    database = Database(tmp_path / "legado.db")
    with database.transaction() as connection:
        connection.execute(
            """CREATE TABLE vagas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL,
                empresa TEXT NOT NULL, localizacao TEXT NOT NULL DEFAULT '',
                modalidade TEXT NOT NULL DEFAULT 'não informada',
                nivel TEXT NOT NULL DEFAULT 'não informado', descricao TEXT NOT NULL,
                link TEXT NOT NULL DEFAULT '', link_normalizado TEXT NOT NULL DEFAULT '',
                fonte TEXT NOT NULL, identificador_externo TEXT NOT NULL DEFAULT '',
                chave_conteudo TEXT NOT NULL, data_publicacao TEXT,
                data_encontrada TEXT NOT NULL DEFAULT (date('now')),
                compatibilidade REAL, status TEXT NOT NULL DEFAULT 'encontrada',
                observacoes TEXT NOT NULL DEFAULT '',
                criado_em TEXT NOT NULL DEFAULT (datetime('now')),
                atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
            )"""
        )
        connection.execute(
            """INSERT INTO vagas
               (titulo, empresa, descricao, fonte, chave_conteudo)
               VALUES ('Legada', 'Empresa', 'Python', 'manual', 'legada|empresa|')"""
        )
    database.initialize()
    with database.connection() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(vagas)")}
        indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index'"
            )
        }
        versions = [row["version"] for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )]
        row = connection.execute("SELECT titulo, empresa FROM vagas WHERE id = 1").fetchone()
    assert {"salario_min", "salario_max", "categoria", "tipo_contrato", "jornada"} <= columns
    assert {
        "uq_vagas_fonte_externo",
        "idx_vagas_status",
        "idx_cache_buscas_provedor_expira",
    } <= indexes
    assert versions == [1, 2, 3]
    assert dict(row) == {"titulo": "Legada", "empresa": "Empresa"}


def test_cache_valido_expirado_e_chave_sem_segredo(tmp_path: Path) -> None:
    database = Database(tmp_path / "cache.db")
    database.initialize()
    cache = CacheBuscaRepository(database)
    query = ConsultaVagas(termo="python", localizacao="Campinas", remoto=True)
    result = ResultadoBusca(
        vagas=[Vaga("Python", "Empresa", "Remoto", "Python")],
        total_aproximado=10,
    )
    key, canonical = cache.chave("adzuna", query)
    assert len(key) == 64
    assert "app_key" not in canonical
    cache.salvar("adzuna", query, result, 30)
    valid = cache.obter("adzuna", query)
    assert valid is not None and valid.veio_cache and not valid.cache_desatualizado

    now = datetime.now(UTC)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE cache_buscas SET criado_em = ?, expira_em = ? WHERE chave = ?",
            ((now - timedelta(hours=1)).isoformat(), (now - timedelta(minutes=1)).isoformat(), key),
        )
    assert cache.obter("adzuna", query) is None
    stale = cache.obter("adzuna", query, permitir_expirado=True)
    assert stale is not None and stale.cache_desatualizado


def test_servico_usa_cache_expirado_so_em_falha_transitoria(tmp_path: Path) -> None:
    database = Database(tmp_path / "fallback.db")
    database.initialize()
    cache = CacheBuscaRepository(database)
    query = ConsultaVagas(termo="python")
    cache.salvar(
        "adzuna",
        query,
        ResultadoBusca(vagas=[Vaga("Python", "Empresa", "Remoto", "Python")]),
        30,
    )
    now = datetime.now(UTC)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE cache_buscas SET criado_em = ?, expira_em = ?",
            ((now - timedelta(hours=1)).isoformat(), (now - timedelta(minutes=1)).isoformat()),
        )
    service = VagaService(
        VagaRepository(database),
        AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json"),
        CalculadoraCompatibilidade(),
        PROJECT_ROOT / "data" / "profile_public.json",
        cache,
    )
    result = service.buscar_e_salvar(ProvedorTransitorio(), query)
    assert result["veio_cache"] is True
    assert result["cache_desatualizado"] is True
    assert result["recebidas"] == 1
    assert "cache anterior" in result["erros"][0]
