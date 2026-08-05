from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from vagasscan.utils.text import normalizar_texto

LOGGER = logging.getLogger(__name__)

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
EXTENSOES_COMPACTADAS = {".zip", ".rar", ".7z", ".tar", ".gz"}


@dataclass(slots=True)
class Movimentacao:
    origem: Path
    destino: Path
    categoria: str


class OrganizadorArquivos:
    def __init__(
        self, historico_path: Path, *, caminhos_protegidos: tuple[Path, ...] = ()
    ) -> None:
        self.historico_path = historico_path
        self.caminhos_protegidos = tuple(path.resolve() for path in caminhos_protegidos)

    def _caminho_protegido(self, path: Path) -> bool:
        resolvido = path.resolve()
        return any(
            resolvido == protegido or resolvido.is_relative_to(protegido)
            for protegido in self.caminhos_protegidos
        )

    @staticmethod
    def _eh_link(path: Path) -> bool:
        return path.is_symlink() or path.is_junction()

    @classmethod
    def _possui_link_simbolico(cls, path: Path) -> bool:
        atual = path
        while True:
            if cls._eh_link(atual):
                return True
            if atual.parent == atual:
                return False
            atual = atual.parent

    @staticmethod
    def classificar(arquivo: Path) -> str:
        nome = normalizar_texto(arquivo.stem)
        if any(termo in nome for termo in ("curriculo", "curriculum", "resume", "cv")):
            return "Curriculos"
        if any(termo in nome for termo in ("certificado", "certificate", "diploma")):
            return "Certificados"
        if any(termo in nome for termo in ("vaga", "job description", "descricao")):
            return "Vagas"
        if any(termo in nome for termo in ("entrevista", "recrutador")):
            return "Entrevistas"
        if any(termo in nome for termo in ("teste", "desafio", "challenge")):
            return "Testes_Tecnicos"
        if arquivo.suffix.lower() in EXTENSOES_IMAGEM:
            return "Outros/Imagens"
        if arquivo.suffix.lower() in EXTENSOES_COMPACTADAS:
            return "Outros/Compactados"
        return "Outros/Documentos"

    @staticmethod
    def _destino_livre(destino: Path) -> Path:
        if not destino.exists() and not OrganizadorArquivos._eh_link(destino):
            return destino
        contador = 1
        while True:
            candidato = destino.with_name(f"{destino.stem}_{contador}{destino.suffix}")
            if not candidato.exists() and not OrganizadorArquivos._eh_link(candidato):
                return candidato
            contador += 1

    def planejar(self, origem: Path, carreira: Path) -> list[Movimentacao]:
        if self._eh_link(origem) or self._possui_link_simbolico(origem):
            raise ValueError("A pasta de origem não pode atravessar links simbólicos.")
        if not origem.is_dir():
            raise ValueError(f"A pasta de origem não existe: {origem}")
        origem_resolvida = origem.resolve()
        carreira_resolvida = carreira.resolve()
        if self._caminho_protegido(origem_resolvida) or self._caminho_protegido(
            carreira_resolvida
        ):
            raise ValueError("A origem e o destino não podem ficar dentro do projeto VagasScan.")
        if origem_resolvida == carreira_resolvida:
            raise ValueError("A origem e o destino da organização devem ser diferentes.")
        if self._possui_link_simbolico(carreira):
            raise ValueError("A pasta de destino não pode atravessar links simbólicos.")
        movimentos: list[Movimentacao] = []
        for arquivo in sorted(origem.iterdir()):
            if self._eh_link(arquivo):
                LOGGER.warning("Link simbólico ignorado na organização: %s", arquivo)
                continue
            if not arquivo.is_file():
                continue
            categoria = self.classificar(arquivo)
            destino = self._destino_livre(carreira_resolvida / categoria / arquivo.name)
            if not destino.is_relative_to(carreira_resolvida):
                raise ValueError(f"Destino fora da pasta Carreira: {destino}")
            if arquivo.resolve() != destino.resolve():
                movimentos.append(Movimentacao(arquivo.resolve(), destino, categoria))
        return movimentos

    def executar(self, movimentos: list[Movimentacao], *, simular: bool = True) -> int:
        self._validar_movimentos(movimentos)
        if simular:
            LOGGER.info("Simulação de organização: %s arquivo(s)", len(movimentos))
            return len(movimentos)
        return self._executar_lote(movimentos, registrar_historico=True)

    def _validar_movimentos(self, movimentos: list[Movimentacao]) -> None:
        origens: set[Path] = set()
        destinos: set[Path] = set()
        for movimento in movimentos:
            if movimento.origem in origens or movimento.destino in destinos:
                raise ValueError("O plano contém origem ou destino repetido.")
            origens.add(movimento.origem)
            destinos.add(movimento.destino)
            if self._caminho_protegido(movimento.origem) or self._caminho_protegido(
                movimento.destino
            ):
                raise ValueError("O plano tenta movimentar arquivos do próprio VagasScan.")
            if self._eh_link(movimento.origem) or self._possui_link_simbolico(
                movimento.origem
            ):
                raise ValueError(f"A origem atravessa link simbólico: {movimento.origem}")
            if not movimento.origem.is_file():
                raise FileNotFoundError(f"Arquivo de origem não encontrado: {movimento.origem}")
            if movimento.destino.exists() or self._eh_link(movimento.destino):
                raise FileExistsError(
                    f"O destino ficou ocupado após a simulação: {movimento.destino}. "
                    "Execute uma nova simulação."
                )
            if self._possui_link_simbolico(movimento.destino.parent):
                raise ValueError(f"O destino atravessa link simbólico: {movimento.destino}")

    def _executar_lote(
        self, movimentos: list[Movimentacao], *, registrar_historico: bool
    ) -> int:
        realizados: list[Movimentacao] = []
        try:
            for movimento in movimentos:
                movimento.destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(movimento.origem), str(movimento.destino))
                realizados.append(movimento)
                LOGGER.info("Arquivo movido: %s -> %s", movimento.origem, movimento.destino)
            if realizados and registrar_historico:
                self._registrar(realizados, estado="concluido")
            return len(realizados)
        except Exception as exc:
            falhas_rollback: list[str] = []
            nao_revertidos: list[Movimentacao] = []
            for realizado in reversed(realizados):
                try:
                    if realizado.destino.is_file() and not realizado.origem.exists():
                        realizado.origem.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(realizado.destino), str(realizado.origem))
                except OSError as rollback_exc:
                    falhas_rollback.append(f"{realizado.destino}: {rollback_exc}")
                    nao_revertidos.append(realizado)
            if falhas_rollback:
                self._registrar(nao_revertidos, estado="falha_parcial")
                raise RuntimeError(
                    "A movimentação falhou e parte do lote não pôde ser revertida. "
                    "Consulte o histórico antes de continuar."
                ) from exc
            raise RuntimeError(
                "A movimentação falhou; alterações realizadas foram revertidas."
            ) from exc

    def _registrar(self, movimentos: list[Movimentacao], *, estado: str) -> None:
        historico = self._ler_historico()
        historico.append(
            {
                "versao": 1,
                "id": uuid.uuid4().hex,
                "data": datetime.now().astimezone().isoformat(timespec="seconds"),
                "desfeito": False,
                "estado": estado,
                "movimentos": [
                    {
                        "origem": str(item.origem),
                        "destino": str(item.destino),
                        "categoria": item.categoria,
                    }
                    for item in movimentos
                ],
            }
        )
        self._salvar_historico(historico)

    def _salvar_historico(self, historico: list[dict[str, object]]) -> None:
        if self._eh_link(self.historico_path):
            raise ValueError("O histórico de movimentações não pode ser um link simbólico.")
        self.historico_path.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.historico_path.with_name(
            f"{self.historico_path.name}.{uuid.uuid4().hex}.tmp"
        )
        temporario.write_text(
            json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporario.replace(self.historico_path)

    def _ler_historico(self) -> list[dict[str, object]]:
        if not self.historico_path.exists():
            return []
        try:
            dados = json.loads(self.historico_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("O histórico de movimentações está ilegível ou corrompido.") from exc
        if not isinstance(dados, list):
            raise ValueError("O histórico de movimentações não contém uma lista válida.")
        for registro in dados:
            if not isinstance(registro, dict) or not isinstance(registro.get("movimentos"), list):
                raise ValueError("O histórico de movimentações possui um registro inválido.")
            for item in registro["movimentos"]:
                if not isinstance(item, dict) or not all(
                    isinstance(item.get(chave), str)
                    for chave in ("origem", "destino", "categoria")
                ):
                    raise ValueError("O histórico possui uma movimentação inválida.")
        return dados

    def desfazer_ultima(self, *, simular: bool = True) -> list[Movimentacao]:
        historico = self._ler_historico()
        indice = next(
            (
                i
                for i in range(len(historico) - 1, -1, -1)
                if not historico[i].get("desfeito")
                and historico[i].get("estado", "concluido") == "concluido"
            ),
            None,
        )
        if indice is None:
            return []
        registro = historico[indice]
        reversoes = [
            Movimentacao(Path(item["destino"]), Path(item["origem"]), item["categoria"])
            for item in reversed(registro["movimentos"])
        ]
        if simular:
            self._validar_movimentos(reversoes)
            return reversoes
        self._validar_movimentos(reversoes)
        historico[indice]["estado"] = "desfazendo"
        self._salvar_historico(historico)
        try:
            self._executar_lote(reversoes, registrar_historico=False)
        except RuntimeError:
            historico[indice]["estado"] = "concluido"
            self._salvar_historico(historico)
            raise
        historico[indice]["desfeito"] = True
        historico[indice]["estado"] = "desfeito"
        self._salvar_historico(historico)
        return reversoes
