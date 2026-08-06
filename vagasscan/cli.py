from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from vagasscan.analyzers.compatibility import CalculadoraCompatibilidade
from vagasscan.analyzers.keywords import AnalisadorPalavrasChave, carregar_perfil, salvar_perfil
from vagasscan.config import PROJECT_ROOT, Settings
from vagasscan.database import Database
from vagasscan.file_organizer import OrganizadorArquivos
from vagasscan.models import (
    ETAPAS_CANDIDATURA,
    STATUS_VAGAS,
    Candidatura,
    ConsultaVagas,
    ResultadoCompatibilidade,
    Vaga,
)
from vagasscan.providers import (
    ErroProvedor,
    ProvedorAdzuna,
    ProvedorDemonstracao,
    ProvedorHttpConfiguravel,
)
from vagasscan.reports import GeradorRelatorios
from vagasscan.repositories.candidaturas import CandidaturaRepository
from vagasscan.repositories.vagas import VagaDuplicadaError, VagaRepository
from vagasscan.services.vagas import VagaService


def perguntar(mensagem: str, *, obrigatorio: bool = False, padrao: str = "") -> str | None:
    while True:
        sufixo = f" [{padrao}]" if padrao else ""
        valor = input(f"{mensagem}{sufixo} (0 cancela): ").strip()
        if valor == "0":
            return None
        if valor:
            return valor
        if padrao:
            return padrao
        if not obrigatorio:
            return ""
        print("Este campo é obrigatório.")


def perguntar_inteiro(mensagem: str) -> int | None:
    while True:
        valor = perguntar(mensagem, obrigatorio=True)
        if valor is None:
            return None
        try:
            numero = int(valor)
            if numero > 0:
                return numero
        except ValueError:
            pass
        print("Digite um número inteiro maior que zero.")


def perguntar_data(mensagem: str, *, padrao: str = "", opcional: bool = False) -> str | None:
    while True:
        valor = perguntar(mensagem, obrigatorio=not opcional, padrao=padrao)
        if valor is None or (opcional and not valor):
            return valor
        try:
            date.fromisoformat(valor)
            return valor
        except ValueError:
            print("Data inválida. Use o formato AAAA-MM-DD.")


def perguntar_texto_longo(mensagem: str) -> str | None:
    print(f"{mensagem}. Finalize com uma linha contendo apenas FIM; 0 cancela.")
    linhas: list[str] = []
    while True:
        linha = input("> ")
        if linha.strip() == "0" and not linhas:
            return None
        if linha.strip().upper() == "FIM":
            texto = "\n".join(linhas).strip()
            if texto:
                return texto
            print("A descrição não pode ficar vazia.")
            continue
        linhas.append(linha)


def confirmar(mensagem: str) -> bool:
    return input(f"{mensagem} [s/N]: ").strip().lower() in {"s", "sim"}


def mostrar_resultado(resultado: ResultadoCompatibilidade) -> None:
    print(f"\nCompatibilidade aproximada: {resultado.pontuacao:.1f}%")
    print("A pontuação é uma estimativa e não garante aprovação.")
    print("Pontos compatíveis: " + (", ".join(resultado.pontos_compativeis) or "nenhum detectado"))
    print(
        "Conhecimentos ausentes: "
        + (", ".join(resultado.conhecimentos_ausentes) or "nenhum detectado")
    )
    print("Confirmar manualmente: " + (", ".join(resultado.confirmar) or "nenhum"))
    print(f"Justificativa: {resultado.justificativa}")


class CLI:
    def __init__(
        self,
        settings: Settings,
        vaga_service: VagaService,
        vagas: VagaRepository,
        candidaturas: CandidaturaRepository,
        relatorios: GeradorRelatorios,
    ) -> None:
        self.settings = settings
        self.vaga_service = vaga_service
        self.vagas = vagas
        self.candidaturas = candidaturas
        self.relatorios = relatorios
        self.acoes: dict[str, Callable[[], None]] = {
            "1": self.buscar_vagas,
            "2": self.cadastrar_manual,
            "3": self.importar_descricao,
            "4": self.listar_vagas,
            "5": self.ver_detalhes,
            "6": self.atualizar_status,
            "7": self.registrar_candidatura,
            "8": self.atualizar_candidatura,
            "9": self.mais_compativeis,
            "10": self.tecnologias,
            "11": self.proximas_acoes,
            "12": self.organizar_documentos,
            "13": self.editar_perfil,
            "14": self.exportar_relatorio,
        }

    def executar(self) -> None:
        while True:
            self._menu()
            try:
                opcao = input("Escolha uma opção: ").strip()
                if opcao == "15":
                    print("Até logo!")
                    return
                acao = self.acoes.get(opcao)
                if not acao:
                    print("Opção inválida.")
                    continue
                acao()
            except (KeyboardInterrupt, EOFError):
                print("\nOperação cancelada. Até logo!")
                return
            except (ValueError, OSError, RuntimeError, sqlite3.DatabaseError) as exc:
                print(f"Não foi possível concluir: {exc}")

    @staticmethod
    def _menu() -> None:
        print(
            """
=== VagasScan ===
1. Buscar vagas
2. Cadastrar vaga manualmente
3. Importar e analisar descrição
4. Listar vagas
5. Ver detalhes de uma vaga
6. Atualizar status
7. Registrar candidatura
8. Atualizar etapa de candidatura
9. Ver vagas mais compatíveis
10. Ver tecnologias mais pedidas
11. Ver próximas ações
12. Organizar documentos
13. Editar perfil
14. Exportar relatório
15. Sair
"""
        )

    def buscar_vagas(self) -> None:
        print("1. Adzuna — vagas reais\n2. Demonstração local\n3. HTTP configurável")
        escolha = perguntar("Fonte", obrigatorio=True)
        if escolha is None:
            return
        provedor = ProvedorAdzuna(self.settings) if escolha == "1" else None
        if escolha == "1" and (
            not self.settings.adzuna_app_id or not self.settings.adzuna_app_key
        ):
            print(
                "A integração com a Adzuna ainda não está configurada. Preencha "
                "ADZUNA_APP_ID e ADZUNA_APP_KEY no arquivo .env."
            )
            print("O cadastro manual, a importação e a demonstração continuam disponíveis.")
            return
        if escolha == "2":
            provedor = ProvedorDemonstracao()
        if escolha == "3":
            provedor = ProvedorHttpConfiguravel(self.settings)
        if not provedor:
            print("Fonte inválida.")
            return
        termo = perguntar("Termo de busca")
        if termo is None:
            return
        local = perguntar("Localização")
        if local is None:
            return
        consulta = ConsultaVagas(
            termo=termo or "",
            localizacao=local or "",
            resultados_por_pagina=self.settings.adzuna_results_per_page,
            pais=self.settings.adzuna_country,
        )
        if escolha == "1":
            pagina = perguntar("Página", padrao="1")
            quantidade = perguntar(
                "Resultados por página", padrao=str(self.settings.adzuna_results_per_page)
            )
            remoto = perguntar("Somente remoto? (s/N)")
            contrato = perguntar("Contrato (permanent/contract ou vazio)")
            jornada = perguntar("Jornada (full_time/part_time ou vazio)")
            ordenacao = perguntar(
                "Ordenação (relevance/date/salary/hybrid/default)", padrao="relevance"
            )
            distancia = perguntar("Distância em km (1-100 ou vazio)")
            if None in {pagina, quantidade, remoto, contrato, jornada, ordenacao, distancia}:
                return
            try:
                consulta.pagina = int(pagina or "1")
                consulta.resultados_por_pagina = int(
                    quantidade or self.settings.adzuna_results_per_page
                )
                consulta.distancia_km = int(distancia) if distancia else None
            except ValueError:
                print("Página, quantidade ou distância inválida.")
                return
            consulta.remoto = (remoto or "").strip().lower() in {"s", "sim"}
            consulta.tipo_contrato = contrato or ""
            consulta.jornada = jornada or ""
            consulta.ordenacao = ordenacao or "relevance"
        service = self.vaga_service
        try:
            if escolha == "2":
                demo_database = Database(self.settings.demo_database_path)
                demo_database.initialize()
                service = VagaService(
                    VagaRepository(demo_database),
                    AnalisadorPalavrasChave(self.settings.keywords_path),
                    CalculadoraCompatibilidade(),
                    self.settings.profile_path,
                )
                print(f"Dados fictícios serão mantidos separados em {demo_database.path}")
            resultado = service.buscar_e_salvar(provedor, consulta)
        except (ErroProvedor, ValueError, OSError) as exc:
            print(f"A fonte não pôde ser consultada: {exc}")
            print("O cadastro manual e a importação de descrições continuam disponíveis.")
            return
        print(
            f"Página: {resultado['pagina']} | total aproximado: "
            f"{resultado['total_aproximado']} | recebidas: {resultado['recebidas']} | cadastradas: "
            f"{len(resultado['cadastradas'])} | duplicadas: {len(resultado['duplicadas'])} | "
            f"erros: {len(resultado['erros'])}"
        )
        if resultado["veio_cache"]:
            sufixo = " desatualizado" if resultado["cache_desatualizado"] else " válido"
            print(f"Resultado fornecido pelo cache{sufixo}.")
        for mensagem in [*resultado["duplicadas"], *resultado["erros"]]:
            print(f"- {mensagem}")

    def _dados_vaga(self, *, apenas_descricao: bool = False) -> Vaga | None:
        descricao = perguntar_texto_longo("Cole a descrição completa da vaga")
        if descricao is None:
            return None
        if apenas_descricao:
            titulo = perguntar("Título", padrao="Vaga importada")
            empresa = perguntar("Empresa", padrao="Não informada")
            local = perguntar("Localização", padrao="Não informada")
        else:
            titulo = perguntar("Título", obrigatorio=True)
            empresa = perguntar("Empresa", obrigatorio=True)
            local = perguntar("Localização", obrigatorio=True)
        if None in {titulo, empresa, local}:
            return None
        modalidade = perguntar("Modalidade", padrao="não informada")
        nivel = perguntar("Nível", padrao="não informado")
        link = perguntar("Link")
        if None in {modalidade, nivel, link}:
            return None
        return Vaga(
            titulo=titulo or "Vaga importada",
            empresa=empresa or "Não informada",
            localizacao=local or "Não informada",
            modalidade=modalidade or "não informada",
            nivel=nivel or "não informado",
            descricao=descricao,
            link=link or "",
            fonte="manual",
        )

    def _salvar_vaga(self, vaga: Vaga) -> None:
        try:
            vaga_id, resultado = self.vaga_service.cadastrar_e_analisar(vaga)
        except VagaDuplicadaError as exc:
            if "título, empresa e localização" in str(exc) and confirmar(
                f"{exc} Deseja cadastrar mesmo assim?"
            ):
                vaga_id, resultado = self.vaga_service.cadastrar_e_analisar(
                    vaga, aceitar_possivel_duplicata=True
                )
            else:
                raise
        print(f"Vaga #{vaga_id} cadastrada.")
        mostrar_resultado(resultado)

    def cadastrar_manual(self) -> None:
        print("Digite 0 em qualquer campo para cancelar.")
        titulo = perguntar("Título", obrigatorio=True)
        if titulo is None:
            return
        empresa = perguntar("Empresa", padrao="Não informada")
        local = perguntar("Localização", obrigatorio=True)
        modalidade = perguntar("Modalidade", padrao="não informada")
        nivel = perguntar("Nível", padrao="não informado")
        descricao = perguntar_texto_longo("Digite ou cole a descrição")
        link = perguntar("Link")
        if None in {empresa, local, modalidade, nivel, descricao, link}:
            return
        self._salvar_vaga(
            Vaga(
                titulo=titulo,
                empresa=empresa,
                localizacao=local,
                modalidade=modalidade or "não informada",
                nivel=nivel or "não informado",
                descricao=descricao,
                link=link or "",
            )
        )

    def importar_descricao(self) -> None:
        vaga = self._dados_vaga(apenas_descricao=True)
        if vaga:
            self._salvar_vaga(vaga)

    def listar_vagas(self) -> None:
        print("Deixe vazio para não filtrar; 0 cancela.")
        status = perguntar("Status")
        area = perguntar("Área ou palavra no título")
        local = perguntar("Local")
        fonte = perguntar("Fonte")
        minima_texto = perguntar("Compatibilidade mínima")
        if None in {status, area, local, fonte, minima_texto}:
            return
        try:
            minima = float(minima_texto.replace(",", ".")) if minima_texto else None
        except ValueError:
            print("Compatibilidade inválida; filtro ignorado.")
            minima = None
        if minima is not None and not 0 <= minima <= 100:
            print("A compatibilidade mínima deve ficar entre 0 e 100; filtro ignorado.")
            minima = None
        registros = self.vagas.listar(
            status=status or "",
            area=area or "",
            local=local or "",
            fonte=fonte or "",
            compatibilidade_minima=minima,
        )
        self._mostrar_lista(registros)

    @staticmethod
    def _mostrar_lista(registros: list[dict[str, Any]]) -> None:
        if not registros:
            print("Nenhuma vaga encontrada.")
            return
        print("\nID | Compat. | Status | Título | Empresa | Local")
        print("-" * 100)
        for vaga in registros:
            nota = "-" if vaga["compatibilidade"] is None else f"{vaga['compatibilidade']:.1f}%"
            print(
                f"{vaga['id']} | {nota} | {vaga['status']} | {vaga['titulo']} | "
                f"{vaga['empresa']} | {vaga['localizacao']}"
            )

    def ver_detalhes(self) -> None:
        vaga_id = perguntar_inteiro("ID da vaga")
        if vaga_id is None:
            return
        vaga = self.vagas.obter(vaga_id)
        if not vaga:
            print("Vaga não encontrada.")
            return
        print("\n" + "=" * 60)
        for campo in (
            "id", "titulo", "empresa", "localizacao", "modalidade", "nivel", "fonte",
            "salario_min", "salario_max", "categoria", "tipo_contrato", "jornada",
            "status", "compatibilidade", "link", "data_publicacao", "data_encontrada",
            "observacoes", "descricao",
        ):
            print(f"{campo.replace('_', ' ').title()}: {vaga[campo]}")
        requisitos = self.vagas.listar_requisitos(vaga_id)
        print("Requisitos:")
        for item in requisitos:
            perfil = "sim" if item["encontrado_no_perfil"] else "não"
            print(
                f"- {item['requisito']} ({item['categoria']}, perfil: {perfil}, "
                f"peso: {item['peso']})"
            )
        historico = self.vagas.historico(vaga_id)
        if historico:
            print("Histórico de status:")
            for item in historico:
                print(
                    f"- {item['data_alteracao']}: {item['status_anterior']} -> "
                    f"{item['status_novo']} ({item['observacao']})"
                )

    def atualizar_status(self) -> None:
        vaga_id = perguntar_inteiro("ID da vaga")
        if vaga_id is None:
            return
        for indice, status in enumerate(STATUS_VAGAS, 1):
            print(f"{indice}. {status}")
        escolha = perguntar("Número do novo status", obrigatorio=True)
        if escolha is None:
            return
        try:
            indice = int(escolha)
            if not 1 <= indice <= len(STATUS_VAGAS):
                raise ValueError
            novo_status = STATUS_VAGAS[indice - 1]
        except ValueError:
            print("Status inválido.")
            return
        observacao = perguntar("Observação da alteração")
        if observacao is None:
            return
        atual = self.vagas.obter(vaga_id)
        if atual and atual["status"] in {"aprovada", "recusada", "encerrada"}:
            print("Aviso: a vaga está em estado final. A correção manual continua permitida.")
        self.vagas.atualizar_status(vaga_id, novo_status, observacao or "")
        print("Status atualizado.")

    def registrar_candidatura(self) -> None:
        vaga_id = perguntar_inteiro("ID da vaga")
        if vaga_id is None:
            return
        data_candidatura = perguntar_data(
            "Data (AAAA-MM-DD)", padrao=date.today().isoformat()
        )
        proxima = perguntar("Próxima ação")
        data_proxima = perguntar_data("Data da próxima ação (AAAA-MM-DD)", opcional=True)
        observacoes = perguntar("Observações")
        if None in {data_candidatura, proxima, data_proxima, observacoes}:
            return
        candidatura_id = self.candidaturas.registrar(
            Candidatura(
                vaga_id=vaga_id,
                data_candidatura=data_candidatura or date.today().isoformat(),
                proxima_acao=proxima or "",
                data_proxima_acao=data_proxima or None,
                observacoes=observacoes or "",
            )
        )
        print(f"Candidatura #{candidatura_id} registrada.")

    def atualizar_candidatura(self) -> None:
        candidatura_id = perguntar_inteiro("ID da candidatura")
        if candidatura_id is None:
            return
        for indice, nome_etapa in enumerate(ETAPAS_CANDIDATURA, 1):
            print(f"{indice}. {nome_etapa}")
        escolha = perguntar("Número da nova etapa", obrigatorio=True)
        if escolha is None:
            return
        try:
            indice = int(escolha)
            if not 1 <= indice <= len(ETAPAS_CANDIDATURA):
                raise ValueError
            etapa = ETAPAS_CANDIDATURA[indice - 1]
        except ValueError:
            print("Etapa inválida.")
            return
        proxima = perguntar("Próxima ação")
        data_proxima = perguntar_data("Data da próxima ação (AAAA-MM-DD)", opcional=True)
        observacoes = perguntar("Observações")
        if None in {etapa, proxima, data_proxima, observacoes}:
            return
        self.candidaturas.atualizar_etapa(
            candidatura_id, etapa, proxima or "", data_proxima or None, observacoes or ""
        )
        print("Candidatura atualizada.")

    def mais_compativeis(self) -> None:
        self._mostrar_lista(self.vagas.listar(compatibilidade_minima=0, limite=20))

    def tecnologias(self) -> None:
        itens = self.relatorios.resumo()["tecnologias_mais_pedidas"]
        print("\nTecnologias mais pedidas:")
        if not itens:
            print("Nenhuma tecnologia encontrada. Cadastre e analise uma vaga primeiro.")
        for item in itens:
            print(f"- {item['nome']}: {item['quantidade']}")

    def proximas_acoes(self) -> None:
        resumo = self.relatorios.resumo()
        print("\nPróximas ações:")
        if not resumo["proximas_acoes"]:
            print("Nenhuma próxima ação cadastrada.")
        for item in resumo["proximas_acoes"]:
            print(
                f"- Candidatura #{item['id']} | {item['titulo']} - {item['empresa']} | "
                f"{item['data_proxima_acao'] or 'sem data'} | {item['proxima_acao']}"
            )
        print("\nSem atualização há mais de 14 dias:")
        for item in resumo["candidaturas_sem_atualizacao"]:
            print(f"- #{item['id']} {item['titulo']} ({item['etapa']})")

    def organizar_documentos(self) -> None:
        print("1. Analisar/organizar pasta\n2. Desfazer última movimentação")
        escolha = perguntar("Opção", obrigatorio=True)
        if escolha is None:
            return
        organizador = OrganizadorArquivos(
            PROJECT_ROOT / "data" / "movimentacoes.json",
            caminhos_protegidos=(PROJECT_ROOT,),
        )
        if escolha == "2":
            reversoes = organizador.desfazer_ultima(simular=True)
            if not reversoes:
                print("Não há movimentação para desfazer.")
                return
            for item in reversoes:
                print(f"DESFAZER: {item.origem} -> {item.destino}")
            if confirmar("Confirma o desfazer?"):
                organizador.desfazer_ultima(simular=False)
                print("Movimentação desfeita.")
            return
        origem_texto = perguntar("Pasta a analisar", obrigatorio=True)
        destino_texto = perguntar("Pasta Carreira de destino", obrigatorio=True)
        if origem_texto is None or destino_texto is None:
            return
        movimentos = organizador.planejar(Path(origem_texto), Path(destino_texto))
        if not movimentos:
            print("Nenhum arquivo encontrado para organizar.")
            return
        for item in movimentos:
            print(f"{item.categoria}: {item.origem} -> {item.destino}")
        if not confirmar("Sair do modo de simulação e mover todos os arquivos?"):
            print("Simulação concluída; nenhum arquivo foi movido.")
            return
        quantidade = organizador.executar(movimentos, simular=False)
        print(f"{quantidade} arquivo(s) movido(s), sem exclusões.")

    def editar_perfil(self) -> None:
        perfil = carregar_perfil(self.settings.profile_path)
        print(json.dumps(perfil, ensure_ascii=False, indent=2))
        print("1. Adicionar conhecimento\n2. Adicionar área\n3. Adicionar localidade")
        escolha = perguntar("Opção", obrigatorio=True)
        if escolha is None:
            return
        campos = {"1": "conhecimentos", "2": "areas_desejadas", "3": "localidades_desejadas"}
        campo = campos.get(escolha)
        if not campo:
            print("Opção inválida.")
            return
        valor = perguntar("Novo valor", obrigatorio=True)
        if valor is None:
            return
        perfil.setdefault(campo, []).append(valor)
        if confirmar(f"Salvar alteração em {self.settings.profile_path}?"):
            salvar_perfil(self.settings.profile_path, perfil)
            print("Perfil atualizado. Reanalise vagas existentes para recalcular as notas.")

    def exportar_relatorio(self) -> None:
        print(self.relatorios.formatar_terminal())
        print("1. Markdown (resumo)\n2. CSV (vagas)")
        escolha = perguntar("Formato", obrigatorio=True)
        if escolha is None:
            return
        extensao = "md" if escolha == "1" else "csv" if escolha == "2" else ""
        if not extensao:
            print("Formato inválido.")
            return
        destino = PROJECT_ROOT / "exports" / f"relatorio_{date.today().isoformat()}.{extensao}"
        destino_existe = destino.exists()
        if destino_existe and not confirmar(f"O arquivo {destino} existe. Sobrescrever?"):
            return
        if not destino_existe and not confirmar(f"Criar o arquivo {destino}?"):
            return
        arquivo = (
            self.relatorios.exportar_markdown(destino, sobrescrever=destino_existe)
            if extensao == "md"
            else self.relatorios.exportar_csv(destino, sobrescrever=destino_existe)
        )
        print(f"Relatório exportado para {arquivo}")
