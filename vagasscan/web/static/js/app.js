const menuButton = document.querySelector('.menu-button');
const navigation = document.querySelector('#main-nav');

if (menuButton && navigation) {
  const closeNavigation = (returnFocus = false) => {
    menuButton.setAttribute('aria-expanded', 'false');
    navigation.classList.remove('open');
    if (returnFocus) menuButton.focus();
  };

  menuButton.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') === 'true';
    menuButton.setAttribute('aria-expanded', String(!open));
    navigation.classList.toggle('open', !open);
  });

  navigation.addEventListener('click', (event) => {
    if (event.target.closest('a')) closeNavigation();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menuButton.getAttribute('aria-expanded') === 'true') {
      closeNavigation(true);
    }
  });
}

document.querySelectorAll('[data-confirm]').forEach((button) => {
  button.addEventListener('click', (event) => {
    if (!window.confirm(button.dataset.confirm)) event.preventDefault();
  });
});

document.querySelectorAll('[data-suggestion-term]').forEach((button) => {
  button.addEventListener('click', () => {
    const container = button.closest('.container');
    const form = container?.querySelector('[data-public-search-form]');
    if (!form) return;
    const term = form.querySelector('[name="termo"]');
    const location = form.querySelector('[name="localizacao"]');
    const modality = form.querySelector('[name="modalidade"]');
    if (term) term.value = button.dataset.suggestionTerm || '';
    if (location && button.dataset.suggestionLocation !== undefined) {
      location.value = button.dataset.suggestionLocation;
    }
    if (modality && button.dataset.suggestionModality !== undefined) {
      modality.value = button.dataset.suggestionModality;
    }
    term?.focus();
  });
});

document.querySelectorAll('[data-sort-select]').forEach((select) => {
  select.addEventListener('change', () => select.form?.requestSubmit());
});

function setFormLoading(form, loading, message) {
  const submit = form.querySelector('[data-search-submit], [data-loading-submit]');
  if (!submit) return;
  const label = submit.querySelector('[data-submit-label]');
  const spinner = submit.querySelector('.loading-spinner');
  const status = form.querySelector('[data-search-status], [data-form-status]');
  const original = submit.dataset.originalLabel || label?.textContent || submit.textContent;
  submit.dataset.originalLabel = original;
  form.setAttribute('aria-busy', String(loading));
  submit.disabled = loading;
  if (label) label.textContent = loading ? message : original;
  else submit.textContent = loading ? message : original;
  if (spinner) spinner.hidden = !loading;
  if (status) status.textContent = loading ? message : '';
}

document.querySelectorAll('[data-public-search-form]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (form.dataset.submitting === 'true') {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = 'true';
    setFormLoading(form, true, 'Buscando vagas...');
  });
});

document.querySelectorAll('[data-loading-form]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (form.dataset.submitting === 'true') {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = 'true';
    const submit = form.querySelector('[data-loading-submit]');
    setFormLoading(form, true, submit?.dataset.loadingText || 'Processando...');
  });
});

window.addEventListener('pageshow', () => {
  document.querySelectorAll('[data-public-search-form], [data-loading-form]').forEach((form) => {
    if (document.querySelector('[data-rate-limit]') && form.matches('[data-public-search-form]')) {
      return;
    }
    form.dataset.submitting = 'false';
    setFormLoading(form, false, '');
  });
});

const RECENT_SEARCH_KEY = 'vagasscan.lastSearchUrl';
const successfulResults = document.querySelector('[data-store-search-url]');
if (successfulResults) {
  try {
    sessionStorage.setItem(RECENT_SEARCH_KEY, `${window.location.pathname}${window.location.search}`);
  } catch (_) {
    // A busca continua funcional quando o armazenamento de sessão não está disponível.
  }
}

function recentSearchUrl() {
  try {
    const recent = sessionStorage.getItem(RECENT_SEARCH_KEY) || '';
    return recent.startsWith('/buscar?') ? recent : '';
  } catch (_) {
    return '';
  }
}

document.querySelectorAll('[data-recent-search], [data-back-results]').forEach((link) => {
  const recent = recentSearchUrl();
  if (recent) {
    link.href = recent;
    link.hidden = false;
  }
});

const rateLimitAlert = document.querySelector('[data-rate-limit]');
if (rateLimitAlert) {
  const submit = document.querySelector('[data-search-submit]');
  const label = submit?.querySelector('[data-submit-label]');
  let remaining = Math.max(1, Number(rateLimitAlert.dataset.rateLimit) || 1);
  const originalLabel = label?.textContent || submit?.textContent || 'Buscar vagas';
  const updateCountdown = () => {
    if (!submit) return;
    if (remaining > 0) {
      submit.disabled = true;
      if (label) label.textContent = `Tente novamente em ${remaining}s`;
      else submit.textContent = `Tente novamente em ${remaining}s`;
      remaining -= 1;
    } else {
      submit.disabled = false;
      if (label) label.textContent = originalLabel;
      else submit.textContent = originalLabel;
      remaining = -1;
    }
  };
  updateCountdown();
  const timer = window.setInterval(() => {
    updateCountdown();
    if (remaining < 0) window.clearInterval(timer);
  }, 1000);
}

document.querySelectorAll('[data-adjust-search]').forEach((button) => {
  button.addEventListener('click', () => {
    const form = document.querySelector('[data-public-search-form]');
    if (!form) return;
    if (button.dataset.adjustSearch === 'remove-junior') {
      const term = form.querySelector('[name="termo"]');
      if (term) term.value = term.value.replace(/\bj[uú]nior\b/gi, '').replace(/\s+/g, ' ').trim();
    }
    if (button.dataset.adjustSearch === 'all-modalities') {
      const modality = form.querySelector('[name="modalidade"]');
      if (modality) modality.value = '';
    }
    form.querySelector('[name="pagina"]')?.remove();
    form.requestSubmit();
  });
});

const SAVED_JOBS_KEY = 'vagasscan.savedJobs.v2';
const LEGACY_SAVED_JOBS_KEY = 'vagasscan.savedJobs.v1';
const MAX_SAVED_JOBS = Math.min(500, Math.max(1, Number(document.body.dataset.savedJobsLimit) || 200));
const MAX_IMPORT_BYTES = 1_000_000;

function safeText(value, maximum) {
  return String(value || '').trim().slice(0, maximum);
}

function containsMarkup(value) {
  return /[<>]|javascript\s*:/i.test(String(value || ''));
}

function safeExternalUrl(value) {
  if (!value) return '';
  try {
    const url = new URL(String(value));
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch (_) {
    return '';
  }
}

function safeDetailUrl(value) {
  const text = String(value || '');
  return /^\/vagas\/\d+$/.test(text) ? text : '';
}

function normalizeSavedJob(value) {
  if (!value || typeof value !== 'object' || ![1, 2].includes(Number(value.version))) return null;
  const textualValues = [value.id, value.title, value.company, value.location, value.modality];
  if (textualValues.some(containsMarkup)) return null;
  const id = safeText(value.id, 250);
  const title = safeText(value.title, 200);
  if (!id || !title) return null;
  const score = Math.min(100, Math.max(0, Number(value.score) || 0));
  const savedAt = Number.isNaN(Date.parse(value.savedAt)) ? '' : safeText(value.savedAt, 40);
  const publishedAt = Number.isNaN(Date.parse(value.publishedAt)) ? '' : safeText(value.publishedAt, 40);
  const confidence = ['baixa', 'média', 'alta'].includes(value.confidence) ? value.confidence : 'baixa';
  return {
    version: 2,
    id,
    title,
    company: safeText(value.company, 200) || 'Não informada',
    location: safeText(value.location, 200) || 'Não informada',
    modality: safeText(value.modality, 100) || 'não informada',
    modalityOrigin: safeText(value.modalityOrigin, 30) || 'não informada',
    score,
    confidence,
    source: safeText(value.source, 40) || 'VagaScan',
    publishedAt,
    originalUrl: safeExternalUrl(value.originalUrl),
    detailUrl: safeDetailUrl(value.detailUrl),
    savedAt,
  };
}

function uniqueJobs(values) {
  const unique = new Map();
  values.forEach((value) => {
    const job = normalizeSavedJob(value);
    if (job && !unique.has(job.id)) unique.set(job.id, job);
  });
  return [...unique.values()].slice(0, MAX_SAVED_JOBS);
}

function readSavedJobs() {
  try {
    const raw = localStorage.getItem(SAVED_JOBS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (!parsed || Number(parsed.version) !== 2 || !Array.isArray(parsed.items)) {
        throw new Error('invalid saved jobs schema');
      }
      return uniqueJobs(parsed.items);
    }
    const legacyRaw = localStorage.getItem(LEGACY_SAVED_JOBS_KEY);
    if (!legacyRaw) return [];
    const legacy = JSON.parse(legacyRaw);
    if (!Array.isArray(legacy)) throw new Error('invalid legacy schema');
    const migrated = uniqueJobs(legacy);
    writeSavedJobs(migrated);
    localStorage.removeItem(LEGACY_SAVED_JOBS_KEY);
    return migrated;
  } catch (_) {
    try { localStorage.removeItem(SAVED_JOBS_KEY); } catch (_) { /* armazenamento indisponível */ }
    return [];
  }
}

function writeSavedJobs(jobs) {
  try {
    localStorage.setItem(SAVED_JOBS_KEY, JSON.stringify({ version: 2, items: uniqueJobs(jobs) }));
    return true;
  } catch (_) {
    return false;
  }
}

function savedFeedback(message, isError = false) {
  const feedback = document.querySelector('[data-saved-feedback]');
  const globalStatus = document.querySelector('[data-global-status]');
  if (feedback) {
    feedback.textContent = message;
    feedback.hidden = !message;
    feedback.classList.toggle('alert-error', isError);
  }
  if (globalStatus) globalStatus.textContent = message;
}

function refreshSaveButtons() {
  const savedIds = new Set(readSavedJobs().map((job) => job.id));
  document.querySelectorAll('[data-save-job]').forEach((button) => {
    try {
      const payload = normalizeSavedJob(JSON.parse(button.dataset.saveJob));
      const saved = payload && savedIds.has(payload.id);
      button.textContent = saved ? 'Vaga salva' : 'Salvar vaga';
      button.setAttribute('aria-pressed', String(Boolean(saved)));
      button.classList.toggle('is-saved', Boolean(saved));
    } catch (_) {
      button.disabled = true;
    }
  });
}

document.querySelectorAll('[data-save-job]').forEach((button) => {
  button.addEventListener('click', () => {
    let payload;
    try { payload = normalizeSavedJob(JSON.parse(button.dataset.saveJob)); } catch (_) { payload = null; }
    if (!payload) {
      savedFeedback('Esta vaga não pôde ser salva.', true);
      return;
    }
    const jobs = readSavedJobs();
    const existing = jobs.findIndex((job) => job.id === payload.id);
    if (existing >= 0) {
      jobs.splice(existing, 1);
      savedFeedback('Vaga removida dos salvos.');
    } else {
      if (jobs.length >= MAX_SAVED_JOBS) {
        savedFeedback(`O limite de ${MAX_SAVED_JOBS} vagas salvas foi atingido.`, true);
        return;
      }
      payload.savedAt = new Date().toISOString();
      jobs.unshift(payload);
      savedFeedback('Vaga salva neste navegador.');
    }
    if (!writeSavedJobs(jobs)) savedFeedback('O navegador não permitiu salvar a vaga.', true);
    refreshSaveButtons();
  });
});

function companyInitials(company) {
  const parts = String(company || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'VS';
  return (parts.length === 1 ? parts[0].slice(0, 2) : `${parts[0][0]}${parts[1][0]}`).toUpperCase();
}

function filteredSavedJobs() {
  const modality = document.querySelector('[data-saved-modality]')?.value || '';
  const sort = document.querySelector('[data-saved-sort]')?.value || 'date-desc';
  const jobs = readSavedJobs().filter((job) => {
    if (!modality) return true;
    const normalized = job.modality.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    return normalized === modality.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  });
  jobs.sort((a, b) => {
    if (sort === 'score-desc') return b.score - a.score;
    if (sort === 'score-asc') return a.score - b.score;
    const difference = Date.parse(a.savedAt || 0) - Date.parse(b.savedAt || 0);
    return sort === 'date-asc' ? difference : -difference;
  });
  return jobs;
}

function renderSavedJobs() {
  const list = document.querySelector('[data-saved-jobs-list]');
  const template = document.querySelector('#saved-job-template');
  const empty = document.querySelector('[data-saved-empty]');
  const filterEmpty = document.querySelector('[data-saved-filter-empty]');
  const count = document.querySelector('[data-saved-count]');
  if (!list || !template) return;
  const allJobs = readSavedJobs();
  const jobs = filteredSavedJobs();
  list.replaceChildren();
  jobs.forEach((job) => {
    const fragment = template.content.cloneNode(true);
    const card = fragment.querySelector('.saved-job-card');
    card.dataset.savedId = job.id;
    fragment.querySelector('.company-avatar').textContent = companyInitials(job.company);
    fragment.querySelector('h3').textContent = job.title;
    fragment.querySelector('.company').textContent = job.company;
    fragment.querySelector('.metadata').textContent = `${job.location} • ${job.modality}`;
    fragment.querySelector('.saved-source').textContent = `Fonte: ${job.source}`;
    const confidence = fragment.querySelector('.saved-confidence');
    confidence.textContent = `Confiança da análise: ${job.confidence}`;
    confidence.classList.add(`confidence-${job.confidence}`);
    const score = fragment.querySelector('.saved-score');
    score.setAttribute('aria-label', `Compatibilidade ${Math.round(job.score)} por cento; confiança ${job.confidence}`);
    fragment.querySelector('.saved-score strong').textContent = `${Math.round(job.score)}%`;
    fragment.querySelector('.saved-date').textContent = job.savedAt
      ? `Salva em ${new Date(job.savedAt).toLocaleDateString('pt-BR')}`
      : 'Salva neste navegador';
    const detail = fragment.querySelector('.saved-detail');
    detail.href = job.detailUrl || '/buscar';
    if (!job.detailUrl) detail.hidden = true;
    const original = fragment.querySelector('.saved-original');
    original.href = job.originalUrl || '/buscar';
    if (!job.originalUrl) original.hidden = true;
    fragment.querySelector('.saved-remove').dataset.savedId = job.id;
    list.appendChild(fragment);
  });
  if (empty) empty.hidden = allJobs.length > 0;
  if (filterEmpty) filterEmpty.hidden = allJobs.length === 0 || jobs.length > 0;
  if (count) {
    const visible = jobs.length === allJobs.length ? '' : ` (${jobs.length} exibidas)`;
    count.textContent = `${allJobs.length} ${allJobs.length === 1 ? 'vaga' : 'vagas'}${visible}`;
  }
}

document.addEventListener('click', (event) => {
  if (!(event.target instanceof Element)) return;
  const remove = event.target.closest('.saved-remove[data-saved-id]');
  if (!remove) return;
  const jobs = readSavedJobs().filter((job) => job.id !== remove.dataset.savedId);
  writeSavedJobs(jobs);
  savedFeedback('Vaga removida dos salvos.');
  renderSavedJobs();
  refreshSaveButtons();
});

document.querySelectorAll('[data-saved-sort], [data-saved-modality]').forEach((control) => {
  control.addEventListener('change', renderSavedJobs);
});

function downloadFile(name, contents, type) {
  const blob = new Blob([contents], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

document.querySelector('[data-export-json]')?.addEventListener('click', () => {
  const payload = { version: 2, exportedAt: new Date().toISOString(), items: readSavedJobs() };
  downloadFile('vagasscan-vagas-salvas.json', JSON.stringify(payload, null, 2), 'application/json');
  savedFeedback('Arquivo JSON exportado.');
});

function safeCsvCell(value) {
  let text = String(value ?? '');
  if (/^[=+\-@]/.test(text.trimStart())) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

document.querySelector('[data-export-csv]')?.addEventListener('click', () => {
  const fields = ['title', 'company', 'location', 'modality', 'score', 'confidence', 'source', 'savedAt', 'originalUrl'];
  const rows = [fields.join(';'), ...readSavedJobs().map((job) => fields.map((field) => safeCsvCell(job[field])).join(';'))];
  downloadFile('vagasscan-vagas-salvas.csv', `\uFEFF${rows.join('\r\n')}`, 'text/csv;charset=utf-8');
  savedFeedback('Arquivo CSV exportado.');
});

document.querySelector('[data-import-json]')?.addEventListener('change', async (event) => {
  const input = event.target;
  const file = input.files?.[0];
  if (!file) return;
  try {
    if (file.size > MAX_IMPORT_BYTES) throw new Error('O arquivo excede 1 MB.');
    const parsed = JSON.parse(await file.text());
    const items = Array.isArray(parsed) ? parsed : parsed?.version === 2 ? parsed.items : null;
    if (!Array.isArray(items)) throw new Error('O arquivo não usa o schema esperado.');
    const imported = uniqueJobs(items);
    if (items.length && !imported.length) throw new Error('Nenhuma vaga válida foi encontrada.');
    const combined = uniqueJobs([...imported, ...readSavedJobs()]);
    if (!writeSavedJobs(combined)) throw new Error('O navegador bloqueou o armazenamento.');
    renderSavedJobs();
    refreshSaveButtons();
    savedFeedback(`${imported.length} vaga(s) válida(s) importada(s); duplicatas foram ignoradas.`);
  } catch (error) {
    savedFeedback(`Não foi possível importar: ${error.message}`, true);
  } finally {
    input.value = '';
  }
});

document.querySelector('[data-remove-all]')?.addEventListener('click', () => {
  const jobs = readSavedJobs();
  if (!jobs.length) return;
  if (!window.confirm('Remover todas as vagas salvas deste navegador?')) return;
  writeSavedJobs([]);
  renderSavedJobs();
  refreshSaveButtons();
  savedFeedback('Todas as vagas salvas foram removidas.');
});

window.addEventListener('storage', (event) => {
  if ([SAVED_JOBS_KEY, LEGACY_SAVED_JOBS_KEY].includes(event.key)) {
    renderSavedJobs();
    refreshSaveButtons();
  }
});

refreshSaveButtons();
renderSavedJobs();
