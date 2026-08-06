# Preparação para deploy do VagaScan

Este documento prepara uma futura publicação. Nenhum deploy ou DNS é executado pelo projeto.

## Domínio, subdomínio e hospedagem

- domínio: endereço principal, como `dominio.com.br`;
- subdomínio: nome abaixo dele, como `vagasscan.dominio.com.br`;
- hospedagem: servidor que executa Python e mantém os arquivos da aplicação.

O portfólio pode continuar no domínio principal enquanto o VagaScan roda em outra hospedagem. DNS
apenas conecta o subdomínio ao endereço fornecido por essa hospedagem.

## Exemplo genérico com Render

1. Crie um serviço web Python apontado para este repositório.
2. Use uma versão Python compatível e instale com `pip install .`.
3. Configure o comando de produção:

   ```sh
   uvicorn vagasscan.web.app:app --no-access-log --host 0.0.0.0 --port $PORT
   ```

4. Não adicione `--reload` e use um único worker enquanto SQLite/rate limiting local estiverem em
   uso.
5. Configure todas as variáveis pela área secreta da hospedagem; nunca envie `.env`.
6. Adicione um disco persistente e aponte os três bancos, perfil e logs para esse volume.
7. Configure o health check como `/health`.

`$PORT` é sintaxe do shell Linux da hospedagem. No Windows local, use `python -m vagasscan web` ou
`python -m uvicorn ... --port 8000`.

## DNS do subdomínio

Quando o provedor fornecer um hostname, crie um CNAME de `vagasscan` para esse destino. Se fornecer
IPs, use A para IPv4 e AAAA para IPv6. Não crie CNAME e A/AAAA conflitantes para o mesmo nome.

Depois, adicione `vagasscan.dominio.com.br` como domínio personalizado na hospedagem. Aguarde a
propagação e habilite o certificado HTTPS automático antes de ativar cookies Secure.

## Variáveis mínimas de produção

- bancos, perfil, keywords e log em volume persistente;
- credenciais Adzuna;
- username, hash scrypt e segredo de sessão fortes;
- `VAGASSCAN_ENV=production`;
- `VAGASSCAN_BASE_URL=https://vagasscan.dominio.com.br`;
- `VAGASSCAN_COOKIE_SECURE=true`;
- `VAGASSCAN_PUBLIC_DEMO` conforme o limite de API disponível;
- `VAGASSCAN_ENABLE_FILE_ORGANIZER_WEB=false`.

Revise a licença, atribuição visual e limites atuais da Adzuna antes da publicação. Não coloque
segredos em comando de inicialização, logs, templates ou variáveis públicas de frontend.

## SQLite, volume e backup

Hospedagens efêmeras descartam arquivos após restart/deploy. Sem volume persistente, vagas, cache,
perfil e candidaturas serão perdidos.

Faça backup com a aplicação parada ou usando a API de backup do SQLite. Copiar um `.db` durante uma
escrita pode produzir cópia inconsistente. Guarde backups fora do mesmo volume e teste restauração.

Monitore espaço, erros de bloqueio e tempo de resposta. Mantenha logs sem descrições completas,
senhas, tokens ou URLs preparadas da Adzuna.

## Quando migrar para PostgreSQL

Migre quando houver múltiplos workers/instâncias, escrita concorrente relevante, necessidade de alta
disponibilidade ou volume que torne o arquivo local inadequado. A migração exigirá um repository
compatível, ferramenta de schema própria, conexão por ambiente e rate limiting compartilhado
(Redis/gateway).

## Checklist antes de publicar

- testes e Ruff aprovados;
- `.env` ignorado e nenhum segredo rastreado;
- volume persistente montado e backup testado;
- segredo/hashes gerados fora do Git;
- HTTPS ativo e cookie Secure;
- debug/reload desligados;
- organizador web desabilitado;
- atribuição e `redirect_url` da Adzuna preservados;
- limites/licença da API confirmados;
- `/health` monitorado;
- domínio personalizado validado sem iframe.
