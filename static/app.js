/* ─── VANEGAS Web Client ─────────────────────────────────────────────────── */

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
const CLIENT_ID = Math.random().toString(36).slice(2, 10);

let socket = null;
let isStreaming = false;
let password = '';
let currentAssistantBubble = null;
let currentAssistantText = '';

// Configure marked.js
marked.setOptions({
  breaks: true,
  gfm: true,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  }
});

// ─── DOM refs ────────────────────────────────────────────────────────────────
const loginOverlay    = document.getElementById('loginOverlay');
const appEl           = document.getElementById('app');
const passwordInput   = document.getElementById('passwordInput');
const loginBtn        = document.getElementById('loginBtn');
const loginError      = document.getElementById('loginError');
const chatMessages    = document.getElementById('chatMessages');
const messageInput    = document.getElementById('messageInput');
const sendBtn         = document.getElementById('sendBtn');
const typingIndicator = document.getElementById('typingIndicator');
const toolIndicator   = document.getElementById('toolIndicator');
const toolName        = document.getElementById('toolName');
const tokensToday     = document.getElementById('tokensToday');
const costToday       = document.getElementById('costToday');
const statusDot       = document.getElementById('statusDot');
const clearChatBtn    = document.getElementById('clearChatBtn');
const refreshDashboard = document.getElementById('refreshDashboard');
const summaryBtn      = document.getElementById('summaryBtn');

// ─── Login ────────────────────────────────────────────────────────────────────
loginBtn.addEventListener('click', doLogin);
passwordInput.addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

async function doLogin() {
  const pw = passwordInput.value.trim();
  if (!pw) return;
  try {
    const res = await fetch('/api/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw })
    });
    if (!res.ok) throw new Error('wrong');
    password = pw;
    loginOverlay.classList.add('hidden');
    appEl.classList.remove('hidden');
    connectWebSocket();
    loadStatus();
  } catch {
    loginError.classList.remove('hidden');
    passwordInput.value = '';
    passwordInput.focus();
  }
}

// ─── WebSocket ────────────────────────────────────────────────────────────────
function connectWebSocket() {
  setStatus('connecting');
  socket = new WebSocket(`${WS_URL}/${CLIENT_ID}`);

  socket.onopen = () => {
    socket.send(JSON.stringify({ type: 'auth', password }));
  };

  socket.onmessage = e => {
    const event = JSON.parse(e.data);
    handleEvent(event);
  };

  socket.onclose = () => {
    setStatus('offline');
    sendBtn.disabled = true;
    setTimeout(connectWebSocket, 4000);
  };

  socket.onerror = () => {
    setStatus('offline');
  };
}

function handleEvent(event) {
  switch (event.type) {
    case 'auth_ok':
      setStatus('online');
      sendBtn.disabled = false;
      break;

    case 'token':
      if (!currentAssistantBubble) {
        currentAssistantBubble = createAssistantBubble();
        typingIndicator.classList.remove('hidden');
      }
      currentAssistantText += event.content;
      renderAssistantBubble(currentAssistantText);
      scrollBottom();
      break;

    case 'tool_start':
      showToolIndicator(event.tool);
      appendToolPill(event.tool, false);
      break;

    case 'tool_end':
      appendToolPill(event.tool, true);
      break;

    case 'done':
      finalizeResponse(event.total_tokens);
      break;

    case 'error':
      hideToolIndicator();
      appendErrorMessage(event.content);
      endStreaming();
      break;
  }
}

// ─── Chat helpers ─────────────────────────────────────────────────────────────
function sendMessage() {
  const text = messageInput.value.trim();
  if (!text || isStreaming) return;

  appendUserMessage(text);
  messageInput.value = '';
  resizeTextarea();

  socket.send(JSON.stringify({ type: 'message', content: text }));
  startStreaming();
}

function startStreaming() {
  isStreaming = true;
  sendBtn.disabled = true;
  currentAssistantBubble = null;
  currentAssistantText = '';
}

function endStreaming() {
  isStreaming = false;
  sendBtn.disabled = false;
  typingIndicator.classList.add('hidden');
  hideToolIndicator();
  currentAssistantBubble = null;
  currentAssistantText = '';
}

function finalizeResponse(totalTokens) {
  endStreaming();
  // Update sidebar token count
  if (totalTokens) {
    loadStatus();
  }
}

function appendUserMessage(text) {
  const el = document.createElement('div');
  el.className = 'message user-msg';
  el.innerHTML = `
    <div class="msg-avatar">👤</div>
    <div class="msg-body">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
  `;
  chatMessages.appendChild(el);
  scrollBottom();
}

function createAssistantBubble() {
  const el = document.createElement('div');
  el.className = 'message assistant-msg';
  el.innerHTML = `
    <div class="msg-avatar">⚡</div>
    <div class="msg-body"></div>
  `;
  chatMessages.appendChild(el);
  scrollBottom();
  return el.querySelector('.msg-body');
}

function renderAssistantBubble(text) {
  if (!currentAssistantBubble) return;
  currentAssistantBubble.innerHTML = marked.parse(text);
  // Highlight code blocks
  currentAssistantBubble.querySelectorAll('pre code').forEach(el => {
    hljs.highlightElement(el);
  });
}

function appendToolPill(tool, done) {
  if (!currentAssistantBubble) {
    currentAssistantBubble = createAssistantBubble();
  }
  const pill = document.createElement('div');
  pill.className = `tool-pill${done ? ' done' : ''}`;
  pill.innerHTML = done
    ? `✓ ${tool}`
    : `⟳ ${tool}`;
  // Insert before the text content or append
  currentAssistantBubble.insertBefore(pill, currentAssistantBubble.firstChild);
  scrollBottom();
}

function appendErrorMessage(content) {
  const el = document.createElement('div');
  el.className = 'message assistant-msg';
  el.innerHTML = `
    <div class="msg-avatar">⚡</div>
    <div class="msg-body" style="border-color:rgba(248,81,73,.3);background:rgba(248,81,73,.06)">
      ${escapeHtml(content)}
    </div>
  `;
  chatMessages.appendChild(el);
  scrollBottom();
}

function showToolIndicator(tool) {
  toolName.textContent = `Usando herramienta: ${tool}`;
  toolIndicator.classList.remove('hidden');
}

function hideToolIndicator() {
  toolIndicator.classList.add('hidden');
}

function scrollBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ─── Input handling ───────────────────────────────────────────────────────────
sendBtn.addEventListener('click', sendMessage);

messageInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

messageInput.addEventListener('input', resizeTextarea);

function resizeTextarea() {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + 'px';
}

clearChatBtn.addEventListener('click', () => {
  chatMessages.innerHTML = '';
  appendUserMessage(''); // will be cleared below
  chatMessages.innerHTML = `
    <div class="message assistant-msg">
      <div class="msg-avatar">⚡</div>
      <div class="msg-body"><p>Chat limpiado. ¿En qué te ayudo?</p></div>
    </div>
  `;
});

// ─── Panel navigation ─────────────────────────────────────────────────────────
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.panel;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => { p.classList.remove('active'); p.classList.add('hidden'); });
    btn.classList.add('active');
    const panel = document.getElementById(`panel${capitalize(target)}`);
    if (panel) { panel.classList.remove('hidden'); panel.classList.add('active'); }
    if (target === 'dashboard') loadDashboard();
  });
});

function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

// ─── Status & Dashboard ───────────────────────────────────────────────────────
function setStatus(state) {
  statusDot.className = 'stat-value status-dot ' + state;
  const labels = { online: '● Conectado', offline: '● Desconectado', connecting: '● Conectando' };
  statusDot.textContent = labels[state] || '● —';
}

async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    if (data.ok) {
      tokensToday.textContent = fmtNum(data.tokens_hoy);
      costToday.textContent = '$' + (data.costo_hoy || 0).toFixed(3);
    }
  } catch {}
}

async function loadDashboard() {
  await Promise.all([loadTokenStats(), loadSystemStatus()]);
}

async function loadTokenStats() {
  try {
    const res = await fetch('/api/tokens?days=7');
    const data = await res.json();
    if (!data.ok) return;
    const d = data.data;

    document.getElementById('dashTokensToday').textContent = fmtNum(d.today_tokens || 0);
    document.getElementById('dashTokens7d').textContent = fmtNum(d.total_tokens || 0);
    document.getElementById('dashCost7d').textContent = '$' + (d.total_cost || 0).toFixed(3);

    // Draw bars for last 7 days
    const bars = document.getElementById('tokenChart');
    bars.innerHTML = '';
    const daily = d.daily || [];
    const max = Math.max(...daily.map(x => x.tokens), 1);
    daily.forEach(row => {
      const pct = Math.round((row.tokens / max) * 100);
      bars.innerHTML += `
        <div class="bar-row">
          <span class="bar-label">${row.date.slice(5)}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
          <span class="bar-count">${fmtNum(row.tokens)}</span>
        </div>`;
    });
  } catch {}
}

async function loadSystemStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    if (!data.ok) return;
    const el = document.getElementById('systemStatus');
    el.innerHTML = `
      <div class="status-row">
        <span>Agente Claude</span>
        <span class="badge ${data.agent ? 'ok' : 'error'}">${data.agent ? 'Activo' : 'Error'}</span>
      </div>
      <div class="status-row">
        <span>Monitor Proactivo</span>
        <span class="badge ${data.monitor ? 'ok' : 'warning'}">${data.monitor ? 'Activo' : 'Inactivo'}</span>
      </div>
      <div class="status-row">
        <span>Telegram Alertas</span>
        <span class="badge ${data.telegram ? 'ok' : 'warning'}">${data.telegram ? 'Activo' : 'Inactivo'}</span>
      </div>
    `;
  } catch {}
}

refreshDashboard?.addEventListener('click', loadDashboard);

summaryBtn?.addEventListener('click', async () => {
  summaryBtn.disabled = true;
  summaryBtn.textContent = '⏳ Generando resumen...';
  try {
    const res = await fetch('/api/daily-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    });
    const data = await res.json();
    if (data.ok) {
      // Switch to chat panel and show summary
      document.querySelector('[data-panel="chat"]').click();
      const el = document.createElement('div');
      el.className = 'message assistant-msg';
      el.innerHTML = `
        <div class="msg-avatar">⚡</div>
        <div class="msg-body">${marked.parse(data.summary)}</div>
      `;
      chatMessages.appendChild(el);
      scrollBottom();
    }
  } catch {}
  summaryBtn.disabled = false;
  summaryBtn.textContent = '📋 Generar resumen del día';
});

// ─── Number formatter ────────────────────────────────────────────────────────
function fmtNum(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}
