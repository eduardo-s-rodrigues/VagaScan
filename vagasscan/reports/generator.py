from __future__ import annotations

import csv
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from vagasscan.database import Database


class GeradorRelatorios:
    def __init__(self, database: Database) -> None:
        self.database = database

    def resumo(self, dias_sem_atualizacao: int = 14) -> dict[str, Any]:
        limite = f"-{max(1, dias_sem_atualizacao)} days"
        with self.database.connection() as connection:
            por_fonte = self._contagem(connection, "fonte")
            por_status = self._contagem(connection, "status")
            por_cargo = self._contagem(connection, "titulo")
            por_local = self._contagem(connection, "localizacao")
            media = connection.execute(
                "SELECT ROUND(AVG(compatibilidade), 1) AS valor FROM vagas"
            ).fetchone()["valor"]
            tecnologias = [
                dict(row)
                for row in connection.execute(
                    """SELECT requisito AS nome, COUNT(*) AS quantidade
                       FROM requisitos_vaga
                       WHERE categoria NOT IN ('escolaridade', 'experiência',
                                              'habilidades comportamentais')
                       GROUP BY requisito ORDER BY quantidade DESC, requisito LIMIT 20"""
                ).fetchall()
            ]
            ausentes = [
                dict(row)
                for row in connection.execute(
                    """SELECT requisito AS nome, COUNT(*) AS quantidade
                       FROM requisitos_vaga
                       WHERE encontrado_no_perfil = 0
                         AND categoria NOT IN ('escolaridade', 'experiência')
                       GROUP BY requisito ORDER BY quantidade DESC, requisito LIMIT 20"""
                ).fetchall()
            ]
            etapas = [
                dict(row)
                for row in connection.execute(
                    """SELECT etapa AS nome, COUNT(*) AS quantidade
                       FROM candidaturas GROUP BY etapa ORDER BY quantidade DESC"""
                ).fetchall()
            ]
            proximas = [
                dict(row)
                for row in connection.execute(
                    """SELECT c.id, v.titulo, v.empresa, c.proxima_acao, c.data_proxima_acao
                       FROM candidaturas c JOIN vagas v ON v.id = c.vaga_id
                       WHERE c.proxima_acao <> ''
                       ORDER BY c.data_proxima_acao IS NULL, c.data_proxima_acao"""
                ).fetchall()
            ]
            paradas = [
                dict(row)
                for row in connection.execute(
                    """SELECT c.id, v.titulo, v.empresa, c.etapa, c.atualizado_em
                       FROM candidaturas c JOIN vagas v ON v.id = c.vaga_id
                       WHERE datetime(c.atualizado_em) < datetime('now', ?)
                       ORDER BY c.atualizado_em""",
                    (limite,),
                ).fetchall()
            ]
        return {
            "gerado_em": date.today().isoformat(),
            "vagas_por_fonte": por_fonte,
            "vagas_por_status": por_status,
            "vagas_por_cargo": por_cargo,
            "vagas_por_localidade": por_local,
            "media_compatibilidade": media or 0,
            "tecnologias_mais_pedidas": tecnologias,
            "conhecimentos_ausentes": ausentes,
            "candidaturas_por_etapa": etapas,
            "proximas_acoes": proximas,
            "candidaturas_sem_atualizacao": paradas,
        }

    @staticmethod
    def _contagem(connection: Any, coluna: str) -> list[dict[str, Any]]:
        permitidas = {"fonte", "status", "titulo", "localizacao"}
        if coluna not in permitidas:
            raise ValueError("Coluna de relatório inválida.")
        return [
            dict(row)
            for row in connection.execute(
                f"SELECT {coluna} AS nome, COUNT(*) AS quantidade "  # noqa: S608
                f"FROM vagas GROUP BY {coluna} ORDER BY quantidade DESC, nome"
            ).fetchall()
        ]

    @staticmethod
    def _preparar_destino(destino: Path, *, sobrescrever: bool) -> None:
        if destino.is_symlink():
            raise ValueError("O arquivo de relatório não pode ser um link simbólico.")
        if destino.exists() and not sobrescrever:
            raise FileExistsError(f"O relatório já existe: {destino}")
        destino.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _valor_csv_seguro(valor: Any) -> Any:
        """Evita que textos externos sejam interpretados como fórmulas por planilhas."""
        if isinstance(valor, str) and valor.lstrip().startswith(("=", "+", "-", "@")):
            return f"'{valor}"
        return valor

    def exportar_markdown(self, destino: Path, *, sobrescrever: bool = False) -> Path:
        self._preparar_destino(destino, sobrescrever=sobrescrever)
        resumo = self.resumo()
        linhas = ["# Relatório VagasScan", "", f"Gerado em: {resumo['gerado_em']}", ""]
        for titulo, chave in (
            ("Vagas por fonte", "vagas_por_fonte"),
            ("Vagas por status", "vagas_por_status"),
            ("Vagas por cargo", "vagas_por_cargo"),
            ("Vagas por localidade", "vagas_por_localidade"),
            ("Tecnologias mais pedidas", "tecnologias_mais_pedidas"),
            ("Conhecimentos ausentes", "conhecimentos_ausentes"),
            ("Candidaturas por etapa", "candidaturas_por_etapa"),
        ):
            linhas.extend([f"## {titulo}", "", "| Item | Quantidade |", "|---|---:|"])
            linhas.extend(f"| {item['nome']} | {item['quantidade']} |" for item in resumo[chave])
            linhas.append("")
        linhas.extend(
            ["## Média de compatibilidade", "", f"{resumo['media_compatibilidade']}%", ""]
        )
        linhas.extend(["## Próximas ações", ""])
        linhas.extend(
            f"- {item['data_proxima_acao'] or 'sem data'} — {item['titulo']} / "
            f"{item['empresa']}: {item['proxima_acao']}"
            for item in resumo["proximas_acoes"]
        )
        linhas.extend(["", "## Candidaturas sem atualização há mais de 14 dias", ""])
        linhas.extend(
            f"- {item['titulo']} / {item['empresa']} — {item['etapa']} "
            f"(última atualização: {item['atualizado_em']})"
            for item in resumo["candidaturas_sem_atualizacao"]
        )
        temporario = destino.with_name(f"{destino.name}.{uuid.uuid4().hex}.tmp")
        temporario.write_text("\n".join(linhas), encoding="utf-8")
        temporario.replace(destino)
        return destino

    def formatar_terminal(self) -> str:
        resumo = self.resumo()
        linhas = [
            "\n=== Relatório VagasScan ===",
            f"Média de compatibilidade: {resumo['media_compatibilidade']}%",
        ]
        for titulo, chave in (
            ("Vagas por fonte", "vagas_por_fonte"),
            ("Vagas por status", "vagas_por_status"),
            ("Vagas por cargo", "vagas_por_cargo"),
            ("Vagas por localidade", "vagas_por_localidade"),
            ("Tecnologias mais pedidas", "tecnologias_mais_pedidas"),
            ("Conhecimentos ausentes", "conhecimentos_ausentes"),
            ("Candidaturas por etapa", "candidaturas_por_etapa"),
        ):
            linhas.append(f"\n{titulo}:")
            itens = resumo[chave]
            linhas.extend(f"- {item['nome']}: {item['quantidade']}" for item in itens)
            if not itens:
                linhas.append("- nenhum registro")
        linhas.append("\nPróximas ações:")
        linhas.extend(
            f"- {item['data_proxima_acao'] or 'sem data'} | {item['titulo']} | "
            f"{item['proxima_acao']}"
            for item in resumo["proximas_acoes"]
        )
        if not resumo["proximas_acoes"]:
            linhas.append("- nenhuma ação cadastrada")
        linhas.append("\nCandidaturas sem atualização há mais de 14 dias:")
        linhas.extend(
            f"- {item['titulo']} | {item['etapa']} | {item['atualizado_em']}"
            for item in resumo["candidaturas_sem_atualizacao"]
        )
        if not resumo["candidaturas_sem_atualizacao"]:
            linhas.append("- nenhuma candidatura atrasada")
        return "\n".join(linhas)

    def exportar_csv(self, destino: Path, *, sobrescrever: bool = False) -> Path:
        self._preparar_destino(destino, sobrescrever=sobrescrever)
        temporario = destino.with_name(f"{destino.name}.{uuid.uuid4().hex}.tmp")
        with self.database.connection() as connection, temporario.open(
            "w", encoding="utf-8-sig", newline=""
        ) as arquivo:
            linhas = connection.execute(
                """SELECT id, titulo, empresa, localizacao, modalidade, nivel, fonte,
                          compatibilidade, status, link, data_publicacao, data_encontrada
                   FROM vagas ORDER BY id"""
            )
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow([coluna[0] for coluna in linhas.description])
            escritor.writerows(
                [self._valor_csv_seguro(valor) for valor in linha]
                for linha in linhas.fetchall()
            )
        temporario.replace(destino)
        return destino
