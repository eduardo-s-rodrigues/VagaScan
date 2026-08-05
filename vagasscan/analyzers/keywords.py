from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from vagasscan.models import Requisito
from vagasscan.utils.text import normalizar_texto


class AnalisadorPalavrasChave:
    def __init__(self, keywords_path: Path) -> None:
        self.keywords_path = keywords_path
        self.palavras_chave = self._carregar()

    def _carregar(self) -> dict[str, dict[str, list[str]]]:
        try:
            with self.keywords_path.open(encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Não foi possível carregar palavras-chave: {exc}") from exc
        if not isinstance(dados, dict):
            raise ValueError("O arquivo de palavras-chave deve conter um objeto JSON.")
        for categoria, termos in dados.items():
            if not isinstance(categoria, str) or not isinstance(termos, dict):
                raise ValueError("Cada categoria de palavras-chave deve ser um objeto.")
            for nome, sinonimos in termos.items():
                if (
                    not isinstance(nome, str)
                    or not isinstance(sinonimos, list)
                    or not sinonimos
                    or not all(isinstance(item, str) and item.strip() for item in sinonimos)
                ):
                    raise ValueError(f"Sinônimos inválidos para a palavra-chave {nome!r}.")
        return dados

    @staticmethod
    def _termo_presente(texto: str, termo: str) -> bool:
        termo_normalizado = normalizar_texto(termo)
        padrao = rf"(?<!\w){re.escape(termo_normalizado)}(?!\w)"
        return re.search(padrao, texto) is not None

    @staticmethod
    def _termo_negado(texto: str, termo: str) -> bool:
        """Reconhece negações simples para não transformar ausência em requisito."""
        termo_normalizado = normalizar_texto(termo)
        contexto = next(
            (
                trecho.strip()
                for trecho in re.split(r"[.;\n]", texto)
                if termo_normalizado in trecho
            ),
            "",
        )
        termo_escapado = re.escape(termo_normalizado)
        padroes = (
            rf"\b{termo_escapado}\s+nao\s+(?:e\s+)?(?:necessario|obrigatorio|exigido)",
            rf"\bnao\s+(?:e\s+)?(?:necessario|obrigatorio|exigido).*\b{termo_escapado}\b",
            rf"\bsem\s+(?:necessidade|exigencia|conhecimento)(?:\s+de|\s+em)?\s+{termo_escapado}\b",
            rf"\bsem\s+{termo_escapado}\b",
            rf"\bnao\s+(?:usamos|utilizamos|trabalhamos\s+com)\s+{termo_escapado}\b",
            rf"\bnao\s+(?:exige|requer)\s+{termo_escapado}\b",
            rf"\bdispensa(?:\s+conhecimento)?(?:\s+de|\s+em)?\s+{termo_escapado}\b",
        )
        return any(re.search(padrao, contexto) for padrao in padroes)

    @staticmethod
    def _peso_no_contexto(texto: str, termo: str) -> float:
        termo_normalizado = normalizar_texto(termo)
        contexto = next(
            (trecho for trecho in re.split(r"[.;\n]", texto) if termo_normalizado in trecho),
            "",
        )
        if any(
            palavra in contexto
            for palavra in (
                "obrigatorio",
                "obrigatoria",
                "obrigatorios",
                "obrigatorias",
                "necessario",
                "necessarios",
            )
        ):
            return 2.0
        if any(
            palavra in contexto
            for palavra in ("desejavel", "desejaveis", "diferencial", "sera um plus")
        ):
            return 0.75
        return 1.0

    def extrair(self, descricao: str, conhecimentos: list[str]) -> list[Requisito]:
        texto = normalizar_texto(descricao)
        perfil = normalizar_texto(" | ".join(conhecimentos))
        requisitos: list[Requisito] = []
        for categoria, termos_canonicos in self.palavras_chave.items():
            for nome, sinonimos in termos_canonicos.items():
                encontrado = next(
                    (
                        sinonimo
                        for sinonimo in sinonimos
                        if self._termo_presente(texto, sinonimo)
                        and not self._termo_negado(texto, sinonimo)
                    ),
                    None,
                )
                if encontrado:
                    no_perfil = any(
                        self._termo_presente(perfil, opcao) for opcao in [nome, *sinonimos]
                    )
                    requisitos.append(
                        Requisito(
                            requisito=nome,
                            categoria=categoria,
                            encontrado_no_perfil=no_perfil,
                            peso=self._peso_no_contexto(texto, encontrado),
                        )
                    )
        return requisitos


def carregar_perfil(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as arquivo:
            perfil = json.load(arquivo)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Não foi possível carregar o perfil: {exc}") from exc
    if not isinstance(perfil.get("conhecimentos"), list):
        raise ValueError("O perfil precisa ter uma lista 'conhecimentos'.")
    for campo in (
        "areas_desejadas",
        "localidades_desejadas",
        "niveis_desejados",
        "modalidades_desejadas",
    ):
        valor = perfil.get(campo, [])
        if not isinstance(valor, list) or not all(isinstance(item, str) for item in valor):
            raise ValueError(f"O campo '{campo}' do perfil deve ser uma lista de textos.")
    try:
        experiencia = int(perfil.get("experiencia_anos", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("O campo 'experiencia_anos' deve ser um número inteiro.") from exc
    if experiencia < 0:
        raise ValueError("O campo 'experiencia_anos' não pode ser negativo.")
    perfil["experiencia_anos"] = experiencia
    return perfil


def salvar_perfil(path: Path, perfil: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporario = path.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(perfil, arquivo, ensure_ascii=False, indent=2)
    temporario.replace(path)
