# Changelog

## Não publicado

### Adicionado

- confiança da análise baixa/média/alta, componentes explicáveis, fatores e aviso de truncamento;
- origem e confiança da modalidade, incluindo “Possivelmente remoto” e negações simples;
- busca com loading acessível, filtros preservados, erro recuperável e estado vazio útil;
- cards com iniciais, confiança e origem; detalhes reorganizados como análise principal;
- vagas salvas v2 com limite configurável, validação, filtro, ordenação, JSON e CSV;
- páginas Sobre, Como funciona, Privacidade, Termos e Contato;
- favicon, manifest, canonical, Open Graph, Twitter Card, robots, sitemap e imagem social local;
- migração 4 aditiva para metadados de modalidade e confiança;
- experiência pública responsiva com hero compacto, busca integrada, cards horizontais e painel de
  métricas do conjunto visível;
- rota “Vagas salvas” com armazenamento local versionado, limitado e sem vínculo com candidaturas;
- provedor oficial Adzuna com filtros, paginação, conversão defensiva e retry limitado;
- cache SQLite com expiração e fallback seguro;
- migrações versionadas e campos de salário, categoria, contrato e jornada;
- aplicação FastAPI/Jinja2 pública e privada;
- login administrativo scrypt, sessão, CSRF, rate limiting e headers de segurança;
- banco/perfil públicos isolados, dashboard, perfil web e organizador condicionado;
- comandos web, teste manual Adzuna, geração de hash e segredo;
- testes de integração, segurança, migração, cache e interface web;
- guias de deploy e integração com portfólio.

### Alterado

- parcela técnica é limitada quando há uma ou duas evidências, sem confundir nota e confiança;
- filtro de modalidade pode consultar até duas páginas extras com cache e parada antecipada;
- contadores públicos usam resultados recebidos/exibidos/já conhecidos, origem e quantidade analisada;
- mensagens públicas de provedor não expõem variáveis, caminhos ou detalhes de infraestrutura;
- rate limiting de busca agora é acionado somente em cache miss, com cooldown público, cotas
  horárias separadas e relógio injetável para testes;
- modalidade e ordenação públicas agora são filtros locais e não fragmentam o cache Adzuna;
- navegação pública e rodapé foram simplificados, mantendo o dashboard isolado nas rotas privadas;
- CLI agora oferece Adzuna, demonstração e HTTP configurável;
- serviço de vagas passou a compartilhar busca, cache, análise e persistência entre CLI e web;
- configuração e documentação foram ampliadas sem incluir valores secretos.

### Segurança

- `.env.*` é ignorado com exceção explícita para `.env.example`;
- credenciais não aparecem em cache, templates, health check ou erros;
- área pública usa banco e perfil separados;
- links externos são validados e abertos com isolamento da janela de origem.
