# Arquitetura do VagaScan

## Visão geral

O VagaScan continua sendo uma única aplicação Python. CLI e FastAPI são duas interfaces para a
mesma camada de serviços; não existem backends duplicados.

```text
CLI                         FastAPI + Jinja2
 |                                |
 `---------- AppContext ----------'
                |
       VagaService / PerfilService
        |        |           |
  provedores  analisadores  repositories
        |                    |
 Adzuna/demo/HTTP       SQLite + migrações
```

`bootstrap.criar_contexto()` monta banco, repositories, analisadores, cache, relatórios e serviços.
O contexto privado usa banco/perfil reais; o público usa arquivos separados e sanitizados.

## Camadas

| Camada | Responsabilidade |
|---|---|
| `providers/` | obter e converter vagas sem persistir |
| `services/` | coordenar cache, análise, deduplicação, persistência e perfil |
| `repositories/` | executar SQL parametrizado e devolver estruturas simples |
| `analyzers/` | extrair requisitos e calcular compatibilidade determinística |
| `web/routes/` | validar entrada, autorizar e apresentar casos de uso |
| `cli.py` | interação de terminal sobre os mesmos serviços |
| `database.py` | conexões, transações, índices e migrações |

## Contrato de busca

`ConsultaVagas` representa termo, localização, página, quantidade, remoto, contrato, jornada,
ordenação, distância e país. `ResultadoBusca` devolve vagas, total aproximado, página, estado do
cache e erros seguros.

`ProvedorVagas.buscar(termo, localizacao)` foi preservado. `consultar(ConsultaVagas)` oferece o
contrato rico; a implementação padrão mantém provedores antigos compatíveis.

### Adzuna

`ProvedorAdzuna` usa o endpoint oficial com país e página no caminho. Credenciais seguem somente em
`params`, nunca em headers ou logs. Página, país e valores enumerados são validados antes da rede.

O provedor converte objetos aninhados, preserva `redirect_url`, aceita campos ausentes e classifica
falhas. Uma repetição curta é permitida para timeout, conexão ou 5xx. HTTP 429 não é repetido.

O filtro remoto é posterior à resposta porque a API oficial não oferece parâmetro equivalente. O
total aproximado continua sendo o total informado pela fonte antes da heurística local.

### Cache

`CacheBuscaRepository` cria uma chave SHA-256 de JSON canônico contendo apenas consulta e provedor.
O resultado normalizado é salvo em `cache_buscas`; app ID e chave não fazem parte do modelo de
consulta e não podem entrar no cache.

O serviço consulta cache válido antes da rede. Após falha transitória ou limite, pode usar um cache
expirado criado há no máximo 24 horas, marcando `veio_cache` e `cache_desatualizado`.

## Fluxos

### Busca pública

1. FastAPI valida limites e rate limiting.
2. O provedor devolve vagas, possivelmente via cache.
3. `VagaService` analisa com `profile_public.json`.
4. Vagas/requisitos são deduplicados e salvos em `vagasscan_public.db`.
5. O template recebe somente objetos públicos e metadados seguros.

O banco principal não participa desse fluxo.

### Busca privada/CLI

O fluxo é equivalente, mas usa `profile.json` e o banco principal. A demonstração da CLI continua
usando seu banco fictício próprio.

### Análise temporária

`analisar_temporaria()` extrai requisitos e calcula a nota sem chamar repository. O modo privado só
persiste quando o administrador escolhe explicitamente “Salvar como vaga”.

### Candidatura

Registro ou alteração de etapa ocorre em transação e sincroniza o status da vaga com histórico. A
área pública não possui acesso ao repository de candidaturas.

### Perfil

`PerfilService` valida listas, textos e anos, remove duplicatas, cria backup datado e substitui o
JSON por arquivo temporário. Reanálise é uma ação POST protegida, separada do salvamento.

## Banco e migrações

`schema_migrations` registra versões:

1. schema original de vagas, requisitos, candidaturas e histórico;
2. salário, categoria, contrato e jornada;
3. cache de buscas e índice por provedor/expiração.

Um banco anterior sem controle de versão é reconhecido como versão 1 e migrado. Colunas são
adicionadas apenas quando ausentes. Migrações e registro da versão participam da mesma transação.
`PRAGMA optimize` atualiza informações do planejador após inicialização.

## Web e segurança

FastAPI serve HTML Jinja2 e arquivos locais. `SessionMiddleware` assina a sessão; ela guarda apenas
administrador e token CSRF. Senhas usam scrypt; segredos permanecem no ambiente.

Todas as decisões de autorização são server-side. Rotas `/dashboard` consultam o contexto privado;
rotas públicas recebem apenas o contexto público. Jinja aplica autoescape e links externos passam
por validação HTTP(S).

A CSP permite apenas recursos locais, bloqueia objetos e framing. Headers complementares reduzem
riscos de MIME sniffing, referrer, permissões e clickjacking. Limites em memória reduzem abuso do
MVP, mas não substituem Redis ou gateway em múltiplas instâncias.

O organizador web só funciona com flag e caminhos definidos no servidor. O navegador nunca escolhe
caminhos, e a implementação existente continua bloqueando projeto, symlinks, destinos ocupados e
falhas parciais.

## Decisões e limites

- SQL explícito e dataclasses preservam o valor didático do projeto.
- FastAPI usa funções síncronas de domínio com conexões SQLite curtas por operação.
- Não há ORM, SPA, cadastro público, upload, fila, worker ou IA paga.
- Um processo Uvicorn é a configuração suportada do MVP.
- PostgreSQL e rate limiting compartilhado são necessários para escala horizontal.
