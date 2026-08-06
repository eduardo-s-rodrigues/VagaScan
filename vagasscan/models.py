from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

STATUS_VAGAS = (
    "encontrada",
    "analisar",
    "interessante",
    "descartada",
    "candidatura_enviada",
    "teste_tecnico",
    "entrevista_rh",
    "entrevista_tecnica",
    "aguardando_resposta",
    "aprovada",
    "recusada",
    "encerrada",
)

ETAPAS_CANDIDATURA = (
    "candidatura_enviada",
    "teste_tecnico",
    "entrevista_rh",
    "entrevista_tecnica",
    "aguardando_resposta",
    "aprovada",
    "recusada",
    "encerrada",
)


@dataclass(slots=True)
class Vaga:
    titulo: str
    empresa: str
    localizacao: str
    descricao: str
    modalidade: str = "não informada"
    nivel: str = "não informado"
    link: str = ""
    fonte: str = "manual"
    identificador_externo: str = ""
    data_publicacao: str | None = None
    compatibilidade: float | None = None
    status: str = "encontrada"
    observacoes: str = ""
    salario_min: float | None = None
    salario_max: float | None = None
    categoria: str = ""
    tipo_contrato: str = ""
    jornada: str = ""
    id: int | None = None


@dataclass(slots=True)
class ConsultaVagas:
    termo: str = ""
    localizacao: str = ""
    pagina: int = 1
    resultados_por_pagina: int = 20
    remoto: bool = False
    tipo_contrato: str = ""
    jornada: str = ""
    ordenacao: str = "relevance"
    distancia_km: int | None = None
    pais: str = "br"


@dataclass(slots=True)
class ResultadoBusca:
    vagas: list[Vaga] = field(default_factory=list)
    pagina: int = 1
    resultados_por_pagina: int = 20
    total_aproximado: int = 0
    veio_cache: bool = False
    cache_desatualizado: bool = False
    cache_expira_em: str | None = None
    erros: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Requisito:
    requisito: str
    categoria: str
    encontrado_no_perfil: bool
    peso: float = 1.0
    vaga_id: int | None = None
    id: int | None = None


@dataclass(slots=True)
class ResultadoCompatibilidade:
    pontuacao: float
    pontos_compativeis: list[str] = field(default_factory=list)
    conhecimentos_ausentes: list[str] = field(default_factory=list)
    confirmar: list[str] = field(default_factory=list)
    justificativa: str = ""


@dataclass(slots=True)
class Candidatura:
    vaga_id: int
    data_candidatura: str = field(default_factory=lambda: date.today().isoformat())
    etapa: str = "candidatura_enviada"
    proxima_acao: str = ""
    data_proxima_acao: str | None = None
    observacoes: str = ""
    id: int | None = None
