from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from vagasscan.database import Database
from vagasscan.models import ConsultaVagas, ResultadoBusca, Vaga


class CacheBuscaRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def chave(provedor: str, consulta: ConsultaVagas) -> tuple[str, str]:
        parametros = asdict(consulta)
        # Modalidade é uma heurística local: não deve fragmentar nem consumir o cache da fonte.
        parametros.pop("modalidade", None)
        parametros.pop("remoto", None)
        canonical = json.dumps(
            {"provedor": provedor, **parametros},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), canonical

    def salvar(
        self,
        provedor: str,
        consulta: ConsultaVagas,
        resultado: ResultadoBusca,
        minutos: int,
    ) -> None:
        chave, parametros = self.chave(provedor, consulta)
        now = datetime.now(UTC)
        payload = {
            "vagas": [asdict(vaga) for vaga in resultado.vagas],
            "pagina": resultado.pagina,
            "resultados_por_pagina": resultado.resultados_por_pagina,
            "total_aproximado": resultado.total_aproximado,
            "erros": resultado.erros,
        }
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO cache_buscas
                   (chave, provedor, parametros_json, resultado_json, criado_em, expira_em)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(chave) DO UPDATE SET
                     parametros_json=excluded.parametros_json,
                     resultado_json=excluded.resultado_json,
                     criado_em=excluded.criado_em,
                     expira_em=excluded.expira_em""",
                (
                    chave,
                    provedor,
                    parametros,
                    json.dumps(payload, ensure_ascii=False),
                    now.isoformat(),
                    (now + timedelta(minutes=max(1, minutos))).isoformat(),
                ),
            )

    def obter(
        self,
        provedor: str,
        consulta: ConsultaVagas,
        *,
        permitir_expirado: bool = False,
        maximo_expirado_horas: int = 24,
    ) -> ResultadoBusca | None:
        chave, _ = self.chave(provedor, consulta)
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM cache_buscas WHERE chave = ? AND provedor = ?",
                (chave, provedor),
            ).fetchone()
        if not row:
            return None
        now = datetime.now(UTC)
        try:
            created = datetime.fromisoformat(row["criado_em"])
            expires = datetime.fromisoformat(row["expira_em"])
            expired = expires <= now
            if expired and (
                not permitir_expirado
                or created < now - timedelta(hours=maximo_expirado_horas)
            ):
                return None
            data: dict[str, Any] = json.loads(row["resultado_json"])
            vagas = [Vaga(**item) for item in data.get("vagas", [])]
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return ResultadoBusca(
            vagas=vagas,
            pagina=int(data.get("pagina", consulta.pagina)),
            resultados_por_pagina=int(
                data.get("resultados_por_pagina", consulta.resultados_por_pagina)
            ),
            total_aproximado=int(data.get("total_aproximado", len(vagas))),
            veio_cache=True,
            cache_desatualizado=expired,
            cache_expira_em=expires.isoformat(),
            erros=[str(item) for item in data.get("erros", [])],
            cache_criado_em=created.isoformat(),
        )
