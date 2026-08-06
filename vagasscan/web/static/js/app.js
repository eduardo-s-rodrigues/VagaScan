const menuButton = document.querySelector('.menu-button');
const navigation = document.querySelector('#main-nav');

if (menuButton && navigation) {
  menuButton.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') === 'true';
    menuButton.setAttribute('aria-expanded', String(!open));
    navigation.classList.toggle('open', !open);
  });
}

document.querySelectorAll('[data-confirm]').forEach((button) => {
  button.addEventListener('click', (event) => {
    if (!window.confirm(button.dataset.confirm)) {
      event.preventDefault();
    }
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
  select.addEventListener('change', () => select.form?.submit());
});

const RECENT_SEARCH_KEY = 'vagasscan.lastSearchUrl';
const successfulResults = document.querySelector('[data-store-search-url]');
if (successfulResults) {
  try {
    sessionStorage.setItem(RECENT_SEARCH_KEY, `${window.location.pathname}${window.location.search}`);
  } catch (_) {
    // A busca continua funcional quando o navegador bloqueia armazenamento de sessão.
  }
}

const rateLimitAlert = document.querySelector('[data-rate-limit]');
if (rateLimitAlert) {
  const submit = document.querySelector('[data-search-submit]');
  const recentLink = document.querySelector('[data-recent-search]');
  let remaining = Math.max(1, Number(rateLimitAlert.dataset.rateLimit) || 1);
  const originalLabel = submit?.textContent || 'Buscar vagas';
  const updateCountdown = () => {
    if (!submit) return;
    if (remaining > 0) {
      submit.disabled = true;
      submit.textContent = `Tente novamente em ${remaining}s`;
      remaining -= 1;
    } else {
      submit.disabled = false;
      submit.textContent = originalLabel;
      remaining = -1;
    }
  };
  updateCountdown();
  const timer = window.setInterval(() => {
    updateCountdown();
    if (remaining < 0) window.clearInterval(timer);
  }, 1000);
  try {
    const recent = sessionStorage.getItem(RECENT_SEARCH_KEY);
    if (recent && recent.startsWith('/buscar?') && recentLink) {
      recentLink.href = recent;
      recentLink.hidden = false;
    }
  } catch (_) {
    // O botão de retorno é apenas uma conveniência progressiva.
  }
}

const SAVED_JOBS_KEY = 'vagasscan.savedJobs.v1';
const MAX_SAVED_JOBS = 100;

function safeText(value, maximum) {
  return String(value || '').trim().slice(0, maximum);
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
  if (!value || typeof value !== 'object' || Number(value.version) !== 1) return null;
  const id = safeText(value.id, 250);
  const title = safeText(value.title, 200);
  if (!id || !title) return null;
  const score = Math.min(100, Math.max(0, Number(value.score) || 0));
  const savedAt = Number.isNaN(Date.parse(value.savedAt)) ? '' : value.savedAt;
  return {
    version: 1,
    id,
    title,
    company: safeText(value.company, 200) || 'Não informada',
    location: safeText(value.location, 200) || 'Não informada',
    modality: safeText(value.modality, 100) || 'não informada',
    score,
    originalUrl: safeExternalUrl(value.originalUrl),
    detailUrl: safeDetailUrl(value.detailUrl),
    savedAt,
  };
}

function readSavedJobs() {
  try {
    const parsed = JSON.parse(localStorage.getItem(SAVED_JOBS_KEY) || '[]');
    if (!Array.isArray(parsed)) throw new Error('invalid saved jobs');
    return parsed.map(normalizeSavedJob).filter(Boolean).slice(0, MAX_SAVED_JOBS);
  } catch (_) {
    try { localStorage.removeItem(SAVED_JOBS_KEY); } catch (_) { /* armazenamento indisponível */ }
    return [];
  }
}

function writeSavedJobs(jobs) {
  try {
    localStorage.setItem(SAVED_JOBS_KEY, JSON.stringify(jobs.slice(0, MAX_SAVED_JOBS)));
    return true;
  } catch (_) {
    return false;
  }
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
    try {
      payload = normalizeSavedJob(JSON.parse(button.dataset.saveJob));
    } catch (_) {
      payload = null;
    }
    if (!payload) return;
    const jobs = readSavedJobs();
    const existing = jobs.findIndex((job) => job.id === payload.id);
    if (existing >= 0) {
      jobs.splice(existing, 1);
    } else {
      payload.savedAt = new Date().toISOString();
      jobs.unshift(payload);
    }
    writeSavedJobs(jobs);
    refreshSaveButtons();
  });
});

function renderSavedJobs() {
  const list = document.querySelector('[data-saved-jobs-list]');
  const template = document.querySelector('#saved-job-template');
  const empty = document.querySelector('[data-saved-empty]');
  const count = document.querySelector('[data-saved-count]');
  if (!list || !template) return;
  const jobs = readSavedJobs();
  list.replaceChildren();
  jobs.forEach((job) => {
    const fragment = template.content.cloneNode(true);
    const card = fragment.querySelector('.saved-job-card');
    card.dataset.savedId = job.id;
    fragment.querySelector('h3').textContent = job.title;
    fragment.querySelector('.company').textContent = job.company;
    fragment.querySelector('.metadata').textContent = `${job.location} • ${job.modality}`;
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
  if (empty) empty.hidden = jobs.length > 0;
  if (count) count.textContent = `${jobs.length} ${jobs.length === 1 ? 'vaga' : 'vagas'}`;
}

document.addEventListener('click', (event) => {
  const remove = event.target.closest('[data-saved-id]');
  if (!remove?.classList.contains('saved-remove')) return;
  const jobs = readSavedJobs().filter((job) => job.id !== remove.dataset.savedId);
  writeSavedJobs(jobs);
  renderSavedJobs();
  refreshSaveButtons();
});

window.addEventListener('storage', (event) => {
  if (event.key === SAVED_JOBS_KEY) {
    renderSavedJobs();
    refreshSaveButtons();
  }
});

refreshSaveButtons();
renderSavedJobs();
