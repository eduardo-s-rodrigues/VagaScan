from vagasscan.providers.adzuna import ProvedorAdzuna
from vagasscan.providers.base import ErroProvedor, ProvedorNaoConfigurado, ProvedorVagas
from vagasscan.providers.demo import ProvedorDemonstracao
from vagasscan.providers.http_configurable import ProvedorHttpConfiguravel

__all__ = [
    "ErroProvedor",
    "ProvedorAdzuna",
    "ProvedorDemonstracao",
    "ProvedorHttpConfiguravel",
    "ProvedorNaoConfigurado",
    "ProvedorVagas",
]
