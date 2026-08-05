from __future__ import annotations

from vagasscan.models import Vaga
from vagasscan.providers.base import ProvedorVagas
from vagasscan.utils.text import normalizar_texto

VAGAS_DEMO = [
    Vaga(
        titulo="Desenvolvedor Python Júnior",
        empresa="Tech Exemplo",
        localizacao="Campinas - SP",
        modalidade="híbrido",
        nivel="júnior",
        descricao=(
            "Desenvolvimento de APIs REST com Python e FastAPI. SQL, Git e JSON são "
            "obrigatórios. Docker será um diferencial. Ensino superior cursando."
        ),
        link="https://example.invalid/vagas/python-jr",
        fonte="demonstracao",
        identificador_externo="demo-python-001",
        data_publicacao="2026-08-01",
    ),
    Vaga(
        titulo="Analista de Suporte Júnior",
        empresa="Serviços Modelo",
        localizacao="Piracicaba - SP",
        modalidade="presencial",
        nivel="júnior",
        descricao=(
            "Atendimento ao usuário, Windows, redes e hardware. Conhecimentos de ITIL e "
            "Active Directory são desejáveis. Boa comunicação e organização."
        ),
        link="https://example.invalid/vagas/suporte-jr",
        fonte="demonstracao",
        identificador_externo="demo-suporte-002",
        data_publicacao="2026-08-02",
    ),
    Vaga(
        titulo="Estágio em Dados",
        empresa="Dados Fictícios SA",
        localizacao="Remoto no Brasil",
        modalidade="remoto",
        nivel="estágio",
        descricao="Análise de dados com SQL, Excel, Power BI e Python. Pandas é diferencial.",
        link="https://example.invalid/vagas/estagio-dados",
        fonte="demonstracao",
        identificador_externo="demo-dados-003",
        data_publicacao="2026-08-03",
    ),
]


class ProvedorDemonstracao(ProvedorVagas):
    nome = "demonstracao"

    def buscar(self, termo: str, localizacao: str = "") -> list[Vaga]:
        termo_normalizado = normalizar_texto(termo)
        local_normalizado = normalizar_texto(localizacao)
        return [
            vaga
            for vaga in VAGAS_DEMO
            if (
                not termo_normalizado
                or termo_normalizado in normalizar_texto(f"{vaga.titulo} {vaga.descricao}")
            )
            and (
                not local_normalizado
                or local_normalizado in normalizar_texto(vaga.localizacao)
            )
        ]
