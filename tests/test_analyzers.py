from __future__ import annotations

from pathlib import Path

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave, carregar_perfil
from vagasscan.config import PROJECT_ROOT
from vagasscan.models import Requisito, Vaga


def test_extrai_tecnologias_e_detecta_perfil(profile_path: Path) -> None:
    analisador = AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json")
    perfil = carregar_perfil(profile_path)
    requisitos = analisador.extrair(
        "Python e SQL são obrigatórios. Docker será um diferencial.", perfil["conhecimentos"]
    )
    por_nome = {item.requisito: item for item in requisitos}
    assert por_nome["Python"].encontrado_no_perfil is True
    assert por_nome["SQL"].peso == 2.0
    assert por_nome["Docker"].encontrado_no_perfil is False
    assert por_nome["Docker"].peso == 0.75


def test_compatibilidade_fica_entre_zero_e_cem(profile_path: Path) -> None:
    perfil = carregar_perfil(profile_path)
    analisador = AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json")
    vaga = Vaga(
        titulo="Desenvolvedor Python Júnior",
        empresa="Exemplo",
        localizacao="Campinas",
        modalidade="híbrido",
        nivel="júnior",
        descricao="Python, SQL, Git e Docker. Ensino superior cursando.",
    )
    requisitos = analisador.extrair(vaga.descricao, perfil["conhecimentos"])
    resultado = CalculadoraCompatibilidade().calcular(vaga, requisitos, perfil)
    assert 0 <= resultado.pontuacao <= 100
    assert resultado.pontuacao >= 70
    assert "Docker" in resultado.conhecimentos_ausentes
    assert "Técnica" in resultado.justificativa


def test_sem_requisitos_pede_confirmacao_humana(profile_path: Path) -> None:
    perfil = carregar_perfil(profile_path)
    vaga = Vaga("Auxiliar", "Empresa", "Outro lugar", "Atividades gerais")
    resultado = CalculadoraCompatibilidade().calcular(vaga, [], perfil)
    assert "Requisitos técnicos não identificados automaticamente" in resultado.confirmar


def test_texto_vazio_e_descricao_curta_nao_quebram(profile_path: Path) -> None:
    analisador = AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json")
    perfil = carregar_perfil(profile_path)
    assert analisador.extrair("", perfil["conhecimentos"]) == []
    assert analisador.extrair("Olá", perfil["conhecimentos"]) == []


def test_acentos_caixa_e_sinonimos_sao_reconhecidos(profile_path: Path) -> None:
    analisador = AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json")
    perfil = carregar_perfil(profile_path)
    requisitos = analisador.extrair(
        "EXPERIÊNCIA com POSTGRES, API RESTful e comunicação.", perfil["conhecimentos"]
    )
    nomes = {item.requisito for item in requisitos}
    assert {"PostgreSQL", "APIs REST", "Comunicação", "Experiência profissional"} <= nomes


def test_tecnologia_negada_nao_vira_requisito(profile_path: Path) -> None:
    analisador = AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json")
    perfil = carregar_perfil(profile_path)
    requisitos = analisador.extrair(
        "Python não é necessário. Não utilizamos Java. Sem Docker. SQL é obrigatório.",
        perfil["conhecimentos"],
    )
    nomes = {item.requisito for item in requisitos}
    assert "Python" not in nomes
    assert "Java" not in nomes
    assert "Docker" not in nomes
    assert "SQL" in nomes


def test_requisito_repetido_nao_infla_pontuacao(profile_path: Path) -> None:
    perfil = carregar_perfil(profile_path)
    vaga = Vaga("Backend", "Empresa", "Campinas", "Python e Docker", nivel="júnior")
    requisitos = [
        Requisito("Python", "linguagens", True),
        Requisito("Docker", "ferramentas", False),
    ]
    repetidos = requisitos + [Requisito("Python", "linguagens", True)] * 5
    calculadora = CalculadoraCompatibilidade()
    assert calculadora.calcular(vaga, requisitos, perfil).pontuacao == calculadora.calcular(
        vaga, repetidos, perfil
    ).pontuacao


def test_vaga_senior_e_penalizada_sem_zerar(profile_path: Path) -> None:
    perfil = carregar_perfil(profile_path)
    requisitos = [Requisito("Python", "linguagens", True)]
    calculadora = CalculadoraCompatibilidade()
    junior = calculadora.calcular(
        Vaga("Desenvolvedor Python Júnior", "E", "Campinas", "Python", nivel="júnior"),
        requisitos,
        perfil,
    )
    senior = calculadora.calcular(
        Vaga("Desenvolvedor Python Sênior", "E", "Campinas", "Python", nivel="sênior"),
        requisitos,
        perfil,
    )
    assert 0 < senior.pontuacao < junior.pontuacao <= 100
    assert "penalidade 12" in senior.justificativa
    assert "Nível sênior/especialista acima do perfil iniciante" in senior.confirmar


def test_modalidades_e_nivel_de_estagio(profile_path: Path) -> None:
    perfil = carregar_perfil(profile_path)
    calculadora = CalculadoraCompatibilidade()
    requisito = [Requisito("SQL", "linguagens", True)]
    remoto = calculadora.calcular(
        Vaga("Estágio em Dados", "E", "Remoto no Brasil", "SQL", "remoto", "estágio"),
        requisito,
        perfil,
    )
    hibrido = calculadora.calcular(
        Vaga("Estágio em Dados", "E", "Campinas", "SQL", "híbrido", "estágio"),
        requisito,
        perfil,
    )
    assert remoto.pontuacao == 100
    assert hibrido.pontuacao == 100


def test_obrigatorio_pesa_mais_que_desejavel_quando_ausente(profile_path: Path) -> None:
    perfil = carregar_perfil(profile_path)
    vaga = Vaga("Backend Júnior", "E", "Campinas", "Python, Docker", nivel="júnior")
    calculadora = CalculadoraCompatibilidade()
    obrigatorio_ausente = [
        Requisito("Python", "linguagens", True, 1),
        Requisito("Docker", "ferramentas", False, 2),
    ]
    desejavel_ausente = [
        Requisito("Python", "linguagens", True, 1),
        Requisito("Docker", "ferramentas", False, 0.75),
    ]
    assert calculadora.calcular(vaga, obrigatorio_ausente, perfil).pontuacao < (
        calculadora.calcular(vaga, desejavel_ausente, perfil).pontuacao
    )


def test_plural_desejaveis_recebe_peso_reduzido(profile_path: Path) -> None:
    perfil = carregar_perfil(profile_path)
    analisador = AnalisadorPalavrasChave(PROJECT_ROOT / "data" / "keywords.json")
    requisitos = analisador.extrair("Docker e AWS são desejáveis.", perfil["conhecimentos"])
    assert {item.peso for item in requisitos if item.requisito in {"Docker", "AWS"}} == {0.75}
