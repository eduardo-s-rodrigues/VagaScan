from __future__ import annotations

import re
from typing import Any

from vagasscan.models import Requisito, ResultadoCompatibilidade, Vaga
from vagasscan.utils.text import normalizar_texto


def _contem_algum(texto: str, opcoes: list[str]) -> bool:
    normalizado = normalizar_texto(texto)
    return any(normalizar_texto(opcao) in normalizado for opcao in opcoes)


def _area_compativel(titulo: str, descricao: str, areas: list[str]) -> bool:
    texto = normalizar_texto(f"{titulo} {descricao}")
    regras: dict[str, tuple[tuple[str, ...], ...]] = {
        "desenvolvimento python": (("python", "desenvolv"), ("python", "backend")),
        "backend": (("backend",), ("api", "desenvolv")),
        "analise de sistemas": (("analista de sistemas",), ("analise de sistemas",)),
        "analise de dados": (("dados",), ("power bi",), ("etl",)),
        "suporte tecnico": (("suporte",), ("service desk",)),
        "helpdesk": (("helpdesk",), ("service desk",), ("suporte",)),
    }
    for area in areas:
        area_normalizada = normalizar_texto(area)
        if area_normalizada in texto:
            return True
        if any(
            all(termo in texto for termo in grupo)
            for grupo in regras.get(area_normalizada, ())
        ):
            return True
    return False


def _requisitos_unicos(requisitos: list[Requisito]) -> list[Requisito]:
    """Consolida o mesmo conhecimento sem permitir inflação da pontuação."""
    unicos: dict[str, Requisito] = {}
    for item in requisitos:
        chave = normalizar_texto(item.requisito)
        atual = unicos.get(chave)
        if atual is None:
            unicos[chave] = Requisito(
                requisito=item.requisito,
                categoria=item.categoria,
                encontrado_no_perfil=item.encontrado_no_perfil,
                peso=item.peso,
            )
            continue
        atual.encontrado_no_perfil = (
            atual.encontrado_no_perfil or item.encontrado_no_perfil
        )
        atual.peso = max(atual.peso, item.peso)
    return list(unicos.values())


class CalculadoraCompatibilidade:
    """Calcula 0-100: técnica 55, área 15, nível 10, local 10, experiência 5, formação 5."""

    def calcular(
        self, vaga: Vaga | dict[str, Any], requisitos: list[Requisito], perfil: dict[str, Any]
    ) -> ResultadoCompatibilidade:
        obter = (lambda chave, padrao="": vaga.get(chave, padrao)) if isinstance(vaga, dict) else (
            lambda chave, padrao="": getattr(vaga, chave, padrao)
        )
        descricao = str(obter("descricao"))
        titulo = str(obter("titulo"))
        nivel = str(obter("nivel"))
        localizacao = str(obter("localizacao"))
        modalidade = str(obter("modalidade"))

        requisitos = _requisitos_unicos(requisitos)
        requisitos_tecnicos = [
            item
            for item in requisitos
            if item.categoria not in {"escolaridade", "experiência"}
        ]
        peso_total = sum(item.peso for item in requisitos_tecnicos)
        peso_compativel = sum(
            item.peso for item in requisitos_tecnicos if item.encontrado_no_perfil
        )
        tecnica = 55.0 * peso_compativel / peso_total if peso_total else 27.5

        area_ok = _area_compativel(titulo, descricao, perfil.get("areas_desejadas", []))
        texto_nivel = normalizar_texto(f"{titulo} {nivel}")
        nivel_ok = _contem_algum(texto_nivel, perfil.get("niveis_desejados", []))
        penalidade_nivel = 0.0
        nivel_acima = ""
        if any(termo in texto_nivel for termo in ("senior", "especialista", "tech lead", "lider")):
            penalidade_nivel = 12.0
            nivel_acima = "sênior/especialista"
        elif "pleno" in texto_nivel:
            penalidade_nivel = 6.0
            nivel_acima = "pleno"
        remoto = _contem_algum(f"{localizacao} {modalidade}", ["remoto", "home office"])
        localidades = perfil.get("localidades_desejadas", [])
        modalidades = perfil.get("modalidades_desejadas", [])
        remoto_desejado = _contem_algum(" ".join(localidades + modalidades), ["remoto"])
        modalidade_ok = not modalidades or _contem_algum(modalidade, modalidades)
        local_ok = (
            (remoto and remoto_desejado)
            or (_contem_algum(localizacao, localidades) and modalidade_ok)
        )

        descricao_normalizada = normalizar_texto(descricao)
        anos_encontrados = [
            int(valor) for valor in re.findall(r"(\d+)\s*anos?", descricao_normalizada)
        ]
        anos_exigidos = max(anos_encontrados, default=0)
        anos_perfil = int(perfil.get("experiencia_anos", 0))
        experiencia = 5.0 if anos_exigidos <= anos_perfil else max(0.0, 5.0 - anos_exigidos)

        exige_superior = _contem_algum(descricao, ["ensino superior", "graduação", "faculdade"])
        exige_superior_completo = _contem_algum(
            descricao, ["superior completo", "graduação completa", "faculdade completa"]
        )
        formacao = normalizar_texto(str(perfil.get("formacao", "")))
        perfil_superior = any(
            termo in formacao for termo in ("cursando", "completo", "graduacao", "superior")
        )
        perfil_completo = "completo" in formacao or "concluido" in formacao
        if exige_superior_completo and not perfil_completo:
            pontos_formacao = 2.5 if perfil_superior else 0.0
        else:
            pontos_formacao = 5.0 if not exige_superior or perfil_superior else 0.0

        pontuacao = tecnica + (15 if area_ok else 0) + (10 if nivel_ok else 0)
        pontuacao += (10 if local_ok else 0) + experiencia + pontos_formacao
        pontuacao -= penalidade_nivel
        pontuacao = round(max(0.0, min(100.0, pontuacao)), 1)

        compativeis = [
            item.requisito for item in requisitos_tecnicos if item.encontrado_no_perfil
        ]
        ausentes = [
            item.requisito for item in requisitos_tecnicos if not item.encontrado_no_perfil
        ]
        confirmar = [
            item.requisito
            for item in requisitos_tecnicos
            if item.peso >= 2 and not item.encontrado_no_perfil
        ]
        if anos_exigidos > anos_perfil:
            confirmar.append(f"Experiência de {anos_exigidos} ano(s)")
        if nivel_acima:
            confirmar.append(f"Nível {nivel_acima} acima do perfil iniciante")
        if exige_superior_completo and not perfil_completo:
            confirmar.append("Formação superior completa")
        if not requisitos_tecnicos:
            confirmar.append("Requisitos técnicos não identificados automaticamente")
        justificativa = (
            f"Técnica {tecnica:.1f}/55; área "
            f"{'compatível' if area_ok else 'não identificada'}; nível "
            f"{'compatível' if nivel_ok else 'fora/não informado'}"
            f"{f' (penalidade {penalidade_nivel:.0f})' if penalidade_nivel else ''}; local "
            f"{'compatível' if local_ok else 'fora/não informado'}; experiência "
            f"{experiencia:.1f}/5; formação {pontos_formacao:.1f}/5."
        )
        return ResultadoCompatibilidade(
            pontuacao=pontuacao,
            pontos_compativeis=compativeis,
            conhecimentos_ausentes=ausentes,
            confirmar=confirmar,
            justificativa=justificativa,
        )
