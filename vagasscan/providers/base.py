from __future__ import annotations

from abc import ABC, abstractmethod

from vagasscan.models import Vaga


class ErroProvedor(RuntimeError):
    """Falha previsível ao consultar um provedor."""


class ProvedorNaoConfigurado(ErroProvedor):
    """O provedor não possui a configuração mínima."""


class ProvedorVagas(ABC):
    nome: str

    @abstractmethod
    def buscar(self, termo: str, localizacao: str = "") -> list[Vaga]:
        """Busca vagas e as converte para o modelo interno."""

