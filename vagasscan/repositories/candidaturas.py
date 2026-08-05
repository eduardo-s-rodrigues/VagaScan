from __future__ import annotations

from typing import Any

from vagasscan.database import Database
from vagasscan.models import ETAPAS_CANDIDATURA, Candidatura
from vagasscan.utils.validation import validar_data_iso


class CandidaturaRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def registrar(self, candidatura: Candidatura) -> int:
        data_candidatura = validar_data_iso(
            candidatura.data_candidatura, "Data da candidatura"
        )
        data_proxima_acao = validar_data_iso(
            candidatura.data_proxima_acao, "Data da próxima ação", opcional=True
        )
        if candidatura.etapa not in ETAPAS_CANDIDATURA:
            raise ValueError(f"Etapa de candidatura inválida: {candidatura.etapa}")
        with self.database.transaction() as connection:
            vaga = connection.execute(
                "SELECT status FROM vagas WHERE id = ?", (candidatura.vaga_id,)
            ).fetchone()
            if not vaga:
                raise ValueError(f"Vaga #{candidatura.vaga_id} não encontrada.")
            existente = connection.execute(
                "SELECT id FROM candidaturas WHERE vaga_id = ?", (candidatura.vaga_id,)
            ).fetchone()
            if existente:
                raise ValueError(
                    f"A vaga #{candidatura.vaga_id} já possui a candidatura #{existente['id']}."
                )
            cursor = connection.execute(
                """INSERT INTO candidaturas
                   (vaga_id, data_candidatura, etapa, proxima_acao,
                    data_proxima_acao, observacoes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    candidatura.vaga_id,
                    data_candidatura,
                    candidatura.etapa,
                    str(candidatura.proxima_acao or "").strip(),
                    data_proxima_acao,
                    str(candidatura.observacoes or "").strip(),
                ),
            )
            self._sincronizar_status(
                connection,
                candidatura.vaga_id,
                vaga["status"],
                candidatura.etapa,
                "Etapa sincronizada com a candidatura",
            )
            return int(cursor.lastrowid)

    def atualizar_etapa(
        self,
        candidatura_id: int,
        etapa: str,
        proxima_acao: str,
        data_proxima_acao: str | None,
        observacoes: str = "",
    ) -> None:
        if etapa not in ETAPAS_CANDIDATURA:
            raise ValueError(f"Etapa de candidatura inválida: {etapa}")
        data_validada = validar_data_iso(
            data_proxima_acao, "Data da próxima ação", opcional=True
        )
        with self.database.transaction() as connection:
            atual = connection.execute(
                """SELECT c.vaga_id, v.status
                   FROM candidaturas c JOIN vagas v ON v.id = c.vaga_id
                   WHERE c.id = ?""",
                (candidatura_id,),
            ).fetchone()
            if not atual:
                raise ValueError(f"Candidatura #{candidatura_id} não encontrada.")
            connection.execute(
                """UPDATE candidaturas
                   SET etapa = ?, proxima_acao = ?, data_proxima_acao = ?,
                       observacoes = ?, atualizado_em = datetime('now')
                   WHERE id = ?""",
                (
                    etapa,
                    str(proxima_acao or "").strip(),
                    data_validada,
                    str(observacoes or "").strip(),
                    candidatura_id,
                ),
            )
            self._sincronizar_status(
                connection,
                atual["vaga_id"],
                atual["status"],
                etapa,
                "Etapa atualizada na candidatura",
            )

    @staticmethod
    def _sincronizar_status(
        connection: Any,
        vaga_id: int,
        status_anterior: str,
        status_novo: str,
        observacao: str,
    ) -> None:
        if status_anterior == status_novo:
            return
        connection.execute(
            """UPDATE vagas SET status = ?, atualizado_em = datetime('now')
               WHERE id = ?""",
            (status_novo, vaga_id),
        )
        connection.execute(
            """INSERT INTO historico_status
               (vaga_id, status_anterior, status_novo, observacao)
               VALUES (?, ?, ?, ?)""",
            (vaga_id, status_anterior, status_novo, observacao),
        )

    def listar(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """SELECT c.*, v.titulo, v.empresa
                       FROM candidaturas c JOIN vagas v ON v.id = c.vaga_id
                       ORDER BY c.data_proxima_acao IS NULL, c.data_proxima_acao, c.id DESC"""
                ).fetchall()
            ]
