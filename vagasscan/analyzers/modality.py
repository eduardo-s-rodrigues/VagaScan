from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from vagasscan.utils.text import normalizar_texto


@dataclass(frozen=True, slots=True)
class ModalidadeDetectada:
    valor: str
    origem: str
    confianca: str
    inferida: bool


NAO_INFORMADA = ModalidadeDetectada("não informada", "não informada", "baixa", False)


def _valor_estruturado(item: dict[str, Any]) -> str:
    for campo in ("workplace_type", "work_location_type", "workplace", "remote"):
        valor = item.get(campo)
        if isinstance(valor, dict):
            valor = valor.get("label") or valor.get("display_name") or valor.get("name")
        if valor is True:
            return "remoto"
        if valor is False and campo == "remote":
            return "presencial"
        texto = normalizar_texto(str(valor or ""))
        if texto:
            return texto
    return ""


def classificar_modalidade(
    titulo: str,
    localizacao: str,
    descricao: str,
    *,
    item_fonte: dict[str, Any] | None = None,
) -> ModalidadeDetectada:
    """Classifica modalidade, preservando a diferença entre dado e inferência.

    Campos estruturados conhecidos têm prioridade. Na heurística textual, negações simples são
    removidas antes de procurar remoto e termos de possibilidade recebem um rótulo próprio.
    """

    estruturado = _valor_estruturado(item_fonte or {})
    if estruturado:
        if any(termo in estruturado for termo in ("hybrid", "hibrid")):
            return ModalidadeDetectada("híbrido", "fonte", "alta", False)
        if any(termo in estruturado for termo in ("remote", "remot", "home office")):
            return ModalidadeDetectada("remoto", "fonte", "alta", False)
        if any(
            termo in estruturado
            for termo in ("on-site", "onsite", "presencial", "office", "local")
        ):
            return ModalidadeDetectada("presencial", "fonte", "alta", False)

    titulo_local = normalizar_texto(f"{titulo}. {localizacao}")
    texto = normalizar_texto(f"{titulo}. {localizacao}. {descricao}")
    if not texto:
        return NAO_INFORMADA

    padroes_negacao = (
        r"\bnao\s+(?:sera\s+|e\s+|totalmente\s+)?(?:remot[oa]|remote|home office)\b",
        r"\bsem\s+(?:opcao|possibilidade)\s+(?:de\s+)?(?:trabalho\s+)?remot[oa]\b",
        r"\b(?:remot[oa]|home office)\s+nao\s+(?:e\s+)?(?:permitid[oa]|disponivel)\b",
    )
    remoto_negado = any(re.search(padrao, texto) for padrao in padroes_negacao)
    texto_sem_negacoes = texto
    for padrao in padroes_negacao:
        texto_sem_negacoes = re.sub(padrao, " ", texto_sem_negacoes)

    if re.search(r"\b(?:modelo|regime|trabalho)?\s*hibrid[oa]\b|\bhybrid\b", texto):
        return ModalidadeDetectada("híbrido", "VagaScan", "média", True)

    possibilidade = re.search(
        r"\b(?:possibilidade|opcao|eventualmente|ocasionalmente|alguns dias)"
        r".{0,35}\b(?:remot[oa]|home office)\b",
        texto_sem_negacoes,
    )
    if possibilidade:
        return ModalidadeDetectada("possivelmente remoto", "VagaScan", "baixa", True)

    contexto_tecnico = re.search(
        r"\b(?:acesso|suporte|atendimento|desktop|servidor|conexao)\s+remot[oa]\b",
        texto_sem_negacoes,
    )
    remoto_explicito = re.search(
        r"\b(?:trabalho|modelo|regime|atuacao|vaga|posicao|100%)\s+"
        r"(?:e\s+)?(?:remot[oa]|remote|home office)\b|\bremote work\b",
        texto_sem_negacoes,
    )
    remoto_no_titulo_ou_local = re.search(
        r"\b(?:remot[oa]|remote|home office)\b", titulo_local
    )
    if (remoto_explicito or remoto_no_titulo_ou_local) and not contexto_tecnico:
        return ModalidadeDetectada("remoto", "VagaScan", "média", True)

    if re.search(r"\b(?:trabalho|modelo|regime)?\s*presencial\b|\b(?:on-site|onsite)\b", texto):
        return ModalidadeDetectada("presencial", "VagaScan", "média", True)

    if remoto_negado:
        return ModalidadeDetectada("presencial", "VagaScan", "média", True)
    if (
        re.search(r"\b(?:remot[oa]|remote|home office)\b", texto_sem_negacoes)
        and not contexto_tecnico
    ):
        return ModalidadeDetectada("possivelmente remoto", "VagaScan", "baixa", True)
    return NAO_INFORMADA


def modalidade_corresponde(valor: str, filtro: str) -> bool:
    modalidade = normalizar_texto(valor)
    esperado = normalizar_texto(filtro)
    if esperado == "hibrido":
        return modalidade == "hibrido"
    if esperado == "remoto":
        return modalidade in {"remoto", "possivelmente remoto"}
    if esperado == "presencial":
        return modalidade == "presencial"
    return True
