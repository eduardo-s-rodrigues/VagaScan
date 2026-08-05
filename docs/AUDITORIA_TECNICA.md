# Auditoria técnica — 5 de agosto de 2026

## Escopo

A auditoria foi feita sobre o VagasScan existente, sem reiniciar o projeto. Código, banco, SQL,
provedores, analisadores, compatibilidade, deduplicação, candidaturas, relatórios, arquivos, CLI,
dependências, configuração, documentação e testes foram inspecionados.

Todos os bancos e arquivos usados nos fluxos de auditoria ficaram sob `data/audit-*` ou nas pastas
temporárias do pytest. Nenhum documento pessoal foi lido ou movimentado.

## Falhas reproduzidas antes da correção

- `Python não é necessário` ainda extraía Python como requisito.
- Repetir o requisito Python elevava a mesma vaga de 62,5 para 80,8 pontos.
- Empresa vazia era persistida como texto vazio.
- `data-invalida` e `etapa inventada` eram aceitas em candidaturas.
- Uma chamada direta do relatório sobrescrevia um arquivo existente.
- O organizador aceitava uma pasta de projeto como origem.
- O SQLite temporário não podia ser removido no Windows após consultas: uma conexão de leitura
  continuava aberta porque `with sqlite3.Connection` não fecha a conexão.
- Texto acentuado recebido por pipe do PowerShell podia ser armazenado como mojibake.

## Correções principais

- context manager próprio fecha toda conexão SQLite de consulta;
- vaga e requisitos passam pela mesma transação;
- candidatura, etapa, status e histórico são sincronizados atomicamente;
- datas ISO, etapas, campos essenciais, nulos previsíveis e notas são validados;
- requisitos iguais são consolidados; formação/experiência não duplicam a parcela técnica;
- negações simples são ignoradas e plural de obrigatório/desejável recebe o peso correto;
- pleno perde 6 pontos e sênior/especialista 12, com explicação e limite 0–100;
- URL com credenciais é rejeitada, sessão HTTP é fechada e erro de rede não mostra URL/token;
- relatórios não sobrescrevem por padrão, usam arquivo temporário e neutralizam fórmulas CSV;
- o organizador bloqueia projeto, symlinks e junctions, não troca destino após confirmação, valida
  histórico e tenta rollback do lote em falha;
- stdin é configurado como UTF-8 sem substituir a saída nativa do console Windows;
- o banco de demonstração ganhou caminho próprio configurável.

## Evidências finais

```text
tests/test_audit_flow.py ... PASSED
71 passed, 1 skipped in 1.69s
All checks passed!
No broken requirements found.
```

O skip corresponde à criação de symlink de arquivo, negada pela política do Windows da máquina. A
mesma proteção foi exercitada com uma junction real do Windows:

```text
JUNCTION_DETECTADA True
JUNCTION_BLOQUEADA A pasta de origem não pode atravessar links simbólicos.
ARQUIVO_ALVO_INTACTO True
```

A CLI real, apontada para bancos temporários, confirmou:

```text
Banco principal: 2 vagas manuais/importadas, 7 requisitos
Banco de demonstração: 3 vagas, 21 requisitos
Entrada UTF-8: título, modalidade e nível preservados
```

## Comandos executados

```powershell
python -m pip install -e ".[dev]"
python -m vagasscan --somente-inicializar
python -m vagasscan --carregar-demo
python -m pytest -vv tests\test_audit_flow.py --basetemp=data\audit-pytest-flow
python -m pytest --basetemp=data\audit-pytest-final -rs
python -m ruff check .
python -m compileall -q vagasscan tests
python -m pip check
```

## Limitações mantidas conscientemente

- nenhuma chamada real foi feita a uma API sem URL/credenciais fornecidas;
- regras de negação não substituem compreensão humana de linguagem natural;
- rollback de arquivos entre volumes é de melhor esforço;
- o histórico é validado, mas não possui assinatura contra adulteração intencional;
- SQLite e CLI são voltados a um usuário local, sem agendador ou sincronização.
