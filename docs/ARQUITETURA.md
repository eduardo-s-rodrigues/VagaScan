# Arquitetura do VagasScan

## Visão geral

O projeto usa camadas pequenas, sem framework web e sem ORM. A regra principal é: entrada conversa
com serviço; serviço coordena regras; repositório fala com SQLite. Provedores apenas obtêm e
convertem vagas.

```text
CLI / comando
    |
    v
VagaService -----> ProvedorVagas
    |                  |-- demonstração local
    |                  `-- HTTP configurável
    |-- AnalisadorPalavrasChave <--- keywords.json
    |-- CalculadoraCompatibilidade <--- profile.json
    `-- VagaRepository / CandidaturaRepository
                         |
                         v
                       SQLite
```

## Módulos e responsabilidades

| Módulo | Responsabilidade |
|---|---|
| `main.py` | interpreta argumentos, monta dependências, inicializa banco e abre CLI |
| `cli.py` | mostra menus, valida entrada, confirma arquivos e apresenta resultados |
| `config.py` | carrega `.env`, resolve `pathlib.Path` e configura logging |
| `models.py` | mantém dataclasses simples e a lista canônica de status |
| `database.py` | abre conexões, transações e cria schema/índices idempotentes |
| `repositories/` | contém SQL parametrizado de vagas, requisitos e candidaturas |
| `providers/` | define contrato de busca e adaptadores local/HTTP |
| `analyzers/` | extrai palavras-chave e calcula aderência explicável |
| `services/` | coordena busca, deduplicação, análise e persistência |
| `reports/` | agrega dados e exporta terminal, Markdown ou CSV |
| `file_organizer/` | classifica, simula, move sem sobrescrever e desfaz |
| `utils/` | normaliza texto e URL |

## Fluxo principal

### Busca

1. A CLI escolhe um `ProvedorVagas`.
2. O provedor devolve modelos `Vaga`; nenhuma persistência ocorre ali.
3. O serviço carrega perfil, extrai requisitos e calcula compatibilidade.
4. O repositório procura duplicata na ordem definida.
5. Vaga, nota e requisitos são gravados na mesma transação; falhas individuais são relatadas.

### Cadastro manual

O fluxo começa diretamente no passo 3. Assim, o programa não depende da internet para iniciar ou
entregar sua função principal.

### Candidatura

Uma candidatura referencia uma vaga por chave estrangeira. A vaga muda para
`candidatura_enviada`, e cada mudança de status cria uma linha imutável em `historico_status`.
Correções manuais continuam possíveis; estados finais apenas geram aviso na CLI.
Registro da candidatura, atualização da etapa, status da vaga e histórico participam da mesma
transação, evitando um funil parcialmente atualizado.

### Documentos

Primeiro é criado um `Movimentacao` para cada arquivo. A simulação não cria pastas. Depois de mostrar
todos os pares origem/destino, a CLI solicita confirmação em lote. Movimentos reais entram no
histórico. O desfazer valida todos os caminhos antes de começar para evitar uma reversão parcial
previsível. O diretório do projeto, links simbólicos e destinos ocupados depois da simulação são
rejeitados. Falhas durante o lote tentam rollback dos arquivos já movidos.

## Decisões técnicas

- **SQLite e SQL explícito:** menor instalação e bom valor didático; quatro tabelas não justificam
  ORM.
- **Dataclasses:** deixam o formato interno visível sem criar hierarquia complexa.
- **Configuração JSON:** perfil e vocabulário mudam sem alteração no código.
- **Interface abstrata de provedor:** um método separa dependência externa do caso de uso.
- **Provedor HTTP genérico:** não inventa endpoint nem prende o aluno a fornecedor; exige URL real.
- **Pontuação determinística:** a mesma entrada produz a mesma justificativa, sem custo de IA.
- **`pathlib`:** caminhos legíveis e portáveis entre Windows, Linux e macOS.
- **Logging em arquivo:** registra operações relevantes e preserva mensagens amigáveis no terminal.
- **Exportação defensiva:** não sobrescreve sem autorização, usa arquivo temporário e neutraliza
  fórmulas em CSV.

## Banco e integridade

`Database.initialize()` pode rodar várias vezes. Chaves estrangeiras são ativadas por conexão.
Índices únicos parciais protegem fonte + ID e link somente quando não vazios. A chave normalizada de
conteúdo é indexada, mas não é única, pois coincidências incertas podem ser mantidas após confirmação.

Transações confirmam (`commit`) ao concluir e revertem (`rollback`) ao ocorrer exceção. Valores de
usuário sempre entram por parâmetros. Os nomes de coluna dinâmicos dos relatórios passam por uma
lista fechada antes da interpolação. Conexões de consulta usam um context manager próprio porque o
`with` nativo do `sqlite3.Connection` controla transação, mas não fecha o arquivo.

## Fórmula de compatibilidade

```text
nota = técnica (0..55)
     + área (0 ou 15)
     + nível (0 ou 10)
     + local/remoto (0 ou 10)
     + experiência (0..5)
     + formação (0 ou 5)
     - penalidade de nível (0, 6 ou 12)
```

A parte técnica é `55 × pesos compatíveis / pesos encontrados`. Peso obrigatório é 2, normal é 1 e
desejável é 0,75. Conhecimentos iguais são consolidados; escolaridade e experiência ficam fora da
parcela técnica. Sem termos, usa 27,5 e exige conferência humana. Vaga plena perde 6 pontos e vaga
sênior/especialista perde 12. O valor final é limitado a 0–100. Essa simplicidade é intencional: o
estudante consegue defender cada decisão em entrevista.

## Como adicionar um provedor

1. Consulte a documentação oficial da fonte e confirme que o uso da API é permitido.
2. Crie um módulo em `vagasscan/providers/`.
3. Herde de `ProvedorVagas`, defina `nome` e implemente `buscar(termo, localizacao)`.
4. Converta a resposta para uma lista de `Vaga`; não grave no banco dentro do provedor.
5. Traduza timeout, limite, autenticação e resposta inválida para `ErroProvedor`.
6. Exporte a classe em `providers/__init__.py` e ofereça a escolha na CLI.
7. Escreva testes com sessão falsa; não faça chamadas reais na suíte.
8. Adicione somente variáveis necessárias ao `.env.example`, nunca chaves reais.

O cliente genérico valida o esquema HTTP/HTTPS, rejeita credenciais embutidas na URL, fecha a sessão
que criou e não inclui tokens ou a URL completa em mensagens de falha de rede.

Não é necessário alterar `VagaService`, analisadores, repositórios ou schema.

## Limites do MVP

O aplicativo é monousuário, local e síncrono. Não possui paginação genérica, agendamento, download
de anexos, autenticação, backup automático, interface gráfica, análise semântica avançada ou
automação de candidatura. A camada HTTP pressupõe que o serviço aceite `q` e `location`; contratos
diferentes exigem um adaptador próprio. Essas restrições mantêm o projeto seguro e compreensível.
Movimentos de arquivos não podem ser totalmente atômicos entre volumes; o programa usa validação
prévia, rollback de melhor esforço e registro de falha parcial. O histórico local não é assinado
criptograficamente. A integração HTTP foi validada com sessões controladas, não contra uma API real
sem configuração fornecida pelo usuário.
