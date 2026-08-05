from __future__ import annotations

from pathlib import Path

import pytest

from vagasscan.file_organizer import OrganizadorArquivos


def test_organizador_em_simulacao_nao_move_arquivos(tmp_path: Path) -> None:
    origem = tmp_path / "entrada"
    destino = tmp_path / "Carreira"
    origem.mkdir()
    curriculo = origem / "Currículo Python.pdf"
    teste = origem / "desafio_backend.zip"
    curriculo.write_text("conteúdo", encoding="utf-8")
    teste.write_text("conteúdo", encoding="utf-8")
    organizador = OrganizadorArquivos(tmp_path / "historico.json")
    movimentos = organizador.planejar(origem, destino)
    assert {item.categoria for item in movimentos} == {"Curriculos", "Testes_Tecnicos"}
    assert organizador.executar(movimentos, simular=True) == 2
    assert curriculo.exists()
    assert not destino.exists()
    assert not (tmp_path / "historico.json").exists()


def test_organizador_nao_sobrescreve_destino(tmp_path: Path) -> None:
    origem = tmp_path / "entrada"
    destino = tmp_path / "Carreira"
    origem.mkdir()
    (destino / "Curriculos").mkdir(parents=True)
    (origem / "cv.pdf").write_text("novo", encoding="utf-8")
    (destino / "Curriculos" / "cv.pdf").write_text("antigo", encoding="utf-8")
    movimento = OrganizadorArquivos(tmp_path / "historico.json").planejar(origem, destino)[0]
    assert movimento.destino.name == "cv_1.pdf"


def test_destino_ocupado_depois_da_simulacao_interrompe_movimento(tmp_path: Path) -> None:
    origem = tmp_path / "entrada"
    destino = tmp_path / "Carreira"
    origem.mkdir()
    arquivo = origem / "cv.pdf"
    arquivo.write_text("original", encoding="utf-8")
    organizador = OrganizadorArquivos(tmp_path / "historico.json")
    movimento = organizador.planejar(origem, destino)[0]
    movimento.destino.parent.mkdir(parents=True)
    movimento.destino.write_text("ocupado", encoding="utf-8")
    with pytest.raises(FileExistsError, match="nova simulação"):
        organizador.executar([movimento], simular=False)
    assert arquivo.read_text(encoding="utf-8") == "original"
    assert movimento.destino.read_text(encoding="utf-8") == "ocupado"


def test_movimentacao_real_pode_ser_desfeita(tmp_path: Path) -> None:
    origem = tmp_path / "entrada"
    destino = tmp_path / "Carreira"
    origem.mkdir()
    arquivo = origem / "certificado_python.pdf"
    arquivo.write_text("certificado", encoding="utf-8")
    organizador = OrganizadorArquivos(tmp_path / "historico.json")
    movimento = organizador.planejar(origem, destino)[0]
    assert organizador.executar([movimento], simular=False) == 1
    assert not arquivo.exists()
    assert movimento.destino.exists()
    reversoes = organizador.desfazer_ultima(simular=True)
    assert reversoes[0].destino == arquivo.resolve()
    organizador.desfazer_ultima(simular=False)
    assert arquivo.read_text(encoding="utf-8") == "certificado"
    assert not movimento.destino.exists()
    assert organizador.desfazer_ultima(simular=True) == []


def test_pasta_protegida_nao_pode_ser_organizada(tmp_path: Path) -> None:
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / "main.py").write_text("print('oi')", encoding="utf-8")
    organizador = OrganizadorArquivos(
        tmp_path / "historico.json", caminhos_protegidos=(projeto,)
    )
    with pytest.raises(ValueError, match="projeto VagasScan"):
        organizador.planejar(projeto, tmp_path / "Carreira")


def test_link_simbolico_e_ignorado(tmp_path: Path) -> None:
    origem = tmp_path / "entrada"
    origem.mkdir()
    alvo = tmp_path / "fora.txt"
    alvo.write_text("não mover", encoding="utf-8")
    link = origem / "curriculo_link.txt"
    try:
        link.symlink_to(alvo)
    except OSError:
        pytest.skip("Criação de link simbólico não permitida neste Windows.")
    movimentos = OrganizadorArquivos(tmp_path / "historico.json").planejar(
        origem, tmp_path / "Carreira"
    )
    assert movimentos == []
    assert alvo.exists()


def test_falha_no_meio_do_lote_reverte_arquivos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origem = tmp_path / "entrada"
    origem.mkdir()
    for nome in ("cv_a.pdf", "cv_b.pdf"):
        (origem / nome).write_text(nome, encoding="utf-8")
    organizador = OrganizadorArquivos(tmp_path / "historico.json")
    movimentos = organizador.planejar(origem, tmp_path / "Carreira")
    from vagasscan.file_organizer import organizer as modulo

    mover_real = modulo.shutil.move
    chamadas = 0

    def mover_com_falha(origem_path: str, destino_path: str) -> str:
        nonlocal chamadas
        chamadas += 1
        if chamadas == 2:
            raise OSError("falha simulada")
        return mover_real(origem_path, destino_path)

    monkeypatch.setattr(modulo.shutil, "move", mover_com_falha)
    with pytest.raises(RuntimeError, match="revertidas"):
        organizador.executar(movimentos, simular=False)
    assert all(item.origem.exists() for item in movimentos)
    assert not (tmp_path / "historico.json").exists()


def test_historico_corrompido_nao_e_executado(tmp_path: Path) -> None:
    historico = tmp_path / "historico.json"
    historico.write_text('{"origem": "arquivo arbitrário"}', encoding="utf-8")
    with pytest.raises(ValueError, match="histórico"):
        OrganizadorArquivos(historico).desfazer_ultima(simular=False)
