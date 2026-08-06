# Auditoria técnica — evolução web e Adzuna

## Estado inicial registrado

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
Hospedagem horizontal exige PostgreSQL e limitador compartilhado. Filtro remoto é heurístico. A
licença e limites da Adzuna devem ser reconfirmados antes de publicar.

## Evidências finais

Validações executadas em 5 de agosto de 2026, no Windows e Python 3.14.6:

- dependências instaladas em modo editável com o conjunto de desenvolvimento;
- `pytest`: **109 aprovados, 1 ignorado**, em 3,54 s;
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
- `TestClient`: home, busca mockada, cache, análise temporária, login/logout, sessão, CSRF,
  autorização, dashboard, vaga/status, candidatura, relatórios, perfil/backup e headers aprovados;
- navegador local: layouts verificados em 360, 768 e 1280 px, sem overflow horizontal; menu móvel,
  foco de teclado, headings e formulários verificados; nenhum erro ou aviso no console;
- consulta Adzuna real opcional: executada uma única vez, página 1, cinco resultados, sem cache ou
  persistência; credenciais não foram mostradas;
- `git check-ignore -v .env`: confirmou a regra `.gitignore:1:.env`;
- `.env` não rastreado;
- comparação silenciosa de valores secretos locais: zero correspondências em arquivos rastreados e
  zero nos logs da auditoria;
- inspeção dos logs: zero ocorrências de padrões sensíveis como `app_key=`, `app_id=` ou header de
  autorização.

Nenhum commit, push, deploy, publicação, alteração de DNS ou leitura exibida do `.env` foi feito.
