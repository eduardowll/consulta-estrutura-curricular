'use strict';
const $ = (selector) => document.querySelector(selector);
const state = { structures: [], components: [], filtered: [], selected: null, nature: '', view: 'catalog', revision: 0, detailRevision: 0, importDoc: null, ready: false };
const databaseNames = { postgres: 'PostgreSQL', mongo: 'MongoDB', neo4j: 'Neo4j' };
const natureNames = { obrigatoria: 'Obrigatória', optativa: 'Optativa', atividade_complementar: 'Atividade', outra: 'Outra' };
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const normalize = (value) => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const displayName = (value) => String(value).toLocaleLowerCase('pt-BR').replace(/^\p{L}/u, (char) => char.toUpperCase()).replace(/\b(ii|iii|iv|ti|i)\b/g, (word) => word.toUpperCase());
const matrix = () => state.structures.find((item) => item.curso === $('#course').value && String(item.ano) === $('#year').value);
const params = () => new URLSearchParams({ db: $('#database').value, curso: $('#course').value, ano: $('#year').value });
const errorMessage = (detail) => typeof detail === 'string' ? detail : detail?.erros?.join('\n') || detail?.mensagem || 'Não foi possível concluir a operação.';
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(errorMessage(data.detail));
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('A consulta demorou mais que o esperado. Tente novamente.');
    if (error instanceof TypeError) throw new Error('Não foi possível acessar a API. Verifique se o servidor está em execução.');
    throw error;
  } finally { clearTimeout(timeout); }
}
function pageError(message) {
  $('#page-error').hidden = !message;
  $('#page-error').replaceChildren();
  if (message) {
    $('#page-error').append(document.createTextNode(message + ' '));
    const retry = document.createElement('button');
    retry.className = 'text-button'; retry.textContent = 'Tentar novamente'; retry.onclick = loadStructures;
    $('#page-error').append(retry);
  }
}
function resetComparison() {
  $('#comparison').innerHTML = '<p>Execute uma consulta para medir os tempos e verificar se os resultados são iguais.</p>';
}
async function loadStructures() {
  const revision = ++state.revision;
  ++state.detailRevision;
  pageError(''); state.ready = false; $('#export').disabled = true; $('#run-compare').disabled = true;
  state.components = []; renderList();
  const oldCourse = $('#course').value, oldYear = $('#year').value;
  $('#detail').innerHTML = '<div class="detail-placeholder"><p>Carregando estrutura…</p></div>';
  for (const key of ['total', 'required', 'optional', 'relations']) $('#stat-' + key).textContent = '—';
  try {
    const result = await api('/api/estruturas?db=' + $('#database').value);
    if (revision !== state.revision) return;
    state.structures = result.data;
    const courses = [...new Map(result.data.map((item) => [item.curso, item])).values()];
    $('#course').innerHTML = courses.map((item) => `<option value="${escapeHTML(item.curso)}">${escapeHTML(item.curso_nome)} · ${escapeHTML(item.instituicao || item.curso)}</option>`).join('');
    if (courses.some((item) => item.curso === oldCourse)) $('#course').value = oldCourse;
    populateYears(oldYear);
    if (!courses.length) { pageError('Este banco ainda não tem estruturas. Carregue os dados ou importe um JSON.'); $('#detail').innerHTML = '<div class="detail-placeholder"><p>Nenhuma estrutura disponível.</p></div>'; return; }
    await loadComponents();
  } catch (error) {
    if (revision === state.revision) { pageError(error.message); $('#result-count').textContent = 'Consulta indisponível'; $('#detail').innerHTML = '<div class="detail-placeholder"><p>Os detalhes aparecerão quando a conexão for restabelecida.</p></div>'; }
  }
}
function populateYears(preferred = '') {
  const years = state.structures.filter((item) => item.curso === $('#course').value).map((item) => item.ano).sort((a, b) => b - a);
  $('#year').innerHTML = years.map((year) => `<option value="${year}">${year}</option>`).join('');
  if (years.some((year) => String(year) === preferred)) $('#year').value = preferred;
}
async function loadComponents() {
  const revision = ++state.revision;
  ++state.detailRevision;
  state.ready = false; state.components = []; state.selected = null;
  $('#export').disabled = true; $('#run-compare').disabled = true;
  resetComparison(); pageError(''); renderList();
  $('#result-count').textContent = 'Carregando disciplinas…';
  $('#empty').hidden = true;
  $('#detail').innerHTML = '<div class="detail-placeholder"><p>Carregando disciplinas…</p></div>';
  for (const key of ['total', 'required', 'optional', 'relations']) $('#stat-' + key).textContent = '—';
  const current = matrix();
  if (!current) return;
  $('.course-monogram').textContent = current.curso.slice(0, 2);
  $('#source').textContent = 'Fonte: ' + (current.fonte || 'estrutura cadastrada');
  try {
    const result = await api('/api/componentes?' + params());
    if (revision !== state.revision) return;
    state.components = result.data; state.ready = true;
    $('#stat-total').textContent = result.data.length;
    $('#stat-required').textContent = result.data.filter((item) => item.natureza === 'obrigatoria').length;
    $('#stat-optional').textContent = result.data.filter((item) => item.natureza === 'optativa').length;
    $('#stat-relations').textContent = current.n_relacoes;
    $('#required-bar').style.width = (result.data.length ? result.data.filter((item) => item.natureza === 'obrigatoria').length / result.data.length * 100 : 0) + '%';
    $('#matrix-note').textContent = `${current.curso} · MATRIZ ${current.ano}`;
    $('#query-time').textContent = `${databaseNames[result.database]} · ${result.execution_time_ms.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} ms`;
    $('#run-compare').disabled = false;
    renderList();
    const first = state.filtered.find((item) => item.codigo === 'TAD0103') || state.filtered[0];
    if (first) selectComponent(first.codigo);
    else $('#detail').innerHTML = '<div class="detail-placeholder"><p>Selecione uma disciplina para explorar suas conexões.</p></div>';
  } catch (error) {
    if (revision === state.revision) { pageError(error.message); $('#result-count').textContent = 'Consulta indisponível'; $('#query-time').textContent = 'Consulta não concluída'; $('#detail').innerHTML = '<div class="detail-placeholder"><p>Não foi possível carregar as disciplinas.</p></div>'; }
  }
}
function renderList() {
  const focusedCode = document.activeElement?.closest('#components [data-code]')?.dataset.code;
  const search = normalize($('#search').value.trim());
  state.filtered = state.components.filter((item) => (!state.nature || item.natureza === state.nature) && (!search || normalize(item.nome + ' ' + item.codigo).includes(search)));
  const sort = $('#sort').value;
  state.filtered.sort((a, b) => sort === 'carga' ? (b.carga ?? -1) - (a.carga ?? -1) || a.codigo.localeCompare(b.codigo) : String(a[sort]).localeCompare(String(b[sort]), 'pt-BR'));
  $('#components').innerHTML = state.filtered.map((item) => `<tr class="${item.codigo === state.selected ? 'selected' : ''}"><td><button class="discipline-button" data-code="${escapeHTML(item.codigo)}" aria-pressed="${item.codigo === state.selected}">${escapeHTML(displayName(item.nome))}<small>${escapeHTML(item.codigo)}</small></button></td><td><span class="badge ${escapeHTML(item.natureza)}">${escapeHTML(natureNames[item.natureza] || item.natureza)}</span></td><td class="load-cell"><span class="load">${escapeHTML(item.carga ?? '—')} <small>${item.unidade_carga === 'creditos' ? 'cr.' : escapeHTML(item.unidade_carga || '')}</small></span></td><td aria-hidden="true"><span class="row-arrow">↗</span></td></tr>`).join('');
  $('#result-count').textContent = `${state.filtered.length} de ${state.components.length} componentes`;
  $('#empty').hidden = !state.ready || state.filtered.length !== 0;
  $('#export').disabled = !state.ready || state.filtered.length === 0;
  if (focusedCode) [...document.querySelectorAll('#components [data-code]')].find((button) => button.dataset.code === focusedCode)?.focus({ preventScroll: true });
}
function chainSection(title, description, entries, emptyText) {
  return `<section class="detail-section"><h4>${title} <span class="connection-count">${entries.length}</span></h4><p>${description}</p>${entries.length ? `<ul class="chain-list">${entries.map((item) => `<li><button class="chain-button" data-code="${escapeHTML(item.codigo)}"><span><small>${escapeHTML(item.codigo)}</small>${escapeHTML(displayName(item.nome))}</span><span class="chain-level">${item.nivel === 1 ? 'Direto' : 'Nível ' + item.nivel} ↗</span></button></li>`).join('')}</ul>` : `<div class="detail-empty">${emptyText}</div>`}</section>`;
}
async function selectComponent(code) {
  const item = state.components.find((component) => component.codigo === code);
  if (!item) return;
  const revision = ++state.detailRevision;
  state.selected = code; renderList();
  const top = `<div class="detail-top"><div class="detail-eyebrow"><span>DISCIPLINA EM FOCO</span><svg class="icon" aria-hidden="true"><use href="#i-nodes"/></svg></div><span class="detail-code">${escapeHTML(item.codigo)}</span><h3>${escapeHTML(displayName(item.nome))}</h3><span class="badge ${escapeHTML(item.natureza)}">${escapeHTML(natureNames[item.natureza] || item.natureza)}</span><div class="detail-facts"><div><span>Carga curricular</span><strong>${escapeHTML(item.carga ?? '—')} ${item.unidade_carga === 'creditos' ? 'créditos' : escapeHTML(item.unidade_carga || '')}</strong></div><div><span>Período</span><strong>${item.periodo ? escapeHTML(item.periodo) + 'º semestre' : 'Não informado'}</strong></div></div></div>`;
  $('#detail').innerHTML = top + '<div class="detail-section"><p>Buscando conexões…</p></div>';
  try {
    const result = await api(`/api/componentes/${encodeURIComponent(code)}/cadeia?${params()}`);
    if (revision !== state.detailRevision) return;
    const data = result.data;
    const alternatives = (item.prerequisitos || []).filter((p) => p.tipo !== 'PRE' || p.logica === 'OU');
    $('#detail').innerHTML = top + chainSection('O que vem antes', 'Cadeia de pré-requisitos desta disciplina.', data.prerequisitos_cadeia, 'Esta disciplina não exige pré-requisitos.') + chainSection('Caminhos que se abrem', 'Disciplinas que dependem deste componente.', data.libera_cadeia, 'Nenhuma dependência posterior cadastrada.') + (alternatives.length ? `<div class="detail-section"><h4>Condições da matriz</h4>${alternatives.map((p) => `<p>${escapeHTML(p.codigo)} · ${p.tipo === 'CO' ? 'Correquisito' : p.tipo === 'EQUIV' ? 'Equivalência' : 'Pré-requisito alternativo (OU)'}</p>`).join('')}</div>` : '') + '<div class="detail-bottom">Direto: conexão imediata. Nível 2 ou maior: conexão indireta. As relações não representam aprovação ou elegibilidade para matrícula.</div>';
  } catch (error) {
    if (revision === state.detailRevision) $('#detail').innerHTML = top + `<div class="detail-section"><p role="alert">${escapeHTML(error.message)}</p><button class="text-button" data-code="${escapeHTML(code)}">Tentar novamente</button></div>`;
  }
}
function changeView(view) {
  state.view = view;
  $('#current-page').textContent = view === 'catalog' ? 'Visão geral' : 'Comparar consultas';
  for (const button of document.querySelectorAll('[data-view]')) { const active = button.dataset.view === view; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); }
  $('#catalog-view').hidden = view !== 'catalog'; $('#compare-view').hidden = view !== 'compare';
}
async function compare() {
  const revision = state.revision;
  const button = $('#run-compare'); button.disabled = true;
  $('#comparison').innerHTML = '<p role="status">Consultando PostgreSQL, MongoDB e Neo4j…</p>';
  const query = params(); query.set('db', 'all');
  try {
    const result = await api('/api/componentes?' + query);
    if (revision !== state.revision) return;
    const max = Math.max(...Object.values(result.execution_times_ms), .001);
    $('#comparison').innerHTML = `<div class="comparison-summary">${result.results_match ? '✓ Resultados iguais nos três bancos' : '⚠ Os bancos retornaram resultados diferentes. Confira a carga dos dados.'}</div>` + Object.entries(result.execution_times_ms).map(([db, time]) => `<div class="comparison-row"><strong>${databaseNames[db]}<small>${result.results_by_database[db].length} componentes</small></strong><div class="bar-track"><div class="bar" style="width:${Math.max(1, time / max * 100)}%"></div></div><span>${time.toLocaleString('pt-BR', { maximumFractionDigits: 3 })} ms</span></div>`).join('');
  } catch (error) { if (revision === state.revision) $('#comparison').innerHTML = `<p role="alert">${escapeHTML(error.message)}</p>`; }
  finally { if (revision === state.revision) button.disabled = false; }
}
function exportCSV() {
  const cell = (value) => '"' + String(value ?? '').replace(/^[=+@-]/, "'$&").replace(/"/g, '""') + '"';
  const rows = [['Código', 'Disciplina', 'Natureza', 'Carga', 'Unidade', 'Período'], ...state.filtered.map((item) => [item.codigo, item.nome, natureNames[item.natureza], item.carga, item.unidade_carga, item.periodo])];
  const url = URL.createObjectURL(new Blob(['\uFEFF' + rows.map((row) => row.map(cell).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url; link.download = `matriz-${$('#course').value}-${$('#year').value}.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function closeImport() { if (!$('#import-submit').dataset.busy) $('#import-dialog').close(); }
$('#import-open').onclick = () => $('#import-dialog').showModal();
$('#import-close').onclick = closeImport; $('#import-cancel').onclick = closeImport;
$('#import-dialog').addEventListener('cancel', (event) => { if ($('#import-submit').dataset.busy) event.preventDefault(); });
let fileRevision = 0;
$('#import-file').onchange = async (event) => {
  const revision = ++fileRevision;
  state.importDoc = null; $('#import-submit').disabled = true; $('#import-message').textContent = ''; $('#import-preview').hidden = true; $('#import-confirm').checked = false;
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size > 5 * 1024 * 1024) throw new Error('Use um JSON de até 5 MB.');
    const doc = JSON.parse(await file.text());
    if (revision !== fileRevision) return;
    if (!doc?.curso?.sigla || !doc?.curso?.nome || !Number.isInteger(doc?.estrutura?.ano) || !Array.isArray(doc?.componentes) || !Array.isArray(doc?.relacoes)) throw new Error('O JSON deve conter curso, estrutura, componentes e relações no formato do projeto.');
    state.importDoc = doc;
    $('#import-preview').textContent = `${doc.curso.nome} · ${doc.estrutura.ano} · ${doc.componentes.length} componentes · ${doc.relacoes.length} relações`;
    $('#import-preview').hidden = false; $('#import-submit').disabled = false;
  } catch (error) { if (revision === fileRevision) $('#import-message').textContent = error instanceof SyntaxError ? 'Arquivo JSON inválido. Confira a sintaxe.' : error.message; }
};
$('#import-form').onsubmit = async (event) => {
  event.preventDefault(); if (!state.importDoc || $('#import-submit').dataset.busy) return;
  const button = $('#import-submit'); button.disabled = true; button.dataset.busy = 'true'; $('#import-file').disabled = true;
  $('#import-message').textContent = 'Validando e registrando a estrutura…';
  try {
    const result = await api('/api/estruturas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(state.importDoc) });
    $('#import-message').textContent = result.mensagem;
    state.importDoc = null; $('#import-form').reset(); $('#import-preview').hidden = true;
    await loadStructures();
  } catch (error) { $('#import-message').textContent = error.message; }
  finally { delete button.dataset.busy; button.disabled = !state.importDoc; $('#import-file').disabled = false; }
};
$('#database').onchange = loadStructures;
$('#course').onchange = () => { populateYears(); loadComponents(); };
$('#year').onchange = loadComponents;
$('#search').oninput = renderList; $('#sort').onchange = renderList;
$('.filter-row').onclick = (event) => {
  const button = event.target.closest('[data-filter]'); if (!button) return;
  state.nature = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach((item) => { const active = item === button; item.classList.toggle('active', active); item.setAttribute('aria-pressed', active); }); renderList();
};
$('#clear-filters').onclick = () => { $('#search').value = ''; $('[data-filter=""]').click(); $('#search').focus(); };
async function navigateComponent(event) {
  const button = event.target.closest('[data-code]');
  if (!button) return;
  const fromDetail = Boolean(button.closest('#detail'));
  await selectComponent(button.dataset.code);
  if (window.matchMedia('(max-width: 950px)').matches || fromDetail) {
    const heading = $('#detail h3');
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
    $('#detail').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
  }
}
$('#components').onclick = navigateComponent;
$('#detail').onclick = navigateComponent;
document.querySelectorAll('[data-view]').forEach((button) => button.onclick = () => changeView(button.dataset.view));
$('#run-compare').onclick = compare; $('#export').onclick = exportCSV;
document.addEventListener('keydown', (event) => { if (event.key === '/' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName) && !$('#import-dialog').open) { event.preventDefault(); changeView('catalog'); $('#search').focus(); } });
async function init() {
  try {
    const result = await api('/api/status');
    const available = Object.entries(result.databases).filter(([, online]) => online).map(([name]) => name);
    $('#connection-status').textContent = `${available.length} de 3 bancos conectados ao iniciar`;
    $('#status-dot').classList.toggle('connected', available.length > 0);
    if (!available.includes($('#database').value) && available.length) $('#database').value = available[0];
  } catch { $('#connection-status').textContent = 'API indisponível'; }
  await loadStructures();
}
init();
