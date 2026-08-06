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

### Regra completa da compatibilidade

| Componente | Máximo | Regra resumida |
|---|---:|---|
| Técnica | 55 | proporção ponderada dos requisitos técnicos presentes no perfil |
| Área | 15 | título/descrição alinhados às áreas desejadas |
| Nível | 10 | nível alinhado ao perfil |
| Localização/modalidade | 10 | local ou modalidade desejados |
| Experiência | 5 | compara maior quantidade de anos encontrada com o perfil |
| Formação | 5 | compara ensino superior/cursando/completo quando informado |
| Penalidade de nível | −6/−12 | pleno ou sênior/especialista acima do perfil iniciante |

Obrigatórios pesam 2, requisitos comuns 1 e desejáveis 0,75. Sem requisitos técnicos, a parcela
técnica usa o valor neutro 27,5/55 e exige confirmação manual. Com apenas um ou dois requisitos
técnicos, a parcela fica limitada a 42/55; se a confiança for baixa por outras razões, o limite é
45/55. Assim, uma única tecnologia compatível não pode produzir 100%, mas a confiança baixa também
não transforma automaticamente uma boa aderência em nota baixa.

### Regra completa da confiança

A confiança é calculada separadamente em uma escala interna de 0–100. Ela não entra na nota de
compatibilidade e combina:

- até 42 pontos pela quantidade total de requisitos (7 por requisito, até seis);
- até 10 pontos pela quantidade de requisitos técnicos (2 por item, até cinco);
- 8 pontos quando há requisito obrigatório;
- 5 pontos pela presença de escolaridade;
- 5 pontos pela presença de experiência ou anos exigidos;
- 5 pontos quando o nível está informado no campo ou texto;
- 0, 3, 6 ou 10 pontos conforme a descrição tenha menos de 160, 160–349, 350–799 ou pelo menos
  800 caracteres;
- até 10 pontos pela proporção de evidências presentes entre requisitos, técnica,
  obrigatoriedade, escolaridade, experiência, nível e descrição adequada;
- menos 15 pontos se o texto terminar com reticências/“ver mais” ou tiver sinais de corte.

Os pontos são combinados com guardrails de volume: zero a dois requisitos resultam em confiança
baixa; três a cinco podem resultar em baixa ou média; alta exige pelo menos seis requisitos e 72
pontos internos. Abaixo de 40 pontos a confiança é baixa; com seis ou mais, 40–71 é média. Essa
combinação evita depender apenas de limites fixos e leva em conta campos ausentes e qualidade do
texto.

Na interface, confiança baixa exibe o aviso para revisão manual, quantidade de requisitos,
eventual truncamento e a limitação técnica. A seção “Como esta pontuação foi calculada?” mostra os
seis componentes, penalidades, fatores positivos, negativos e itens para confirmação sem exigir que
o visitante interprete a fórmula.

`analisar_temporaria()` executa tudo sem repository. `cadastrar_e_analisar()` usa o mesmo cálculo e
depois persiste. Assim, a página pública não precisa criar registros para analisar uma descrição.

## 4.1 Modalidade

`classificar_modalidade()` prioriza campos estruturados conhecidos da fonte. Sem campo estruturado,
procura híbrido, presencial e remoto no título, localização e descrição, remove negações simples e
ignora contextos como “acesso remoto a servidores”. Termos de possibilidade viram “Possivelmente
remoto”. O modelo registra `modalidade_origem`, `modalidade_confianca` e
`modalidade_inferida`; a interface nunca apresenta inferência como dado confirmado da fonte.

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
