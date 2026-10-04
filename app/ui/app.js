const rupees = new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:0});
const form = document.querySelector('#note-form');
const result = document.querySelector('#result');
const authView = document.querySelector('#auth-view');
const appView = document.querySelector('#app-view');

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
  authView.classList.add('hidden');
  appView.classList.remove('hidden');
  await refresh();
}

async function refresh() {
  const [ledgerData, brief] = await Promise.all([
    api('/api/ledger').then(r => r.json()), api('/api/brief').then(r => r.json())
  ]);
  document.querySelector('#ledger').innerHTML = ledgerData.customers.length
    ? ledgerData.customers.map(row => `<tr><td>${escapeHtml(row.name)}</td><td class="money">${rupees.format(row.outstanding_rupees)}</td><td>${row.last_activity || '—'}</td><td>${row.transaction_count}</td></tr>`).join('')
    : '<tr><td colspan="4">Your ledger is empty. Add the first voice note above.</td></tr>';
  document.querySelector('#brief-total').textContent = `${rupees.format(brief.total_outstanding)} to collect`;
  document.querySelector('#brief-list').innerHTML = brief.customers.length
    ? brief.customers.map(item => `<article class="brief-item"><h3>${escapeHtml(item.customer_name)} · ${rupees.format(item.outstanding_rupees)}</h3><p>${item.days_open} days open. ${escapeHtml(item.pattern_note)}</p><p class="message">“${escapeHtml(item.collection_message)}”</p></article>`).join('')
    : '<p>No outstanding credit yet.</p>';
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const data = new FormData();
  const audio = document.querySelector('#audio').files[0];
  const transcript = document.querySelector('#transcript').value.trim();
  if (audio) data.append('audio', audio); else if (transcript) data.append('transcript', transcript); else return;
  result.classList.remove('hidden'); result.textContent = 'Processing note…';
  const response = await api('/api/note', {method:'POST', body:data});
  const body = await response.json();
  result.textContent = response.ok ? `${body.status === 'inserted' ? '✓ Added' : '⚠ Needs review'}\n\nTranscript\n${body.transcript}\n\nExtracted\n${JSON.stringify(body.extracted, null, 2)}\n\n${body.transcription_provider} → ${body.extraction_provider}` : `Error: ${body.detail || response.statusText}`;
  if (response.ok) await refresh();
});
document.querySelector('#refresh').addEventListener('click', refresh);

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

fetch('/api/auth/me').then(async response => {
  if (response.ok) await showApp(await response.json()); else showAuth();
}).catch(() => showAuth('The server is unavailable.'));
