const rupees = new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:0});
const form = document.querySelector('#note-form');
const result = document.querySelector('#result');
const authView = document.querySelector('#auth-view');
const appView = document.querySelector('#app-view');
let recordedAudio = null;
let mediaRecorder = null;
let recordingStream = null;

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 401 && !url.startsWith('/api/auth/')) showAuth();
  return response;
}

function showAuth(message = '') {
  appView.classList.add('hidden');
  authView.classList.remove('hidden');
  const error = document.querySelector('#auth-error');
  error.textContent = message;
  error.classList.toggle('hidden', !message);
}

async function showApp(user) {
  document.querySelector('#account-name').textContent = user.display_name;
  document.querySelector('#owner-greeting').textContent = user.display_name.split(' ')[0];
  document.querySelector('#shop-name').textContent = user.shop_name;
  document.querySelector('#shop-location').textContent = user.city ? `${user.city} · Private shop ledger` : 'Private shop ledger';
  document.querySelector('#account-language').textContent = user.preferred_language;
  document.querySelector('#owner-avatar').textContent = user.display_name.trim().charAt(0).toUpperCase();
  document.querySelector('#today-date').textContent = new Intl.DateTimeFormat('en-IN', {
    weekday: 'long', day: 'numeric', month: 'long'
  }).format(new Date());
  authView.classList.add('hidden');
  appView.classList.remove('hidden');
  await refresh();
}

async function refresh() {
  const [ledgerData, brief, history, reviewData] = await Promise.all([
    api('/api/ledger').then(r => r.json()), api('/api/brief').then(r => r.json()),
    api('/api/transactions').then(r => r.json()), api('/api/reviews').then(r => r.json())
  ]);
  document.querySelector('#ledger').innerHTML = ledgerData.customers.length
    ? ledgerData.customers.map(row => `<tr><td><div class="customer-cell"><span class="customer-avatar">${escapeHtml(row.name.charAt(0).toUpperCase())}</span><strong>${escapeHtml(row.name)}</strong></div></td><td><span class="balance ${row.outstanding_rupees > 0 ? 'open' : 'settled'}">${rupees.format(row.outstanding_rupees)}</span></td><td>${row.last_activity || '—'}</td><td>${row.transaction_count}</td></tr>`).join('')
    : '<tr class="empty-row"><td colspan="4"><b>No customer accounts yet</b><span>Your first voice note will create one automatically.</span></td></tr>';
  document.querySelector('#brief-total').textContent = `${rupees.format(brief.total_outstanding)} to collect`;
  document.querySelector('#stat-outstanding').textContent = rupees.format(brief.total_outstanding);
  document.querySelector('#stat-customers').textContent = ledgerData.customers.length;
  document.querySelector('#stat-entries').textContent = history.transactions.length;
  document.querySelector('#stat-reviews').textContent = reviewData.reviews.length;
  document.querySelector('#brief-list').innerHTML = brief.customers.length
    ? brief.customers.map((item, index) => `<article class="brief-item"><span class="priority">${index + 1}</span><div><h3>${escapeHtml(item.customer_name)}</h3><b>${rupees.format(item.outstanding_rupees)}</b><p>${item.days_open} days open · ${escapeHtml(item.pattern_note)}</p><p class="message">“${escapeHtml(item.collection_message)}”</p></div></article>`).join('')
    : '<div class="empty-state"><span>✓</span><b>No collections due</b><p>Outstanding customer balances will appear here.</p></div>';
  document.querySelector('#transactions').innerHTML = history.transactions.length
    ? history.transactions.map(item => `<tr><td>${escapeHtml(item.happened_on)}</td><td><strong>${escapeHtml(item.customer_name)}</strong></td><td><span class="entry-type ${item.transaction_type}">${item.transaction_type === 'credit_given' ? 'Credit given' : 'Payment received'}</span></td><td class="money">${item.transaction_type === 'credit_paid' ? '−' : ''}${rupees.format(item.amount_rupees)}</td><td>${escapeHtml(item.due_day || '—')}</td><td><button class="danger small delete-transaction" data-id="${item.id}">Delete</button></td></tr>`).join('')
    : '<tr class="empty-row"><td colspan="6"><b>No transactions recorded</b><span>New entries will build the shop passbook.</span></td></tr>';
  renderReviews(reviewData.reviews);
}

function renderReviews(reviews) {
  const section = document.querySelector('#review-section');
  section.classList.toggle('hidden', reviews.length === 0);
  document.querySelector('#review-list').innerHTML = reviews.map(review => {
    const item = review.extracted;
    return `<form class="review-item" data-id="${review.id}"><p><strong>Heard:</strong> ${escapeHtml(review.transcript)}</p><label>Customer<input name="customer_name" value="${escapeAttr(item.customer_name || '')}" required></label><label>Amount (rupees)<input name="amount_rupees" type="number" min="1" value="${item.amount_rupees || ''}" required></label><label>Due<input name="due_day" value="${escapeAttr(item.due_day || '')}"></label><label>Context<input name="context" value="${escapeAttr(item.context || '')}"></label><label>Type<select name="transaction_type"><option value="credit_given" ${item.transaction_type === 'credit_given' ? 'selected' : ''}>Credit given</option><option value="credit_paid" ${item.transaction_type === 'credit_paid' ? 'selected' : ''}>Payment received</option></select></label><div class="review-actions"><button type="submit">Save corrected entry</button><button type="button" class="danger reject-review">Discard</button></div></form>`;
  }).join('');
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const data = new FormData();
  const audio = recordedAudio || document.querySelector('#audio').files[0];
  const transcript = document.querySelector('#transcript').value.trim();
  if (audio) data.append('audio', audio); else if (transcript) data.append('transcript', transcript); else return;
  result.classList.remove('hidden'); result.textContent = 'Processing note…';
  const response = await api('/api/note', {method:'POST', body:data});
  const body = await response.json();
  result.textContent = response.ok ? `${body.status === 'inserted' ? '✓ Added' : '⚠ Needs review'}\n\nTranscript\n${body.transcript}\n\nExtracted\n${JSON.stringify(body.extracted, null, 2)}\n\n${body.transcription_provider} → ${body.extraction_provider}` : `Error: ${body.detail || response.statusText}`;
  if (response.ok) await refresh();
});
document.querySelector('#refresh').addEventListener('click', refresh);

document.querySelector('#record').addEventListener('click', async event => {
  const status = document.querySelector('#record-status');
  if (mediaRecorder?.state === 'recording') {
    mediaRecorder.stop();
    event.currentTarget.querySelector('.mic').textContent = '🎙';
    event.currentTarget.querySelector('b').textContent = 'Start voice note';
    return;
  }
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({audio: true});
    const chunks = [];
    mediaRecorder = new MediaRecorder(recordingStream);
    mediaRecorder.addEventListener('dataavailable', e => { if (e.data.size) chunks.push(e.data); });
    mediaRecorder.addEventListener('stop', () => {
      recordedAudio = new File([new Blob(chunks, {type: mediaRecorder.mimeType})], 'voice-note.webm', {type: mediaRecorder.mimeType});
      recordingStream.getTracks().forEach(track => track.stop());
      status.textContent = '✓ Recording ready';
    });
    mediaRecorder.start();
    event.currentTarget.querySelector('.mic').textContent = '■';
    event.currentTarget.querySelector('b').textContent = 'Stop recording';
    status.textContent = 'Recording…';
  } catch (_error) {
    status.textContent = 'Microphone permission was not granted.';
  }
});

function openAuthPanel(panelId) {
  for (const panel of document.querySelectorAll('.auth-panel')) panel.classList.toggle('hidden', panel.id !== panelId);
  for (const tab of document.querySelectorAll('.auth-tab')) tab.classList.toggle('active', tab.dataset.authPanel === panelId);
  document.querySelector('#auth-error').classList.add('hidden');
}

for (const trigger of document.querySelectorAll('[data-auth-panel]')) {
  trigger.addEventListener('click', () => openAuthPanel(trigger.dataset.authPanel));
}

document.querySelector('#transactions').addEventListener('click', async event => {
  const button = event.target.closest('.delete-transaction');
  if (!button || !confirm('Delete this transaction?')) return;
  const response = await api(`/api/transactions/${button.dataset.id}`, {method: 'DELETE'});
  if (response.ok) await refresh();
});

document.querySelector('#review-list').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.target.closest('.review-item');
  const values = Object.fromEntries(new FormData(form));
  const payload = {...values, amount_rupees: Number(values.amount_rupees), confidence: 1};
  payload.due_day ||= null; payload.context ||= null;
  const response = await api(`/api/reviews/${form.dataset.id}/approve`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  if (response.ok) await refresh();
});

document.querySelector('#review-list').addEventListener('click', async event => {
  const button = event.target.closest('.reject-review');
  if (!button) return;
  const form = button.closest('.review-item');
  const response = await api(`/api/reviews/${form.dataset.id}`, {method: 'DELETE'});
  if (response.ok) await refresh();
});

for (const [formId, endpoint] of [['login-form', '/api/auth/login'], ['register-form', '/api/auth/register']]) {
  document.querySelector(`#${formId}`).addEventListener('submit', async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    const response = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    const body = await response.json();
    if (!response.ok) { showAuth(body.detail || 'Unable to continue'); return; }
    event.currentTarget.reset();
    await showApp(body);
  });
}

document.querySelector('#logout').addEventListener('click', async () => {
  await fetch('/api/auth/logout', {method: 'POST'});
  showAuth();
});

function escapeHtml(value) { const node = document.createElement('div'); node.textContent = String(value); return node.innerHTML; }
function escapeAttr(value) { return escapeHtml(value).replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }

fetch('/api/auth/me').then(async response => {
  if (response.ok) await showApp(await response.json()); else showAuth();
}).catch(() => showAuth('The server is unavailable.'));
