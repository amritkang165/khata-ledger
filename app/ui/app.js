const rupees = new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:0});
const form = document.querySelector('#note-form');
const result = document.querySelector('#result');

async function refresh() {
  const [ledgerData, brief] = await Promise.all([
    fetch('/api/ledger').then(r => r.json()), fetch('/api/brief').then(r => r.json())
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
  const response = await fetch('/api/note', {method:'POST', body:data});
  const body = await response.json();
  result.textContent = response.ok ? `${body.status === 'inserted' ? '✓ Added' : '⚠ Needs review'}\n\nTranscript\n${body.transcript}\n\nExtracted\n${JSON.stringify(body.extracted, null, 2)}\n\n${body.transcription_provider} → ${body.extraction_provider}` : `Error: ${body.detail || response.statusText}`;
  if (response.ok) await refresh();
});
document.querySelector('#refresh').addEventListener('click', refresh);
document.querySelector('#find-similar').addEventListener('click', async () => {
  const profile = document.querySelector('#similar-profile').value;
  const panel = document.querySelector('#similar-list');
  panel.innerHTML = '<p>Searching Atlas…</p>';
  const response = await fetch(`/api/similar?profile_id=${encodeURIComponent(profile)}`);
  const body = await response.json();
  if (!response.ok) { panel.innerHTML = `<p class="similar-error">${escapeHtml(body.detail || 'Atlas unavailable')}</p>`; return; }
  panel.innerHTML = body.matches.map(item => `<article class="brief-item"><h3>${escapeHtml(item.display_name)}</h3><p>${escapeHtml(item.pattern_text)}</p><p class="message">Similarity ${Number(item.score).toFixed(3)} · ${escapeHtml(item.risk_band)} risk</p></article>`).join('');
});
function escapeHtml(value) { const node = document.createElement('div'); node.textContent = String(value); return node.innerHTML; }
refresh();
