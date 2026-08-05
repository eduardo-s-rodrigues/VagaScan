from __future__ import annotations

import math
import sqlite3
from typing import Any

from vagasscan.database import Database
from vagasscan.models import STATUS_VAGAS, Requisito, Vaga
from vagasscan.utils.text import normalizar_texto, normalizar_url


class VagaDuplicadaError(ValueError):
    """Indica que uma vaga já existe e informa a regra que coincidiu."""


class VagaRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def chave_conteudo(vaga: Vaga) -> str:
        return "|".join(
            normalizar_texto(valor) for valor in (vaga.titulo, vaga.empresa, vaga.localizacao)
        )

    @staticmethod
    def _preparar(vaga: Vaga) -> None:
        vaga.titulo = str(vaga.titulo or "").strip()
        vaga.descricao = str(vaga.descricao or "").strip()
        if not vaga.titulo:
            raise ValueError("O título da vaga é obrigatório.")
        if not vaga.descricao:
            raise ValueError("A descrição da vaga é obrigatória.")
        vaga.empresa = str(vaga.empresa or "").strip() or "Não informada"
        vaga.localizacao = str(vaga.localizacao or "").strip() or "Não informada"
        vaga.modalidade = str(vaga.modalidade or "").strip() or "não informada"
        vaga.nivel = str(vaga.nivel or "").strip() or "não informado"
        vaga.fonte = str(vaga.fonte or "").strip() or "manual"
        vaga.link = str(vaga.link or "").strip()
        vaga.identificador_externo = str(vaga.identificador_externo or "").strip()
        vaga.observacoes = str(vaga.observacoes or "").strip()
        if vaga.status not in STATUS_VAGAS:
            raise ValueError(f"Status inválido: {vaga.status}")
        if vaga.compatibilidade is not None:
            try:
                vaga.compatibilidade = float(vaga.compatibilidade)
            except (TypeError, ValueError) as exc:
                raise ValueError("A compatibilidade deve ser um número entre 0 e 100.") from exc
            if not math.isfinite(vaga.compatibilidade) or not 0 <= vaga.compatibilidade <= 100:
                raise ValueError("A compatibilidade deve estar entre 0 e 100.")

    @staticmethod
    def _integridade_e_duplicata_vaga(exc: sqlite3.IntegrityError) -> bool:
        mensagem = str(exc)
        return "vagas.fonte, vagas.identificador_externo" in mensagem or (
            "vagas.link_normalizado" in mensagem
        )

    def encontrar_duplicata(self, vaga: Vaga) -> tuple[dict[str, Any] | None, str | None]:
        link = normalizar_url(vaga.link)
        chave = self.chave_conteudo(vaga)
        with self.database.connection() as connection:
            if vaga.identificador_externo:
                row = connection.execute(
                    "SELECT * FROM vagas WHERE fonte = ? AND identificador_externo = ?",
                    (vaga.fonte, vaga.identificador_externo),
                ).fetchone()
                if row:
                    return dict(row), "fonte e identificador externo"
            if link:
                row = connection.execute(
                    "SELECT * FROM vagas WHERE link_normalizado = ?", (link,)
                ).fetchone()
                if row:
                    return dict(row), "link normalizado"
            row = connection.execute(
                "SELECT * FROM vagas WHERE chave_conteudo = ? ORDER BY id LIMIT 1", (chave,)
            ).fetchone()
            if row:
                return dict(row), "título, empresa e localização"
        return None, None

    def criar(self, vaga: Vaga, *, aceitar_possivel_duplicata: bool = False) -> int:
        self._preparar(vaga)
        duplicata, regra = self.encontrar_duplicata(vaga)
        if duplicata and (
            regra != "título, empresa e localização" or not aceitar_possivel_duplicata
        ):
            raise VagaDuplicadaError(f"Possível duplicata da vaga #{duplicata['id']} por {regra}.")
        sql = """
            INSERT INTO vagas (
                titulo, empresa, localizacao, modalidade, nivel, descricao, link,
                link_normalizado, fonte, identificador_externo, chave_conteudo,
                data_publicacao, compatibilidade, status, observacoes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        valores = self._valores_insert(vaga)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(sql, valores)
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            if self._integridade_e_duplicata_vaga(exc):
                raise VagaDuplicadaError("A vaga coincide com um registro já existente.") from exc
            raise

    def criar_analisada(
        self,
        vaga: Vaga,
        requisitos: list[Requisito],
        *,
        aceitar_possivel_duplicata: bool = False,
    ) -> int:
        """Grava vaga e requisitos na mesma transação para evitar análise parcial."""
        self._preparar(vaga)
        duplicata, regra = self.encontrar_duplicata(vaga)
        if duplicata and (
            regra != "título, empresa e localização" or not aceitar_possivel_duplicata
        ):
            raise VagaDuplicadaError(f"Possível duplicata da vaga #{duplicata['id']} por {regra}.")
        sql = """
            INSERT INTO vagas (
                titulo, empresa, localizacao, modalidade, nivel, descricao, link,
                link_normalizado, fonte, identificador_externo, chave_conteudo,
                data_publicacao, compatibilidade, status, observacoes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(sql, self._valores_insert(vaga))
                vaga_id = int(cursor.lastrowid)
                self._inserir_requisitos(connection, vaga_id, requisitos)
                return vaga_id
        except sqlite3.IntegrityError as exc:
            if self._integridade_e_duplicata_vaga(exc):
                raise VagaDuplicadaError("A vaga coincide com um registro já existente.") from exc
            raise

    def _valores_insert(self, vaga: Vaga) -> tuple[Any, ...]:
        return (
            vaga.titulo,
            vaga.empresa,
            vaga.localizacao,
            vaga.modalidade,
            vaga.nivel,
            vaga.descricao,
            vaga.link,
            normalizar_url(vaga.link),
            vaga.fonte,
            vaga.identificador_externo,
            self.chave_conteudo(vaga),
            vaga.data_publicacao,
            vaga.compatibilidade,
            vaga.status,
            vaga.observacoes,
        )

    @staticmethod
    def _inserir_requisitos(
        connection: sqlite3.Connection, vaga_id: int, requisitos: list[Requisito]
    ) -> None:
        connection.executemany(
            """INSERT INTO requisitos_vaga
               (vaga_id, requisito, categoria, encontrado_no_perfil, peso)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (vaga_id, item.requisito, item.categoria, item.encontrado_no_perfil, item.peso)
                for item in requisitos
            ],
        )

    def obter(self, vaga_id: int) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM vagas WHERE id = ?", (vaga_id,)).fetchone()
            return dict(row) if row else None

    def listar(
        self,
        *,
        status: str = "",
        area: str = "",
        local: str = "",
        fonte: str = "",
        compatibilidade_minima: float | None = None,
        limite: int = 200,
    ) -> list[dict[str, Any]]:
        condicoes: list[str] = []
        parametros: list[Any] = []
        if status:
            condicoes.append("status = ?")
            parametros.append(status)
        if area:
            condicoes.append("(titulo LIKE ? OR descricao LIKE ?)")
            parametros.extend([f"%{area}%", f"%{area}%"])
        if local:
            condicoes.append("localizacao LIKE ?")
            parametros.append(f"%{local}%")
        if fonte:
            condicoes.append("fonte = ?")
            parametros.append(fonte)
        if compatibilidade_minima is not None:
            condicoes.append("compatibilidade >= ?")
            parametros.append(compatibilidade_minima)
        where = " WHERE " + " AND ".join(condicoes) if condicoes else ""
        sql = f"SELECT * FROM vagas{where} ORDER BY compatibilidade DESC, id DESC LIMIT ?"  # noqa: S608
        parametros.append(max(1, min(limite, 1000)))
        with self.database.connection() as connection:
            return [dict(row) for row in connection.execute(sql, parametros).fetchall()]

    def salvar_analise(
        self, vaga_id: int, compatibilidade: float, requisitos: list[Requisito]
    ) -> None:
        if not math.isfinite(compatibilidade) or not 0 <= compatibilidade <= 100:
            raise ValueError("A compatibilidade deve estar entre 0 e 100.")
        with self.database.transaction() as connection:
            existe = connection.execute("SELECT 1 FROM vagas WHERE id = ?", (vaga_id,)).fetchone()
            if not existe:
                raise ValueError(f"Vaga #{vaga_id} não encontrada.")
            connection.execute("DELETE FROM requisitos_vaga WHERE vaga_id = ?", (vaga_id,))
            self._inserir_requisitos(connection, vaga_id, requisitos)
            connection.execute(
                """UPDATE vagas
                   SET compatibilidade = ?, atualizado_em = datetime('now')
                   WHERE id = ?""",
                (compatibilidade, vaga_id),
            )

    def listar_requisitos(self, vaga_id: int) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM requisitos_vaga WHERE vaga_id = ? ORDER BY categoria, requisito",
                    (vaga_id,),
                ).fetchall()
            ]

    def atualizar_status(self, vaga_id: int, novo_status: str, observacao: str = "") -> None:
        if novo_status not in STATUS_VAGAS:
            raise ValueError(f"Status inválido: {novo_status}")
        with self.database.transaction() as connection:
            atual = connection.execute(
                "SELECT status FROM vagas WHERE id = ?", (vaga_id,)
            ).fetchone()
            if not atual:
                raise ValueError(f"Vaga #{vaga_id} não encontrada.")
            if atual["status"] == novo_status:
                return
            connection.execute(
                """UPDATE vagas SET status = ?, atualizado_em = datetime('now')
                   WHERE id = ?""",
                (novo_status, vaga_id),
            )
            connection.execute(
                """INSERT INTO historico_status
                   (vaga_id, status_anterior, status_novo, observacao)
                   VALUES (?, ?, ?, ?)""",
                (vaga_id, atual["status"], novo_status, str(observacao or "").strip()),
            )

    def historico(self, vaga_id: int) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM historico_status WHERE vaga_id = ? ORDER BY id DESC",
                    (vaga_id,),
                ).fetchall()
            ]
