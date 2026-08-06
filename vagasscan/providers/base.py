from __future__ import annotations

from abc import ABC, abstractmethod

from vagasscan.models import ConsultaVagas, ResultadoBusca, Vaga


class ErroProvedor(RuntimeError):
    """Falha previsível ao consultar um provedor."""

    def __init__(
        self,
        mensagem: str,
        *,
        codigo: str = "provedor",
        transitorio: bool = False,
        limite: bool = False,
    ) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.transitorio = transitorio
        self.limite = limite


class ProvedorNaoConfigurado(ErroProvedor):
    """O provedor não possui a configuração mínima."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem, codigo="configuracao")


class ProvedorVagas(ABC):
    nome: str

    @abstractmethod
    def buscar(self, termo: str, localizacao: str = "") -> list[Vaga]:
        """Busca vagas e as converte para o modelo interno."""

    def consultar(self, consulta: ConsultaVagas) -> ResultadoBusca:
        """Interface rica; provedores antigos continuam válidos por esta ponte."""
        vagas = self.buscar(consulta.termo, consulta.localizacao)
        total = len(vagas)
        inicio = (consulta.pagina - 1) * consulta.resultados_por_pagina
        fim = inicio + consulta.resultados_por_pagina
        return ResultadoBusca(
            vagas=vagas[inicio:fim],
            pagina=consulta.pagina,
            resultados_por_pagina=consulta.resultados_por_pagina,
            total_aproximado=total,
        )
