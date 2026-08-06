# VagaScan

Aplicação Python para buscar, analisar e acompanhar vagas de tecnologia. O mesmo núcleo atende a
CLI e a interface web: provedores obtêm anúncios, serviços analisam e coordenam casos de uso,
repositories usam SQLite e templates Jinja2 renderizam o site no servidor.

> A compatibilidade é uma estimativa baseada em regras e palavras-chave. Ela não garante aprovação
> em processo seletivo e não substitui a leitura humana.

## Funcionalidades

- integração oficial com a Adzuna, paginação, filtros documentados e `redirect_url` preservado;
- cache SQLite com expiração e fallback limitado para falhas transitórias/HTTP 429;
- provedor local fictício e provedor HTTP genérico configurável;
- cadastro manual, importação de descrição e análise explicável;
- deduplicação, status, candidaturas, próximas ações e histórico;
- dashboard, relatórios, edição segura do perfil e reanálise confirmada;
- área pública isolada do perfil e banco pessoais;
- autenticação de administrador único, CSRF, cookies seguros e headers HTTP;
- organizador de documentos local, simulado e explicitamente condicionado na web;
- testes sem consumo da cota real da Adzuna.

## Requisitos e instalação no Windows

Requer Python 3.12 ou mais recente. No PowerShell:

```powershell
python --version
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

O `Set-ExecutionPolicy` vale somente para a janela atual. Nunca envie `.env`, bancos, logs ou
backups de perfil ao Git.

## Configuração

Os caminhos padrão mantêm três finalidades separadas:

- `VAGASSCAN_DATABASE`: dados privados da CLI e do administrador;
- `VAGASSCAN_DEMO_DATABASE`: registros fictícios da demonstração local;
- `VAGASSCAN_PUBLIC_DATABASE`: buscas feitas por visitantes;
- `VAGASSCAN_PROFILE`: perfil real;
- `VAGASSCAN_PUBLIC_PROFILE`: perfil sanitizado de demonstração.

### Adzuna

Cadastre uma aplicação no portal da Adzuna e preencha localmente:

```dotenv
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
ADZUNA_COUNTRY=br
ADZUNA_RESULTS_PER_PAGE=20
ADZUNA_TIMEOUT=10
ADZUNA_CACHE_MINUTES=30
```

O adaptador usa `GET https://api.adzuna.com/v1/api/jobs/{pais}/search/{pagina}`. `app_id` e
`app_key` são parâmetros da requisição conforme o contrato oficial, nunca cabeçalho Authorization.
Página é limitada a 1–100, resultados a 1–50 e distância a 1–100 km. Contrato, jornada e ordenação
usam apenas valores aceitos pela API.

A API não possui parâmetro de trabalho remoto. Quando solicitado, o VagaScan filtra localmente
título, localização e descrição e informa que o total aproximado veio antes desse filtro.

O cache considera provedor, país, termo, local, página, quantidade e filtros. Um resultado válido
evita nova chamada. Em timeout, conexão, HTTP 429 ou 5xx, um cache com até 24 horas pode ser usado
como fallback marcado. Credenciais nunca entram no cache.

Resultados exibem “Vagas fornecidas pela Adzuna” e “Jobs by Adzuna”. O botão original mantém o
`redirect_url` e abre com proteção contra acesso à janela de origem. Consulte os
[termos da API](https://developer.adzuna.com/docs/terms_of_service) antes de publicar o projeto.

### Provedor HTTP opcional

```dotenv
JOB_API_URL=
JOB_API_TOKEN=
JOB_API_TOKEN_HEADER=Authorization
JOB_API_REQUIRES_TOKEN=false
JOB_API_TIMEOUT=10
```

O provedor envia somente `q` e `location`. Aceita uma lista JSON ou uma lista em `results`, `items`
ou `jobs`; APIs com contratos diferentes devem ganhar um adaptador próprio. URL e token vêm apenas
do ambiente e não ficam disponíveis para visitantes.

### Administrador e sessão

Gere o hash sem colocar a senha no histórico do terminal:

```powershell
python -m vagasscan gerar-hash-senha
```

Copie somente o hash retornado para `VAGASSCAN_ADMIN_PASSWORD_HASH`. Gere o segredo:

```powershell
python -m vagasscan gerar-segredo-sessao
```

Copie o valor para `VAGASSCAN_SESSION_SECRET`. O exemplo mantém ambos vazios. Sem hash, o login é
desabilitado; sem segredo, desenvolvimento usa uma sessão efêmera e também desabilita o login. Em
produção, segredo ausente impede a inicialização.

```dotenv
VAGASSCAN_ADMIN_USERNAME=admin
VAGASSCAN_ADMIN_PASSWORD_HASH=
VAGASSCAN_SESSION_SECRET=
VAGASSCAN_PUBLIC_DEMO=true
VAGASSCAN_COOKIE_SECURE=false
```

Use `VAGASSCAN_COOKIE_SECURE=true` com HTTPS. A sessão expira em oito horas, usa cookie HttpOnly e
SameSite=Lax. Logout e formulários de escrita exigem CSRF.

## Banco e migrações

Inicialize o banco principal sem abrir o menu:

```powershell
python -m vagasscan --somente-inicializar
```

`Database.initialize()` reconhece o schema legado, aplica migrações ordenadas e registra versões em
`schema_migrations`. Nenhuma migração apaga ou recria tabelas existentes. Vagas antigas recebem
defaults para salário, categoria, contrato e jornada.

## Executar a CLI

```powershell
python -m vagasscan
```

O menu oferece:

1. Adzuna — vagas reais;
2. demonstração local;
3. HTTP configurável.

Credenciais Adzuna ausentes mostram orientação e retornam ao menu. Cadastro manual, importação,
relatórios e demonstração continuam funcionando.

Carregue três vagas fictícias no banco separado:

```powershell
python -m vagasscan --carregar-demo
```

## Executar a web

Modo local pela configuração do `.env`:

```powershell
python -m vagasscan web
```

Acesse [http://127.0.0.1:8000](http://127.0.0.1:8000). Também funciona:

```powershell
python -m uvicorn vagasscan.web.app:app --reload --host 127.0.0.1 --port 8000
```

Em produção, não use reload. O health check é `GET /health` e retorna somente:

```json
{"status":"ok"}
```

### Área pública

Visitantes podem ver a landing page, buscar vagas em banco público separado, abrir detalhes e
analisar temporariamente uma descrição. Não podem consultar o banco principal, perfil real,
candidaturas, observações, relatórios ou organizador.

`VAGASSCAN_PUBLIC_DEMO=false` mantém landing e login, mas desabilita busca/análise públicas. O
limitador simples é por processo: cinco buscas/minuto, dez análises/minuto e dez cache misses Adzuna
por minuto no total.

### Área privada

Após login, o administrador acessa dashboard, busca no banco principal, vagas, status, candidaturas,
relatórios, perfil, reanálise e cadastro/importação. Não existe cadastro público de usuários.

O organizador web só aparece quando a flag e os dois caminhos do servidor estão configurados:

```dotenv
VAGASSCAN_ENABLE_FILE_ORGANIZER_WEB=false
VAGASSCAN_FILE_ORGANIZER_SOURCE=
VAGASSCAN_FILE_ORGANIZER_DESTINATION=
```

O navegador nunca envia caminhos. A página apenas simula e confirma o plano calculado no servidor.
Deixe a função desabilitada em hospedagem.

## Teste manual opcional da Adzuna

Os testes automatizados nunca chamam a API real. Para uma única consulta, sem cache ou gravação:

```powershell
python -m vagasscan testar-adzuna --termo python
```

O comando usa página 1, no máximo cinco resultados e mostra apenas título, empresa e localização.
Sem ambas as credenciais, nenhuma chamada é feita.

## Testes e qualidade

```powershell
python -m pytest --basetemp=data\pytest-temporario -rs
python -m ruff check .
python -m compileall -q vagasscan tests
python -m pip check
```

Fixtures usam bancos e perfis temporários. Sessões HTTP falsas validam endpoint, parâmetros,
paginação, conversão, cache, erros e proteção de segredos.

## Segurança

- SQL parametrizado e transações para vaga/análise e candidatura/status;
- senha com `hashlib.scrypt` versionado e comparação em tempo constante;
- Jinja2 com autoescape, URLs HTTP(S) validadas e CSP sem scripts inline;
- cookies HttpOnly, SameSite, Secure em produção, expiração e invalidação no logout;
- CSRF em formulários POST, rate limiting em memória e limites de tamanho;
- headers `nosniff`, Referrer-Policy, Permissions-Policy, frame protection e HSTS sob HTTPS;
- credenciais ausentes de HTML, JavaScript, health check, cache e mensagens de erro;
- banco, perfil, logs e documentos fora dos arquivos estáticos;
- organizador sem upload e sem caminhos fornecidos pelo navegador.

## Estrutura

```text
vagasscan/
├── providers/       # Adzuna, demonstração e HTTP genérico
├── services/        # busca, análise, persistência e perfil
├── repositories/    # SQL de vagas, candidaturas e cache
├── analyzers/       # palavras-chave e compatibilidade
├── web/             # FastAPI, rotas, templates, CSS e JS
├── file_organizer/  # simulação, movimento seguro e desfazer
├── database.py      # conexões e migrações
├── models.py        # modelos internos
└── main.py          # CLI e comandos
```

Leia também [Arquitetura](docs/ARQUITETURA.md), [Deploy](docs/DEPLOY.md),
[Integração com portfólio](docs/PORTFOLIO_INTEGRATION.md),
[Auditoria técnica](docs/AUDITORIA_TECNICA.md) e [Guia de estudo](GUIA_DE_ESTUDO.md).

## Limitações reais

- análise determinística não compreende perfeitamente contexto, negações ou requisitos implícitos;
- descrições de busca da Adzuna podem ser resumidas/truncadas pela própria fonte;
- filtro remoto é uma heurística local;
- rate limiting é em memória e pressupõe um processo;
- SQLite requer volume persistente e não é adequado a múltiplas instâncias concorrentes;
- cache pode mostrar resultado marcado com até 24 horas durante falha transitória;
- organizador continua dependente do sistema de arquivos local;
- publicação contínua deve confirmar licença, atribuição e limites vigentes da Adzuna.

O próximo passo de hospedagem está documentado, mas nenhum deploy ou DNS faz parte desta entrega.
