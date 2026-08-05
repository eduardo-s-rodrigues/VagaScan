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
    id: int | None = None


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
