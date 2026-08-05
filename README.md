# VagasScan

VagasScan é um MVP em Python para encontrar, analisar e acompanhar vagas de tecnologia para
profissionais iniciantes. Ele funciona no terminal, salva os dados em SQLite e continua útil
mesmo sem API externa: vagas podem ser cadastradas manualmente, importadas por uma descrição
colada ou carregadas do provedor local de demonstração.

> A compatibilidade é uma estimativa baseada em palavras-chave. Ela ajuda a priorizar a leitura e
> nunca deve ser interpretada como garantia de contratação.

## Funcionalidades

- busca por provedor local ou por uma API HTTP configurada pelo usuário;
- cadastro manual e importação de descrição;
- deduplicação por identificador externo, link e conteúdo normalizado;
- extração editável de tecnologias e requisitos;
- compatibilidade explicada, de 0 a 100;
- perfil editável em JSON;
- funil de status, candidatura, próxima ação e histórico;
- filtros por status, área, local, fonte e compatibilidade;
- relatórios no terminal, Markdown e CSV;
- organização de documentos com simulação, confirmação, nomes não conflitantes e desfazer;
- logs em arquivo, SQL parametrizado e testes automatizados.

O projeto não raspa LinkedIn/Indeed, não envia candidaturas e não usa IA paga.

## Exemplo no terminal

```text
=== VagasScan ===
1. Buscar vagas
2. Cadastrar vaga manualmente
...
14. Exportar relatório
15. Sair

Compatibilidade aproximada: 87.5%
A pontuação é uma estimativa e não garante aprovação.
Pontos compatíveis: Python, SQL, Git, JSON
Conhecimentos ausentes: Docker
Confirmar manualmente: Experiência de 1 ano(s)
Justificativa: Técnica 47.5/55; área compatível; nível compatível; ...
```

Ao organizar documentos, nada é movido antes da confirmação:

```text
Curriculos: C:\Entrada\curriculo.pdf -> C:\Carreira\Curriculos\curriculo.pdf
Testes_Tecnicos: C:\Entrada\desafio.zip -> C:\Carreira\Testes_Tecnicos\desafio.zip
Sair do modo de simulação e mover todos os arquivos? [s/N]:
```

## Instalação no Windows

Requer Python 3.12 ou mais recente. No PowerShell, a partir da pasta do projeto:

```powershell
python --version
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

O `Set-ExecutionPolicy` vale apenas para a janela atual e pode ser omitido quando a política já
permite ativar o ambiente.

## Configuração

O `.env` é opcional. O arquivo real é ignorado pelo Git; nunca publique tokens.

```dotenv
VAGASSCAN_DATABASE=data/vagasscan.db
VAGASSCAN_DEMO_DATABASE=data/vagasscan_demo.db
VAGASSCAN_PROFILE=data/profile.json
VAGASSCAN_KEYWORDS=data/keywords.json
VAGASSCAN_LOG=logs/vagasscan.log
JOB_API_URL=
JOB_API_TOKEN=
JOB_API_TOKEN_HEADER=Authorization
JOB_API_REQUIRES_TOKEN=false
JOB_API_TIMEOUT=10
```

Sem `JOB_API_URL`, somente o provedor HTTP fica indisponível. Cadastro, análise, relatórios e o
provedor de demonstração continuam funcionando.

### Contrato do provedor HTTP configurável

O projeto não contém endpoint inventado. `JOB_API_URL` deve ser a URL real documentada pelo serviço
escolhido. A busca envia `GET` com os parâmetros `q` e `location`. O retorno pode ser uma lista JSON
ou um objeto cuja lista esteja em `results`, `items` ou `jobs`.

Cada item precisa de `title`/`titulo` e `description`/`descricao`. Também são aceitos `id`,
`company`/`empresa`, `location`/`localizacao`, `url`/`link`, `level`/`nivel`,
`modality`/`modalidade` e `created`/`published_at`/`data_publicacao`. Adapte o método `_converter`
ao contrato oficial de outro serviço. HTTP 429, timeout, erro HTTP, JSON inválido e credencial
obrigatória ausente viram mensagens compreensíveis na CLI.

A URL precisa usar HTTP/HTTPS e não pode conter `usuario:senha@host`. Tokens são enviados somente no
cabeçalho configurado e não são incluídos nas mensagens ou logs. A sessão HTTP criada internamente é
fechada após cada busca.

## Inicialização e execução

```powershell
# Cria as tabelas com segurança e encerra
python -m vagasscan --somente-inicializar

# Abre o menu principal
python -m vagasscan

# Alternativa depois da instalação editável
vagasscan
```

Para carregar os três registros fictícios em um banco separado:

```powershell
python -m vagasscan --carregar-demo
```

Esse comando usa `data/vagasscan_demo.db`; não mistura demonstração com `data/vagasscan.db`.
Executá-lo novamente apenas informa as duplicatas.

Para abrir a CLI apontando temporariamente para os dados fictícios:

```powershell
$env:VAGASSCAN_DATABASE = "data\vagasscan_demo.db"
python -m vagasscan
$env:VAGASSCAN_DATABASE = ""
```

A opção “Demonstração local” da busca também grava somente no caminho configurado por
`VAGASSCAN_DEMO_DATABASE`.

## Testes e qualidade

```powershell
python -m pytest
python -m ruff check .
```

Se o Windows negar acesso à pasta temporária global do pytest, use uma pasta isolada:

```powershell
python -m pytest --basetemp=data\pytest-temporario
```

Os testes usam bancos e pastas temporários; não tocam em documentos pessoais nem no banco real.

Para colar uma descrição com várias linhas na CLI, cole o texto e depois digite `FIM` em uma linha
separada. Digitar `0` como primeira linha cancela a operação.

## Estrutura

```text
vagasscan/
├── main.py                 # inicialização e comandos
├── cli.py                  # menu e validação de entradas
├── config.py               # .env, caminhos e logging
├── database.py             # conexão e schema SQLite
├── models.py               # dataclasses e status
├── analyzers/              # extração e compatibilidade
├── providers/              # demonstração e HTTP configurável
├── repositories/           # SQL de vagas e candidaturas
├── services/               # casos de uso
├── reports/                # consultas e exportação
├── file_organizer/         # plano, movimento e desfazer
└── utils/                  # normalização de texto e URL
tests/                      # testes automatizados
data/                       # perfil, palavras-chave e bancos locais
logs/                       # log de execução
exports/                    # relatórios gerados
docs/                       # documentação técnica
```

Leia também [GUIA_DE_ESTUDO.md](GUIA_DE_ESTUDO.md) e
[ARQUITETURA.md](docs/ARQUITETURA.md). A última revisão está registrada em
[AUDITORIA_TECNICA.md](docs/AUDITORIA_TECNICA.md).

## Como usar

1. Ajuste `data/profile.json` sem alterar código.
2. Execute `python -m vagasscan`.
3. Comece pelo provedor de demonstração ou cole uma descrição real autorizada.
4. Confira a análise e confirme manualmente requisitos ambíguos.
5. Marque vagas interessantes, registre candidaturas e próximas ações.
6. Consulte as opções 9, 10, 11 e 14 para priorização e relatórios.

## Segurança

- SQL recebe valores por parâmetros `?`; entradas não são concatenadas às consultas de dados.
- `.env`, bancos, logs e exportações são ignorados pelo Git.
- O organizador começa simulado, mostra origem/destino, pede confirmação em lote, não exclui e
  nunca sobrescreve silenciosamente.
- Pastas internas do VagasScan e caminhos com links simbólicos são rejeitados. Se um lote falhar no
  meio, os movimentos concluídos são revertidos; uma falha parcial fica marcada no histórico.
- O histórico em `data/movimentacoes.json` permite desfazer o último lote quando os caminhos estão
  livres.
- A API é somente leitura e não automatiza candidatura.
- Exportações não sobrescrevem por padrão; a CLI só habilita isso após confirmação. O CSV neutraliza
  textos que poderiam ser interpretados como fórmulas pelo Excel.
- Vaga e requisitos são gravados na mesma transação; candidatura, etapa e status também são
  sincronizados atomicamente. Conexões de leitura e escrita são fechadas explicitamente.

## Compatibilidade auditada

A nota continua limitada a 0–100 e é determinística. A parcela técnica vale 55 pontos, área 15,
nível 10, localização/modalidade 10, experiência 5 e formação 5. Requisito obrigatório pesa 2,
normal pesa 1 e desejável pesa 0,75. Escolaridade e experiência não são contadas novamente na
parcela técnica. Conhecimentos repetidos são consolidados.

Vagas de nível pleno recebem penalidade de 6 pontos e vagas sênior/especialista, 12 pontos. A nota
não é zerada automaticamente e a justificativa mostra a penalidade. Menções negativas simples, como
“Python não é necessário”, não viram requisitos.

Datas e horários internos criados pelo SQLite usam UTC; datas civis de candidatura usam
`AAAA-MM-DD` e são validadas antes da gravação.

## Limitações reais do MVP

- O analisador usa regras: não compreende perfeitamente negação, contexto ou requisitos implícitos.
- O formato HTTP é genérico; uma API concreta pode exigir paginação, parâmetros ou mapeamento.
- Não há atualização automática, agendador, interface web, autenticação ou sincronização em nuvem.
- A edição guiada do perfil adiciona itens; remoções e alterações completas são feitas no JSON.
- O desfazer cobre o último lote e falha com segurança se a origem estiver ocupada ou o arquivo
  movido não existir.
- Datas são armazenadas como ISO 8601; não há cálculo de feriados ou fuso em lembretes.
- Movimentações entre discos/volumes não são transações do sistema operacional. O rollback é de
  melhor esforço e uma falha não reversível fica registrada para correção manual.
- O histórico JSON possui validação estrutural e escrita atômica, mas não assinatura criptográfica;
  um usuário com acesso ao disco ainda pode adulterá-lo.
- Timeout, HTTP e JSON inválido foram testados com respostas controladas. Nenhuma API real foi
  chamada porque não há endpoint ou credencial configurados.

## Roadmap

- adaptadores para APIs públicas escolhidas a partir de documentação oficial;
- paginação e cache de buscas;
- edição completa de vaga e perfil pela CLI;
- reanálise em lote após alteração do perfil;
- notificações locais opcionais;
- interface web somente após estabilizar domínio e testes.

## Solução de problemas

### `python` não é reconhecido

Instale Python 3.12+ pelo site oficial ou Microsoft Store, marque a opção para adicionar Python ao
`PATH` e abra um novo PowerShell. No Windows, tente também `py --version` e substitua `python` por
`py` nos comandos.

### O ambiente virtual não está ativado

O prompt normalmente começa com `(.venv)`. Ative com:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### `ModuleNotFoundError`

Confirme que o ambiente está ativo e reinstale a partir da raiz:

```powershell
python -m pip install -e ".[dev]"
python -m vagasscan --somente-inicializar
```

### Banco bloqueado

Feche outras instâncias do VagasScan e programas que estejam inspecionando o `.db`. O aplicativo
aguarda até cinco segundos antes de informar o bloqueio. Não copie ou sincronize o banco enquanto o
programa estiver escrevendo.

### Credenciais ausentes

Isso desativa apenas o provedor HTTP. Configure `JOB_API_URL`, `JOB_API_TOKEN` e
`JOB_API_REQUIRES_TOKEN=true` conforme a documentação oficial da fonte, ou continue usando cadastro
manual/importação. Não coloque o token no README nem em `JOB_API_URL`.

### API indisponível, timeout ou HTTP 429

A CLI informa que a fonte não pôde ser consultada e volta ao menu. Aguarde, confira internet/URL e
limites da fonte. Os dados locais continuam disponíveis; nenhuma vaga parcial é salva.

### Acentuação incorreta no terminal

O projeto lê e grava UTF-8. No Windows Terminal moderno isso funciona por padrão. No PowerShell
legado, execute antes da aplicação:

```powershell
chcp 65001
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
python -m vagasscan
```
