# Integração do VagaScan com o portfólio

Use um card no repositório do portfólio; não altere nem incorpore o VagaScan por iframe.

## Texto sugerido

**VagaScan**

> Aplicação web em Python para buscar, analisar e acompanhar vagas de tecnologia, com integração à
> Adzuna, SQLite e análise de compatibilidade baseada em regras.

Botões:

- Abrir VagaScan;
- Ver no GitHub.

Abra o aplicativo em nova aba para manter navegação e autenticação isoladas.

## HTML de exemplo

```html
<article class="project-card">
  <h2>VagaScan</h2>
  <p>
    Aplicação web em Python para buscar, analisar e acompanhar vagas de tecnologia,
    com integração à Adzuna, SQLite e análise de compatibilidade baseada em regras.
  </p>
  <div class="project-actions">
    <a href="https://vagasscan.dominio.com.br"
       target="_blank" rel="noopener noreferrer">Abrir VagaScan</a>
    <a href="https://github.com/eduardo-s-rodrigues/VagaScan"
       target="_blank" rel="noopener noreferrer">Ver no GitHub</a>
  </div>
</article>
```

Substitua apenas o domínio genérico depois que a hospedagem e o HTTPS estiverem ativos. Não exponha
credenciais em JavaScript e não copie o banco ou `.env` para o repositório do portfólio.
