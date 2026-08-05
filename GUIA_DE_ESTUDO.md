# Guia de estudo do VagasScan

Este guia acompanha o caminho de um dado usando sempre cinco perguntas: de onde veio, quem recebeu,
o que foi processado, onde foi salvo e qual resultado voltou. Abra os arquivos citados, coloque
`print()` temporários para experimentar e depois execute os testes.

## API, requisição HTTP e JSON

1. **De onde veio o dado?** De uma URL real configurada em `JOB_API_URL` ou do provedor local.
2. **Quem recebeu?** `ProvedorHttpConfiguravel.buscar()` em `vagasscan/providers/`.
3. **O que foi processado?** `requests` faz um `GET`; a resposta JSON é validada e seus campos são
   convertidos para uma `Vaga`. JSON é um formato textual de objetos, listas, números e textos.
4. **Onde foi salvo?** O provedor não salva. Ele retorna objetos ao serviço, que decide persistir.
5. **Qual resultado voltou?** Uma lista de `Vaga` ou um erro previsível para timeout, limite, HTTP,
   credencial ausente ou formato inválido.

Uma API é um contrato entre programas. Requisição HTTP é a mensagem enviada a esse contrato. JSON
é um formato comum para a resposta. São conceitos relacionados, mas não são a mesma coisa.

## SQLite e SQL parametrizado

1. **De onde veio o dado?** De uma `Vaga`, `Requisito` ou `Candidatura` validada pelo fluxo.
2. **Quem recebeu?** Um repositório em `vagasscan/repositories/`.
3. **O que foi processado?** O repositório executa comandos `INSERT`, `SELECT` ou `UPDATE`.
4. **Onde foi salvo?** No arquivo SQLite configurado em `VAGASSCAN_DATABASE`.
5. **Qual resultado voltou?** ID criado, dicionário consultado ou confirmação da atualização.

SQLite é um banco relacional dentro de um arquivo. SQL parametrizado significa escrever
`WHERE id = ?` e enviar o valor separadamente. Isso preserva tipos, evita problemas de aspas e
reduz o risco de injeção de SQL. Transações confirmam todas as alterações juntas ou desfazem o
lote em caso de exceção.

## Deduplicação

1. **De onde veio o dado?** De uma vaga candidata a cadastro.
2. **Quem recebeu?** `VagaRepository.encontrar_duplicata()`.
3. **O que foi processado?** Primeiro fonte + ID externo; depois URL sem rastreadores; por último
   título + empresa + localização sem acentos, caixa ou espaços diferentes.
4. **Onde foi salvo?** Uma vaga certa é salva; uma coincidência duvidosa não apaga nem altera nada.
5. **Qual resultado voltou?** O ID novo ou mensagem com a vaga existente e a regra que coincidiu.

As duas primeiras regras são fortes e possuem índices únicos. A terceira é uma suspeita e a CLI
permite manter os dois registros após confirmação.

## Análise de texto

1. **De onde veio o dado?** Da descrição da vaga e de `data/keywords.json`.
2. **Quem recebeu?** `AnalisadorPalavrasChave`.
3. **O que foi processado?** Texto e sinônimos são normalizados; limites de palavras evitam casos
   como encontrar `java` dentro de `javascript`; a frase indica obrigatório ou desejável.
4. **Onde foi salvo?** Cada termo encontrado vai para `requisitos_vaga` com categoria e peso.
5. **Qual resultado voltou?** Uma lista de requisitos, indicando quais já aparecem no perfil.

O analisador é deliberadamente simples. Ele é fácil de explicar e ajustar, mas uma pessoa deve
confirmar ambiguidades.

## Cálculo de compatibilidade

1. **De onde veio o dado?** Dos requisitos extraídos, vaga e `data/profile.json`.
2. **Quem recebeu?** `CalculadoraCompatibilidade.calcular()`.
3. **O que foi processado?** Técnica vale 55 pontos; área 15; nível 10;
   localização/modalidade 10; experiência 5; formação 5. Obrigatórios pesam 2, comuns 1 e
   desejáveis 0,75. Itens repetidos são consolidados; pleno perde 6 pontos e sênior/especialista
   perde 12, sem zerar automaticamente.
4. **Onde foi salvo?** A nota vai para `vagas.compatibilidade`; requisitos ficam em sua tabela.
5. **Qual resultado voltou?** Nota, acertos, ausências, itens a confirmar e justificativa.

Se não houver requisito técnico detectado, a parte técnica recebe metade (27,5) e é marcada para
confirmação. Escolaridade e experiência são avaliadas fora dessa parcela para não serem contadas
duas vezes. Assim, silêncio do texto não vira nem reprovação nem aderência total.

## Logs

1. **De onde veio o dado?** De eventos importantes e erros da aplicação.
2. **Quem recebeu?** O módulo `logging` configurado por `configure_logging()`.
3. **O que foi processado?** Data, nível, módulo e mensagem são formatados.
4. **Onde foi salvo?** Por padrão, `logs/vagasscan.log`.
5. **Qual resultado voltou?** Um histórico técnico para diagnóstico sem poluir o terminal.

Nunca registre tokens, senhas ou descrições sensíveis completas.

## Testes

1. **De onde veio o dado?** De cenários pequenos preparados em `tests/`.
2. **Quem recebeu?** Funções reais da aplicação chamadas pelo pytest.
3. **O que foi processado?** Resultados são comparados com comportamentos esperados por `assert`.
4. **Onde foi salvo?** Bancos e arquivos ficam em pastas temporárias.
5. **Qual resultado voltou?** Teste aprovado ou falha com linha e diferença encontrada.

Fixtures evitam repetição. Um teste bom verifica comportamento observável, não detalhes internos
sem importância.

## Organização de arquivos

1. **De onde veio o dado?** De uma pasta escolhida explicitamente pelo usuário.
2. **Quem recebeu?** `OrganizadorArquivos.planejar()`.
3. **O que foi processado?** Nome e extensão determinam a categoria e um destino livre.
4. **Onde foi salvo?** Só após confirmação, na árvore `Carreira/`; o lote entra no histórico JSON
   por escrita temporária e substituição atômica.
5. **Qual resultado voltou?** Plano simulado, quantidade movida ou lista de reversões possíveis.

Não existe exclusão. Se um nome já existe durante a simulação, `_1`, `_2` e assim por diante são
acrescentados. Se o destino ficar ocupado depois da confirmação, a execução para e pede nova
simulação. Links simbólicos e o diretório do próprio projeto são recusados. Uma falha no meio do
lote tenta reverter os movimentos já feitos.

## Fluxo completo para acompanhar no depurador

1. A CLI recebe a descrição.
2. `VagaService.cadastrar_e_analisar()` carrega o perfil.
3. O analisador cria requisitos.
4. A calculadora produz a nota explicada.
5. O repositório verifica duplicatas e salva a vaga.
6. O repositório salva requisitos e nota na mesma base.
7. A CLI mostra o resultado sem prometer aprovação.

## Perguntas de entrevista

1. Por que este projeto usa SQLite em vez de um servidor PostgreSQL?
2. O que SQL parametrizado evita?
3. Qual a diferença entre erro de rede, HTTP 429 e JSON inválido?
4. Por que o provedor não grava diretamente no banco?
5. Como os três níveis de deduplicação diferem em confiança?
6. Por que uma vaga sem requisitos recebe pontuação técnica neutra?
7. O que acontece com uma transação se uma exceção for lançada?
8. Como adicionar um status sem espalhar textos pela aplicação?
9. Que risco existe ao mover arquivos e como o MVP o reduz?
10. Qual teste você criaria antes de alterar a fórmula de compatibilidade?
11. Por que fechar uma conexão SQLite exige mais do que usar `with connection`?
12. Como uma exportação CSV pode virar fórmula no Excel e como o projeto evita isso?

## Exercícios curtos

1. Adicione `Redis` e seus sinônimos ao JSON; escreva um teste.
2. Crie um filtro de modalidade no repositório e na CLI.
3. Adicione uma regra explícita para vaga sênior perder pontos de nível.
4. Faça a edição de perfil impedir itens repetidos, ignorando acentos e caixa.
5. Crie um relatório de tempo médio entre candidatura e mudança de status.
6. Implemente um provedor novo usando arquivo JSON local, sem alterar o serviço.
7. Teste HTTP 429 usando uma sessão falsa parecida com `tests/test_providers.py`.
8. Acrescente confirmação individual como alternativa à confirmação em lote do organizador.
