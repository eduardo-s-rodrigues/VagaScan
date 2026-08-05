from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS vagas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    empresa TEXT NOT NULL,
    localizacao TEXT NOT NULL DEFAULT '',
    modalidade TEXT NOT NULL DEFAULT 'não informada',
    nivel TEXT NOT NULL DEFAULT 'não informado',
    descricao TEXT NOT NULL,
    link TEXT NOT NULL DEFAULT '',
    link_normalizado TEXT NOT NULL DEFAULT '',
    fonte TEXT NOT NULL,
    identificador_externo TEXT NOT NULL DEFAULT '',
    chave_conteudo TEXT NOT NULL,
    data_publicacao TEXT,
    data_encontrada TEXT NOT NULL DEFAULT (date('now')),
    compatibilidade REAL CHECK (compatibilidade IS NULL OR compatibilidade BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'encontrada',
    observacoes TEXT NOT NULL DEFAULT '',
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_vagas_fonte_externo
ON vagas(fonte, identificador_externo) WHERE identificador_externo <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_vagas_link
ON vagas(link_normalizado) WHERE link_normalizado <> '';
CREATE INDEX IF NOT EXISTS idx_vagas_chave_conteudo ON vagas(chave_conteudo);
CREATE INDEX IF NOT EXISTS idx_vagas_status ON vagas(status);
CREATE INDEX IF NOT EXISTS idx_vagas_compatibilidade ON vagas(compatibilidade DESC);

CREATE TABLE IF NOT EXISTS requisitos_vaga (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vaga_id INTEGER NOT NULL REFERENCES vagas(id) ON DELETE CASCADE,
    requisito TEXT NOT NULL,
    categoria TEXT NOT NULL,
    encontrado_no_perfil INTEGER NOT NULL CHECK (encontrado_no_perfil IN (0, 1)),
    peso REAL NOT NULL DEFAULT 1.0 CHECK (peso > 0),
    UNIQUE(vaga_id, requisito, categoria)
);
CREATE INDEX IF NOT EXISTS idx_requisitos_vaga ON requisitos_vaga(vaga_id);

CREATE TABLE IF NOT EXISTS candidaturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vaga_id INTEGER NOT NULL UNIQUE REFERENCES vagas(id) ON DELETE CASCADE,
    data_candidatura TEXT NOT NULL,
    etapa TEXT NOT NULL,
    proxima_acao TEXT NOT NULL DEFAULT '',
    data_proxima_acao TEXT,
    observacoes TEXT NOT NULL DEFAULT '',
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_candidaturas_proxima_acao
ON candidaturas(data_proxima_acao) WHERE data_proxima_acao IS NOT NULL;

CREATE TABLE IF NOT EXISTS historico_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vaga_id INTEGER NOT NULL REFERENCES vagas(id) ON DELETE CASCADE,
    status_anterior TEXT NOT NULL,
    status_novo TEXT NOT NULL,
    data_alteracao TEXT NOT NULL DEFAULT (datetime('now')),
    observacao TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_historico_vaga ON historico_status(vaga_id, data_alteracao DESC);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Abre uma conexão de leitura e garante seu fechamento."""
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.transaction() as connection:
            connection.executescript(SCHEMA)
