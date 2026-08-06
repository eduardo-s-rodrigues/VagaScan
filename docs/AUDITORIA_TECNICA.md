# Auditoria técnica — evolução web, Adzuna e experiência pública

## Estado inicial da rodada final — 6 de agosto de 2026

- repositório clonado de `origin/main` no commit
  `6705444f41938f942f5d4e4577ef0c26de13dad3` (`feat: aprimorar interface e experiência de busca`);
- working tree limpo antes da execução; nenhum commit, push, deploy, DNS ou variável real alterada;
- Python 3.14.6 no Windows;
- baseline executado com `python -m pytest --basetemp=data/pytest-temporario`:
  **115 aprovados, 1 ignorado**, com aviso de depreciação Starlette/httpx;
- baseline `python -m ruff check .`: aprovado;
- o diretório `data/pytest-temporario` estava rastreado e foi restaurado após a execução inicial,
  sem manter artefatos gerados;
- compatibilidade podia chegar a 100% com um único requisito compatível;
- não existia métrica separada de confiança nem componentes estruturados da nota;
- modalidade era inferida por ocorrência simples, inclusive em “não é remoto”, sem origem/confiança;
- o filtro público de modalidade examinava somente o lote atual;
- o erro público de configuração mostrava `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` e `.env`;
- contadores públicos usavam “cadastradas” e “duplicatas”;
- vagas salvas v1 permitiam apenas salvar/remover, com limite fixo 100;
- não havia páginas institucionais, canonical, robots, sitemap, manifest ou imagem social;
- detalhes não separavam confiança, componentes, fatores, origem da modalidade ou truncamento.

Os valores do `.env` não foram lidos nem impressos.

## Mudanças da rodada final

- migração 4 aditiva preserva bancos e registra confiança/modalidade;
- confiança combina volume, diversidade de campos, qualidade e truncamento da descrição;
- modalidade estruturada tem prioridade; inferência trata negação, possibilidade e contexto técnico;
- cache é anterior ao rate limit, e modalidade/remoto não fragmentam sua chave;
- mensagens públicas são mapeadas por código, enquanto detalhes permanecem em logs/admin/dev;
- interface recebeu loading, estados vazios/erro, filtros preservados, cards e detalhes explicáveis;
- armazenamento local v2 valida, limita, deduplica, importa e exporta sem usar `innerHTML`;
- SEO, páginas institucionais, acessibilidade e documentação de volume Railway foram adicionados.

## Evidências finais da rodada de 6 de agosto de 2026

- comando obrigatório `python -m pytest --basetemp=data/pytest-temporario`:
  **142 aprovados, 1 ignorado e 1 aviso** na última execução;
- o teste ignorado continua sendo o caso de symlink sem permissão no Windows; o aviso é a
  depreciação não bloqueante do `TestClient` Starlette/httpx;
- `python -m ruff check .`: aprovado;
- `python -m compileall -q vagasscan tests`: aprovado;
- `python -m pip check`: nenhuma dependência quebrada;
- `git diff --check`: aprovado, com apenas avisos informativos LF/CRLF do Git no Windows;
- banco novo inicializado em diretório isolado; demonstração carregou 3 vagas, sem duplicata ou
  erro; CLI abriu e encerrou sem falha;
- servidor local isolado: `/health`, home e CSS responderam 200; CSP permaneceu presente;
- busca de demonstração respondeu 200 e exibiu resultados; falha de configuração Adzuna respondeu
  503 com mensagem pública genérica e sem nomes de variáveis ou `.env`;
- cache válido sem consulta externa respondeu 200, informou origem/idade e não acionou bloqueio;
- navegador local: 360, 768 e 1280 px sem overflow horizontal; formulário e botão ficaram dentro
  da primeira dobra em 360 × 800; reflow equivalente a 200% foi verificado em 640 CSS px;
- menu móvel abriu por teclado e fechou com `Escape`, devolvendo o foco; filtros, estado vazio,
  recuperação de erro, salvos, detalhes, páginas institucionais e metadados SEO foram exercitados;
- os handlers de salvos geraram JSON/CSV, importaram schema v2, eliminaram duplicata e rejeitaram
  item com markup em um harness Node isolado; fallback corrompido e limite também foram verificados;
- nenhum erro ou aviso apareceu no console do navegador;
- a API real da Adzuna não foi consumida: buscas de QA usaram demonstração, mocks ou cache sem rede;
- nenhum commit, push, deploy, DNS ou variável real de ambiente foi alterado.

O controle de navegador usado na auditoria não expõe comando de zoom nativo. Por isso, a validação
automatizada de 200% foi feita pelo reflow equivalente de 1280 para 640 CSS px; recomenda-se repetir
o zoom nativo em Chrome/Firefox antes da publicação.

## Estado inicial da evolução anterior

- commit de origem: `430c9a919f210c89647c92866aa4697e8c229d45`;
- branch `main`, sem commit, push ou deploy desta evolução;
- alteração pré-existente em `.env.example` preservada e completada;
- Python 3.14.6 na máquina de auditoria; projeto continua declarando Python 3.12+;
- suíte inicial: 71 aprovados e 1 ignorado por permissão de symlink no Windows;
- Ruff inicial: aprovado;
- `.env` presente localmente, ignorado por `.gitignore` e não rastreado;
- CLI, SQLite, cadastro, análise, candidaturas, relatórios, organizador, demo e HTTP existentes;
- ausência inicial de web, autenticação, Adzuna dedicada, cache, paginação e migrações.

Nenhum valor do `.env` foi impresso ou incluído nesta auditoria.

## Arquitetura implementada

- `ProvedorAdzuna` dedicado ao endpoint oficial, com credenciais em query params;
- `ConsultaVagas`/`ResultadoBusca` e ponte compatível para provedores existentes;
- cache normalizado em SQLite, chave canônica sem segredos e fallback limitado;
- `schema_migrations` com reconhecimento do banco legado e alterações aditivas;
- contextos público e privado com bancos/perfis separados;
- `VagaService` compartilhado por CLI e FastAPI;
- `PerfilService` com validação, backup e substituição atômica;
- FastAPI/Jinja2 com rotas públicas e dashboard privado;
- autenticação scrypt, sessão assinada, CSRF e rate limiting em memória.
- autorização de consulta externa executada apenas após cache miss, com relógio injetável;
- experiência pública com filtros locais, painel de métricas e vagas salvas no navegador.

## Revisão de segurança

### Credenciais e logs

Adzuna recebe `app_id`/`app_key` somente em `requests` `params`. O código não registra URL
preparada, headers, payload ou credenciais. Cache serializa apenas consulta e modelos normalizados.
Health check devolve somente status.

### Sessão, senha e CSRF

Senha usa scrypt com salt aleatório e comparação constante. Cookie é HttpOnly, SameSite=Lax, expira
em oito horas e fica Secure em produção. Todos os POSTs exigem token CSRF, incluindo login/logout.

### XSS e links

Templates Jinja mantêm autoescape. URLs externas só são renderizadas quando HTTP(S), e links abrem
com `noopener noreferrer`. CSP permite recursos locais, bloqueia objetos e framing. Testes inserem
`<script>` em resposta mockada e confirmam escaping.

### SQL e dados pessoais

Repositories usam parâmetros e transações. Rotas públicas recebem somente o contexto público e
`obter_publico()` seleciona campos permitidos. Banco, perfil, logs e documentos não são montados
como arquivos estáticos.

### Arquivos

Não existe upload. O organizador público não existe; a rota privada depende de flag e caminhos do
servidor. O navegador só confirma uma simulação e nunca informa caminhos.

### Limites conhecidos

Rate limiting é local ao processo e reinicia com ele. SQLite e os contadores pressupõem um worker.
Hospedagem horizontal exige PostgreSQL e limitador compartilhado. O visitante é representado nos
contadores por HMAC em memória, sem IP completo persistido ou registrado. Cache, demonstração,
modalidade e ordenação local não consomem a cota de busca externa. Filtro remoto é heurístico. A
licença e limites da Adzuna devem ser reconfirmados antes de publicar.

“Vagas salvas” usa exclusivamente o armazenamento local versionado do navegador, limitado a 100
itens e com URLs HTTP(S) validadas. Não grava candidatura, não consulta o banco privado e não
sincroniza entre dispositivos.

## Evidências finais

Validações executadas em 5 de agosto de 2026, no Windows e Python 3.14.6:

- dependências instaladas em modo editável com o conjunto de desenvolvimento;
- `pytest`: **115 aprovados, 1 ignorado**;
- teste ignorado: criação de symlink não permitida neste Windows, mesma restrição da linha de base;
- aviso não bloqueante: o `TestClient` da versão instalada da Starlette sinaliza futura migração de
  `httpx` para `httpx2`;
- `ruff check .`: aprovado;
- `compileall`: aprovado para `vagasscan` e `tests`;
- `pip check`: nenhuma dependência quebrada;
- `git diff --check`: aprovado, com apenas avisos informativos de futura conversão LF/CRLF;
- inicialização do banco temporário: aprovada;
- carga da demonstração temporária: três vagas cadastradas, sem duplicata ou erro;
- smoke da CLI: menu abriu e encerrou normalmente;
- smoke HTTP local: `/health` retornou exatamente `{"status":"ok"}`, home respondeu 200 e CSP
  estava presente;
- `TestClient`: home, busca mockada, cache hit/miss, cooldown, limites público/administrativo,
  análise temporária, login/logout, sessão, CSRF, autorização, dashboard, vaga/status, candidatura,
  relatórios, perfil/backup, cards, métricas, salvos e headers aprovados;
- navegador local: layouts verificados em 360, 768 e 1280 px, sem overflow horizontal; menu móvel,
  foco visível de teclado, headings, formulário, filtro, ordenação, salvar/recarregar/listar/remover e
  atualização da interface verificados; nenhum erro ou aviso no console;
- consulta Adzuna real opcional: não executada nesta evolução visual; buscas de QA usaram somente o
  provedor de demonstração e sessões mockadas;
- `git check-ignore -v .env`: confirmou a regra `.gitignore:1:.env`;
- `.env` não rastreado;
- comparação silenciosa de valores secretos locais: zero correspondências em arquivos rastreados e
  zero nos logs da auditoria;
- inspeção dos logs: zero ocorrências de padrões sensíveis como `app_key=`, `app_id=` ou header de
  autorização.

Nenhum commit, push, deploy, publicação, alteração de DNS ou leitura exibida do `.env` foi feito.
