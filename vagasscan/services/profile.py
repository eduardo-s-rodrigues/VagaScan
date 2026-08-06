from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from vagasscan.analyzers.keywords import carregar_perfil

LIST_FIELDS = (
    "areas_desejadas",
    "conhecimentos",
    "experiencias",
    "localidades_desejadas",
    "modalidades_desejadas",
    "idiomas",
    "niveis_desejados",
)


class PerfilService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def carregar(self) -> dict[str, Any]:
        return carregar_perfil(self.path)

    @staticmethod
    def validar(perfil: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(perfil, dict):
            raise ValueError("O perfil deve ser um objeto.")
        validado = dict(perfil)
        for campo in LIST_FIELDS:
            valor = validado.get(campo, [])
            if not isinstance(valor, list) or len(valor) > 100:
                raise ValueError(f"O campo '{campo}' deve ser uma lista com até 100 itens.")
            itens: list[str] = []
            vistos: set[str] = set()
            for item in valor:
                texto = str(item or "").strip()
                if not texto or len(texto) > 200:
                    raise ValueError(f"Cada item de '{campo}' deve ter de 1 a 200 caracteres.")
                chave = texto.casefold()
                if chave not in vistos:
                    vistos.add(chave)
                    itens.append(texto)
            validado[campo] = itens
        try:
            anos = int(validado.get("experiencia_anos", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Anos de experiência deve ser um número inteiro.") from exc
        if not 0 <= anos <= 80:
            raise ValueError("Anos de experiência deve ficar entre 0 e 80.")
        validado["experiencia_anos"] = anos
        for campo, limite in (("formacao", 500), ("nivel_profissional", 100)):
            texto = str(validado.get(campo, "") or "").strip()
            if len(texto) > limite:
                raise ValueError(f"O campo '{campo}' excede {limite} caracteres.")
            validado[campo] = texto
        if not validado["conhecimentos"]:
            raise ValueError("Informe ao menos um conhecimento.")
        return validado

    def salvar(self, perfil: dict[str, Any]) -> Path | None:
        validado = self.validar(perfil)
        if self.path.is_symlink():
            raise ValueError("O arquivo de perfil não pode ser um link simbólico.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        backup: Path | None = None
        if self.path.exists():
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.path.with_name(f"{self.path.name}.bak-{timestamp}-{uuid.uuid4().hex[:8]}")
            shutil.copy2(self.path, backup)
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(validado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.path)
        return backup
