const rupees = new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:0});
const form = document.querySelector('#note-form');
const result = document.querySelector('#result');
const authView = document.querySelector('#auth-view');
const appView = document.querySelector('#app-view');
let recordedAudio = null;
let mediaRecorder = null;
let recordingStream = null;
let recordingTimer = null;
let recordingStartedAt = 0;
let audioContext = null;
let audioAnalyser = null;
let audioSource = null;
let audioMeterFrame = null;
let briefCustomers = [];
let transactionHistory = [];
let noteSubmitting = false;
let pendingNoteKey = null;
let toastTimer = null;

function newIdempotencyKey() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${crypto.getRandomValues(new Uint32Array(2)).join('-')}`;
}

function showToast(message, tone = 'success') {
  const toast = document.querySelector('#toast');
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.dataset.tone = tone;
  toast.classList.remove('hidden');
  toastTimer = setTimeout(() => toast.classList.add('hidden'), 3200);
}

function stopAudioMeter() {
  cancelAnimationFrame(audioMeterFrame);
  audioMeterFrame = null;
  try { audioSource?.disconnect(); } catch (_error) { /* already disconnected */ }
  if (audioContext && audioContext.state !== 'closed') audioContext.close().catch(() => {});
  audioSource = null;
  audioAnalyser = null;
  audioContext = null;
  for (const bar of document.querySelectorAll('.voice-meter i')) bar.style.transform = 'scaleY(.7)';
}

function showReadyWaveform() {
  const levels = [.7, 1.1, 1.7, 1.25, 2.2, 1.45, 2.7, 1.8, 2.35, 1.4, 2.55, 1.65, 2.15, 1.15, 1.75, 1.3, 1.55, 1, .7];
  document.querySelectorAll('.voice-meter i').forEach((bar, index) => {
    bar.style.transform = `scaleY(${levels[index] || 1})`;
  });
}

function startAudioMeter(stream) {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    audioContext = new AudioContextClass();
    if (audioContext.state === 'suspended') audioContext.resume().catch(() => {});
    audioAnalyser = audioContext.createAnalyser();
    audioAnalyser.fftSize = 128;
    audioAnalyser.smoothingTimeConstant = .72;
    audioSource = audioContext.createMediaStreamSource(stream);
    audioSource.connect(audioAnalyser);
    const levels = new Uint8Array(audioAnalyser.frequencyBinCount);
    const bars = [...document.querySelectorAll('.voice-meter i')];
    const centre = Math.floor(bars.length / 2);
    const drawLevels = () => {
      audioAnalyser.getByteFrequencyData(levels);
      bars.forEach((bar, index) => {
        const distance = Math.abs(index - centre);
        const bin = Math.min(levels.length - 1, 2 + distance * 2);
        const strength = levels[bin] / 255;
        const shape = 1 - (distance / (centre + 1)) * .28;
        bar.style.transform = `scaleY(${(.65 + strength * 4.2 * shape).toFixed(2)})`;
      });
      audioMeterFrame = requestAnimationFrame(drawLevels);
    };
    drawLevels();
  } catch (_error) {
    stopAudioMeter();
  }
}

function stopRecordingTimer() {
  clearInterval(recordingTimer);
  recordingTimer = null;
}

function setRecordTime() {
  const seconds = Math.floor((Date.now() - recordingStartedAt) / 1000);
  const minutes = String(Math.floor(seconds / 60)).padStart(2, '0');
  document.querySelector('#record-time').textContent = `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
}

function resetRecorderUi() {
  stopRecordingTimer();
  stopAudioMeter();
  const button = document.querySelector('#record');
  button.disabled = false;
  button.classList.remove('is-recording', 'is-stopping', 'has-recording');
  form.classList.remove('is-recording');
  button.setAttribute('aria-pressed', 'false');
  button.setAttribute('aria-label', 'Start recording a voice note');
  document.querySelector('#record-title').textContent = 'Tap to speak';
  document.querySelector('#record-status').textContent = 'Say the customer, amount and what they bought';
  document.querySelector('#record-time').textContent = '00:00';
}

function updateDiscardButton() {
  const hasNote = Boolean(
    recordedAudio ||
    document.querySelector('#audio').files[0] ||
    document.querySelector('#transcript').value.trim()
  );
  document.querySelector('#discard-note').classList.toggle('hidden', !hasNote);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 401 && !url.startsWith('/api/auth/')) showAuth();
  return response;
}

function showAuth(message = '') {
  appView.classList.add('hidden');
  authView.classList.remove('hidden');
  const error = document.querySelector('#auth-error');
  error.textContent = typeof message === 'string' ? message : 'Please check the information and try again.';
  error.classList.toggle('hidden', !error.textContent);
}

function formatApiError(body) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const labels = {
      shop_name: 'Shop name', display_name: 'Owner name', phone: 'Mobile number',
      city: 'Town or city', preferred_language: 'Working language', email: 'Email address',
      password: 'Password'
    };
    return detail.map(item => {
      if (typeof item === 'string') return item;
      const field = Array.isArray(item.loc) ? item.loc.at(-1) : null;
      if (field === 'password' && /at least 8 characters/i.test(item.msg || '')) {
        return 'Password must contain at least 8 characters.';
      }
      const label = labels[field];
      const message = String(item.msg || 'Please check this field.').replace(/^Value error, /, '');
      return label ? `${label}: ${message}` : message;
    }).join(' ');
  }
  return typeof body?.message === 'string' ? body.message : 'Please check the information and try again.';
}

async function showApp(user, notice = '') {
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
  const appNotice = document.querySelector('#app-notice');
  appNotice.textContent = notice;
  appNotice.classList.toggle('hidden', !notice);
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
  briefCustomers = brief.customers;
  document.querySelector('#brief-total').textContent = `${rupees.format(brief.total_due ?? brief.total_outstanding)} due for follow-up`;
  document.querySelector('#stat-outstanding').textContent = rupees.format(brief.total_outstanding);
  document.querySelector('#stat-customers').textContent = ledgerData.customers.length;
  document.querySelector('#stat-entries').textContent = history.transactions.length;
  document.querySelector('#stat-reviews').textContent = reviewData.reviews.length;
  transactionHistory = history.transactions;
  document.querySelector('#brief-list').innerHTML = brief.customers.length
    ? brief.customers.map((item, index) => `<article class="brief-item"><span class="priority">${index + 1}</span><div><h3>${escapeHtml(item.customer_name)}</h3><b>${rupees.format(item.outstanding_rupees)}</b><p>${item.days_open} days open${item.due_on ? ` · due ${escapeHtml(formatDisplayDate(item.due_on))}` : ''}</p><p>${escapeHtml(item.pattern_note)}</p><button type="button" class="message-button" data-brief-index="${index}">Send message</button></div></article>`).join('')
    : '<div class="empty-state"><span>✓</span><b>No reminders due</b><p>A balance appears here when its due date arrives or it has been open for 3 days.</p></div>';
  renderTransactions();
  renderReviews(reviewData.reviews);
}

function renderTransactions() {
  const query = document.querySelector('#transaction-search').value.trim().toLocaleLowerCase();
  const type = document.querySelector('#transaction-filter').value;
  const visible = transactionHistory.filter(item => {
    const matchesName = item.customer_name.toLocaleLowerCase().includes(query);
    const matchesType = type === 'all' || item.transaction_type === type;
    return matchesName && matchesType;
  });
  document.querySelector('#transactions').innerHTML = visible.length
    ? visible.map(item => `<tr><td>${escapeHtml(formatDisplayDate(item.happened_on))}</td><td><strong>${escapeHtml(item.customer_name)}</strong></td><td><span class="entry-type ${item.transaction_type}">${item.transaction_type === 'credit_given' ? 'Credit given' : 'Payment received'}</span></td><td class="money">${item.transaction_type === 'credit_paid' ? '−' : ''}${rupees.format(item.amount_rupees)}</td><td>${escapeHtml(item.due_day || '—')}</td><td><button class="danger small delete-transaction" data-id="${item.id}">Delete</button></td></tr>`).join('')
    : `<tr class="empty-row"><td colspan="6"><b>${transactionHistory.length ? 'No matching transactions' : 'No transactions recorded'}</b><span>${transactionHistory.length ? 'Try another customer or entry type.' : 'New entries will build the shop passbook.'}</span></td></tr>`;
}

function formatDisplayDate(value) {
  return new Intl.DateTimeFormat('en-IN', {day: 'numeric', month: 'short', year: 'numeric'})
    .format(new Date(`${value}T00:00:00`));
}

function localDateValue() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

function buildReminderMessage(customer) {
  let runningBalance = 0;
  const history = customer.history.map(transaction => {
    const isCredit = transaction.transaction_type === 'credit_given';
    runningBalance += isCredit ? transaction.amount_rupees : -transaction.amount_rupees;
    const action = isCredit ? 'Udhaar' : 'Payment';
    const context = transaction.context ? ` · ${transaction.context}` : '';
    return `${formatDisplayDate(transaction.happened_on)} — ${action} ${rupees.format(transaction.amount_rupees)}${context} · baki ${rupees.format(Math.max(0, runningBalance))}`;
  });
  return [
    `Namaste ${customer.customer_name} ji,`,
    '',
    `Aaj ${formatDisplayDate(localDateValue())} ko aapke khate mein ${rupees.format(customer.outstanding_rupees)} baki hain.`,
    '',
    'Khata history:',
    ...history.map(line => `• ${line}`),
    '',
    `Total pending: ${rupees.format(customer.outstanding_rupees)}`,
    'Kripya hisaab check kar lein. Payment ho gaya ho toh bata dein. Dhanyavaad.'
  ].join('\n');
}

async function copyReminderMessage() {
  const message = document.querySelector('#reminder-message');
  try {
    await navigator.clipboard.writeText(message.value);
  } catch (_error) {
    message.select();
    document.execCommand('copy');
    message.setSelectionRange(0, 0);
  }
  document.querySelector('#message-feedback').textContent = 'Message copied. Paste it into WhatsApp or SMS.';
}

document.querySelector('#brief-list').addEventListener('click', event => {
  const button = event.target.closest('.message-button');
  if (!button) return;
  const customer = briefCustomers[Number(button.dataset.briefIndex)];
  if (!customer) return;
  document.querySelector('#message-title').textContent = `Message ${customer.customer_name}`;
  document.querySelector('#reminder-message').value = buildReminderMessage(customer);
  document.querySelector('#message-feedback').textContent = '';
  document.querySelector('#message-dialog').showModal();
});

document.querySelector('#close-message').addEventListener('click', () => document.querySelector('#message-dialog').close());
document.querySelector('#message-dialog').addEventListener('click', event => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});
document.querySelector('#copy-message').addEventListener('click', copyReminderMessage);
document.querySelector('#share-message').addEventListener('click', async () => {
  const text = document.querySelector('#reminder-message').value;
  if (navigator.share) {
    try { await navigator.share({title: 'Khata reminder', text}); } catch (_error) { /* user closed the share sheet */ }
  } else {
    await copyReminderMessage();
  }
});

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
  if (noteSubmitting) return;
  const data = new FormData();
  const audio = recordedAudio || document.querySelector('#audio').files[0];
  const transcript = document.querySelector('#transcript').value.trim();
  if (audio) data.append('audio', audio); else if (transcript) data.append('transcript', transcript); else return;
  noteSubmitting = true;
  pendingNoteKey ||= newIdempotencyKey();
  const submitButton = form.querySelector('.submit-note');
  submitButton.disabled = true;
  submitButton.classList.add('is-processing');
  result.classList.remove('hidden');
  result.textContent = 'Processing note…';
  try {
    const response = await api('/api/note', {
      method: 'POST', body: data, headers: {'Idempotency-Key': pendingNoteKey}
    });
    const body = await response.json();
    if (response.ok) {
      const entry = body.extracted;
      const isPayment = entry.transaction_type === 'credit_paid';
      const amount = entry.amount_rupees ? rupees.format(entry.amount_rupees) : 'amount not clear';
      const savedLabel = body.deduplicated
        ? '✓ Already saved — duplicate prevented'
        : `✓ ${isPayment ? 'Payment recorded' : 'Added to khata'}`;
      result.textContent = body.status === 'inserted'
        ? `${savedLabel}\n${body.matched_customer || entry.customer_name} · ${amount}${entry.due_day ? ` · due ${entry.due_day}` : ''}\n\nHeard: “${body.transcript}”`
        : `${body.deduplicated ? 'Already waiting for review — duplicate prevented' : 'Please check this note before it is saved'}\n${entry.customer_name || 'Customer unclear'} · ${amount}\n\nHeard: “${body.transcript}”`;
      pendingNoteKey = null;
      recordedAudio = null;
      document.querySelector('#audio').value = '';
      document.querySelector('#transcript').value = '';
      resetRecorderUi();
      updateDiscardButton();
      await refresh();
    } else {
      result.textContent = `Could not add this note\n${formatApiError(body)}`;
    }
  } catch (_error) {
    result.textContent = 'Connection interrupted. Tap the arrow again to retry safely.';
  } finally {
    noteSubmitting = false;
    submitButton.disabled = false;
    submitButton.classList.remove('is-processing');
  }
});
document.querySelector('#refresh').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = 'Refreshing…';
  try {
    await refresh();
    showToast('Ledger refreshed');
  } catch (_error) {
    showToast('Could not refresh the ledger', 'error');
  } finally {
    button.disabled = false;
    button.textContent = '↻ Refresh';
  }
});
document.querySelector('#transaction-search').addEventListener('input', renderTransactions);
document.querySelector('#transaction-filter').addEventListener('change', renderTransactions);

document.querySelector('#record').addEventListener('click', async event => {
  const button = event.currentTarget;
  const status = document.querySelector('#record-status');
  if (mediaRecorder?.state === 'recording') {
    stopRecordingTimer();
    stopAudioMeter();
    mediaRecorder.stop();
    button.classList.remove('is-recording');
    button.classList.add('is-stopping');
    button.disabled = true;
    form.classList.remove('is-recording');
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-label', 'Saving the voice note');
    document.querySelector('#record-title').textContent = 'Saving recording…';
    status.textContent = 'Finishing the audio file';
    return;
  }
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1
    }});
    const chunks = [];
    const supportedTypes = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'];
    const mimeType = supportedTypes.find(type => MediaRecorder.isTypeSupported?.(type));
    mediaRecorder = new MediaRecorder(recordingStream, mimeType ? {mimeType} : undefined);
    mediaRecorder.addEventListener('dataavailable', e => { if (e.data.size) chunks.push(e.data); });
    mediaRecorder.addEventListener('stop', () => {
      const recordedType = mediaRecorder.mimeType || chunks[0]?.type || 'audio/webm';
      recordingStream?.getTracks().forEach(track => track.stop());
      recordingStream = null;
      mediaRecorder = null;
      button.disabled = false;
      button.classList.remove('is-stopping');
      if (!chunks.length) {
        recordedAudio = null;
        updateDiscardButton();
        document.querySelector('#record-title').textContent = 'No audio captured';
        status.textContent = 'Tap the microphone and try again';
        button.setAttribute('aria-label', 'Try recording the voice note again');
        return;
      }
      const extension = recordedType.includes('mp4') ? 'm4a' : 'webm';
      recordedAudio = new File([new Blob(chunks, {type: recordedType})], `voice-note.${extension}`, {type: recordedType});
      document.querySelector('#record-title').textContent = 'Voice note ready';
      status.textContent = 'Tap the arrow to add it, or tap here to record again';
      button.setAttribute('aria-label', 'Record the voice note again');
      button.classList.add('has-recording');
      showReadyWaveform();
      updateDiscardButton();
    });
    mediaRecorder.start(250);
    recordedAudio = null;
    pendingNoteKey = null;
    document.querySelector('#audio').value = '';
    document.querySelector('#transcript').value = '';
    result.classList.add('hidden');
    updateDiscardButton();
    button.classList.add('is-recording');
    button.classList.remove('is-stopping', 'has-recording');
    form.classList.add('is-recording');
    button.setAttribute('aria-pressed', 'true');
    button.setAttribute('aria-label', 'Stop recording');
    document.querySelector('#record-title').textContent = 'Listening — tap to stop';
    status.textContent = 'The bars move with your real voice';
    recordingStartedAt = Date.now();
    setRecordTime();
    recordingTimer = setInterval(setRecordTime, 1000);
    startAudioMeter(recordingStream);
  } catch (_error) {
    recordingStream?.getTracks().forEach(track => track.stop());
    recordingStream = null;
    resetRecorderUi();
    document.querySelector('#record-title').textContent = 'Microphone access needed';
    status.textContent = 'Allow microphone access in your browser, then tap again';
  }
});

document.querySelector('#audio').addEventListener('change', () => {
  recordedAudio = null;
  pendingNoteKey = null;
  resetRecorderUi();
  updateDiscardButton();
});

document.querySelector('#transcript').addEventListener('input', () => {
  if (document.querySelector('#transcript').value.trim()) {
    recordedAudio = null;
    pendingNoteKey = null;
    resetRecorderUi();
  }
  updateDiscardButton();
});

document.querySelector('#discard-note').addEventListener('click', () => {
  recordedAudio = null;
  pendingNoteKey = null;
  document.querySelector('#audio').value = '';
  document.querySelector('#transcript').value = '';
  document.querySelector('.alternate-entry').open = false;
  result.textContent = '';
  result.classList.add('hidden');
  resetRecorderUi();
  updateDiscardButton();
  showToast('Note discarded');
});

function openAuthPanel(panelId) {
  for (const panel of document.querySelectorAll('.auth-panel')) panel.classList.toggle('hidden', panel.id !== panelId);
  for (const tab of document.querySelectorAll('.auth-tab')) tab.classList.toggle('active', tab.dataset.authPanel === panelId);
  document.querySelector('#auth-error').classList.add('hidden');
}

for (const trigger of document.querySelectorAll('[data-auth-panel]')) {
  trigger.addEventListener('click', () => openAuthPanel(trigger.dataset.authPanel));
}

for (const toggle of document.querySelectorAll('.password-toggle')) {
  toggle.addEventListener('click', () => {
    const input = toggle.closest('.password-field').querySelector('input');
    const reveal = input.type === 'password';
    input.type = reveal ? 'text' : 'password';
    toggle.textContent = reveal ? 'Hide' : 'Show';
    toggle.setAttribute('aria-label', `${reveal ? 'Hide' : 'Show'} password`);
    toggle.setAttribute('aria-pressed', String(reveal));
  });
}

const sectionLinks = [...document.querySelectorAll('.desktop-nav a, .mobile-nav a')];
const trackedSections = ['new-entry', 'customers', 'passbook']
  .map(id => document.getElementById(id));

function updateActiveNavigation() {
  const marker = window.innerHeight * .34;
  let activeId = 'overview';
  for (const section of trackedSections) {
    if (section.getBoundingClientRect().top <= marker) activeId = section.id;
  }
  if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 20) activeId = 'passbook';
  for (const link of sectionLinks) {
    link.classList.toggle('active', link.getAttribute('href') === `#${activeId}`);
  }
}

window.addEventListener('scroll', updateActiveNavigation, {passive: true});
window.addEventListener('resize', updateActiveNavigation);
updateActiveNavigation();

document.querySelector('#transactions').addEventListener('click', async event => {
  const button = event.target.closest('.delete-transaction');
  if (!button || !confirm('Delete this transaction?')) return;
  const response = await api(`/api/transactions/${button.dataset.id}`, {method: 'DELETE'});
  if (response.ok) {
    await refresh();
    showToast('Transaction deleted');
  } else {
    showToast('Could not delete the transaction', 'error');
  }
});

document.querySelector('#review-list').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.target.closest('.review-item');
  if (form.dataset.submitting === 'true') return;
  form.dataset.submitting = 'true';
  form.dataset.idempotencyKey ||= newIdempotencyKey();
  const saveButton = form.querySelector('[type="submit"]');
  saveButton.disabled = true;
  const values = Object.fromEntries(new FormData(form));
  const payload = {...values, amount_rupees: Number(values.amount_rupees), confidence: 1};
  payload.due_day ||= null; payload.context ||= null;
  try {
    const response = await api(`/api/reviews/${form.dataset.id}/approve`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Idempotency-Key': form.dataset.idempotencyKey},
      body: JSON.stringify(payload)
    });
    if (response.ok) {
      await refresh();
      showToast('Corrected entry saved');
    } else {
      showToast('Could not save the corrected entry', 'error');
    }
  } finally {
    form.dataset.submitting = 'false';
    saveButton.disabled = false;
  }
});

document.querySelector('#review-list').addEventListener('input', event => {
  const form = event.target.closest('.review-item');
  if (form?.dataset.submitting !== 'true') delete form.dataset.idempotencyKey;
});

document.querySelector('#review-list').addEventListener('click', async event => {
  const button = event.target.closest('.reject-review');
  if (!button) return;
  const form = button.closest('.review-item');
  const response = await api(`/api/reviews/${form.dataset.id}`, {method: 'DELETE'});
  if (response.ok) {
    await refresh();
    showToast('Review discarded');
  } else {
    showToast('Could not discard the review', 'error');
  }
});

for (const [formId, endpoint] of [['login-form', '/api/auth/login'], ['register-form', '/api/auth/register']]) {
  document.querySelector(`#${formId}`).addEventListener('submit', async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    const response = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    const body = await response.json();
    if (!response.ok) { showAuth(formatApiError(body)); return; }
    event.currentTarget.reset();
    await showApp(body, formId === 'register-form' ? 'Account created successfully. Your shop ledger is ready.' : '');
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
