# Guia de estudo do VagaScan

Use este guia para seguir dados reais pelo projeto. Em cada tema, responda: de onde veio, quem
validou, quem transformou, onde foi salvo e o que chegou à interface.

## 1. Uma busca Adzuna

1. `ConsultaVagas` recebe termo, local, página e filtros.
2. `VagaService.buscar_e_salvar()` consulta `CacheBuscaRepository`.
3. Em cache miss, `ProvedorAdzuna.consultar()` valida e faz um GET.
4. `_converter()` transforma JSON externo em `Vaga` e preserva `redirect_url`.
5. O serviço extrai requisitos, calcula compatibilidade e deduplica.
6. Vaga e requisitos são gravados na mesma transação.
7. CLI ou Jinja2 mostram contagens, cache e erros seguros.

Observe que `app_id` e `app_key` pertencem a `Settings`, não a `ConsultaVagas`; por isso a chave do
cache não consegue armazená-los acidentalmente.

## 2. Cache e falhas

A chave usa JSON ordenado e SHA-256. Cache válido evita rede. Cache expirado normalmente é ignorado,
mas pode ser reutilizado por até 24 horas após timeout, conexão, 429 ou 5xx.

Compare:

- 400: filtros inválidos; não usar cache antigo;
- 401/403/410: credencial recusada; não mascarar com cache;
- 429: limite temporário; fallback é permitido;
- 5xx/timeout/conexão: fonte instável; uma repetição e fallback;
- JSON/estrutura inválida: resposta não confiável; não usar fallback.

## 3. Migração SQLite

Abra `database.py`. A versão só entra em `schema_migrations` depois que suas instruções concluem.
Um banco antigo é marcado como versão inicial sem apagar dados e recebe novas colunas via
`ALTER TABLE`.

Pesquise nos testes por `test_migracao_preserva_banco_legado`: ele cria um schema anterior, insere
uma vaga, inicializa a versão nova e confirma dado, colunas e versões.

## 4. Compatibilidade

O analisador encontra termos canônicos e sinônimos, respeita limites de palavra e negações simples.
A calculadora distribui pontos entre técnica, área, nível, local/modalidade, experiência e formação.
Requisitos repetidos não inflam a nota; níveis acima do perfil recebem penalidade explícita.

`analisar_temporaria()` executa tudo sem repository. `cadastrar_e_analisar()` usa o mesmo cálculo e
depois persiste. Assim, a página pública não precisa criar registros para analisar uma descrição.

## 5. Separação público/privado

`bootstrap.criar_contexto(publico=True)` escolhe banco e perfil públicos. O contexto privado usa os
arquivos principais. Rotas públicas nunca recebem o repository privado; isso é mais forte do que
apenas esconder um botão no HTML.

Teste a separação buscando uma vaga pública e verificando que o repository privado continua vazio.

## 6. Login, sessão e CSRF

`gerar_hash_senha()` usa scrypt com salt aleatório. `verificar_senha()` recalcula e compara em tempo
constante. A senha pura não é armazenada.

Depois do login, a sessão assinada contém somente o nome administrativo e um token CSRF. Todo POST
compara o campo oculto com o token da sessão. Logout limpa o cookie.

Autoescape do Jinja transforma `<script>` vindo de uma API em texto. A CSP bloqueia scripts inline,
objetos e framing. Esses controles são complementares: nenhum substitui o outro.

## 7. Perfil seguro

O formulário transforma textareas em listas. `PerfilService` valida contagem, tamanho, anos e
conhecimentos obrigatórios. Antes da substituição atômica, copia o arquivo anterior para um backup
datado ignorado pelo Git.

Salvar não reanalisa automaticamente. O POST separado torna custo e efeito explícitos.

## 8. CLI e web compartilhadas

`bootstrap.py` monta os mesmos serviços usados por `main.py` e `web/app.py`. Regras de deduplicação,
análise, cache e SQL não aparecem nas rotas ou no menu.

Isso reduz divergência: corrigir uma regra no serviço altera ambas as interfaces e seus testes.

## 9. Exercícios

1. Adicione uma categoria a `keywords.json` e escreva o teste antes da mudança.
2. Crie um teste para cache com mais de 24 horas e confirme que o fallback é recusado.
3. Explique por que remoto é filtrado localmente e como isso afeta paginação.
4. Use `EXPLAIN QUERY PLAN` para o índice de status e o índice de cache.
5. Adicione um campo opcional ao perfil sem quebrar um JSON antigo.
6. Teste uma tentativa CSRF em atualização de status.
7. Explique por que `redirect_url` é salvo sem remover rastreadores, mas a chave de deduplicação usa
   uma versão normalizada.
8. Descreva o que precisaria mudar para múltiplos workers e PostgreSQL.

## 10. Perguntas de entrevista

1. Qual a diferença entre autenticação, sessão, autorização e CSRF?
2. Por que cache não deve conter credenciais?
3. Quando um fallback antigo é melhor do que um erro e quando é perigoso?
4. Como uma migração pode preservar um SQLite já usado?
5. Por que separar banco público e privado além de separar rotas?
6. Como Jinja autoescape e CSP reduzem riscos diferentes de XSS?
7. Por que o provedor não grava diretamente no banco?
8. Quais limites impedem SQLite e rate limiting em memória de escalar horizontalmente?
