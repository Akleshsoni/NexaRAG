from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["chat-ui"])

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DocuMind</title>
<style>
  

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22263a;
    --border: #2e3248;
    --accent: #6c63ff;
    --accent-glow: rgba(108,99,255,0.15);
    --text: #e8eaf0;
    --text-muted: #7b82a0;
    --green: #4ade80;
    --red: #f87171;
    --mono: 'Consolas', 'Courier New', monospace;
    --sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 18px 32px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }

  .logo {
    width: 32px; height: 32px;
    background: var(--accent);
    border-radius: 8px;
    display: grid; place-items: center;
    font-size: 16px;
  }

  header h1 { font-size: 18px; font-weight: 600; letter-spacing: -0.3px; }
  header span { font-size: 12px; color: var(--text-muted); margin-left: 4px; }

  .status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    margin-left: auto;
    box-shadow: 0 0 8px var(--green);
  }

  /* ── Layout ── */
  .layout {
    display: flex;
    flex: 1;
    overflow: hidden;
    height: calc(100vh - 61px);
  }

  /* ── Sidebar ── */
  aside {
    width: 280px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    padding: 20px 16px;
    gap: 8px;
    flex-shrink: 0;
  }

  aside h2 {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding: 0 8px;
    margin-bottom: 4px;
  }

  .token-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .token-section label {
    font-size: 12px;
    color: var(--text-muted);
    padding: 0 8px;
  }

  .token-input {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 12px;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text);
    width: 100%;
    outline: none;
    transition: border-color 0.2s;
  }

  .token-input:focus { border-color: var(--accent); }
  .token-input::placeholder { color: var(--text-muted); }

  .token-status {
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .token-status.valid { color: var(--green); }
  .token-status.empty { color: var(--text-muted); }

  .divider {
    height: 1px;
    background: var(--border);
    margin: 8px 0;
  }

  .hint-box {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.6;
  }

  .hint-box strong { color: var(--text); display: block; margin-bottom: 4px; }

  /* ── Chat Area ── */
  main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    scroll-behavior: smooth;
  }

  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-track { background: transparent; }
  .messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--text-muted);
    text-align: center;
  }

  .empty-state .icon { font-size: 40px; opacity: 0.5; }
  .empty-state h3 { font-size: 16px; font-weight: 500; color: var(--text); }
  .empty-state p { font-size: 14px; max-width: 300px; line-height: 1.6; }

  .quick-questions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    margin-top: 8px;
  }

  .quick-q {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 13px;
    color: var(--text);
    cursor: pointer;
    transition: all 0.2s;
  }

  .quick-q:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-glow);
  }

  /* ── Messages ── */
  .msg {
    display: flex;
    gap: 12px;
    animation: fadeIn 0.3s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .msg-avatar {
    width: 32px; height: 32px;
    border-radius: 8px;
    display: grid; place-items: center;
    font-size: 14px;
    flex-shrink: 0;
    margin-top: 2px;
  }

  .msg.user .msg-avatar { background: var(--surface2); border: 1px solid var(--border); }
  .msg.bot .msg-avatar { background: var(--accent); }

  .msg-content { flex: 1; }

  .msg-name {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 6px;
  }

  .msg-text {
    font-size: 14px;
    line-height: 1.7;
    color: var(--text);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .msg.user .msg-text {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 0 12px 12px 12px;
    padding: 10px 14px;
    display: inline-block;
  }

  .cursor {
    display: inline-block;
    width: 2px; height: 16px;
    background: var(--accent);
    margin-left: 2px;
    vertical-align: middle;
    animation: blink 0.8s infinite;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  .sources {
    margin-top: 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .source-chip {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-family: var(--mono);
    color: var(--text-muted);
  }

  .latency {
    margin-top: 8px;
    font-size: 11px;
    color: var(--text-muted);
    font-family: var(--mono);
  }

  /* ── Input Bar ── */
  .input-bar {
    border-top: 1px solid var(--border);
    padding: 16px 32px;
    background: var(--surface);
    display: flex;
    gap: 12px;
    align-items: flex-end;
  }

  .input-wrap {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
    display: flex;
    align-items: flex-end;
    gap: 8px;
    transition: border-color 0.2s;
  }

  .input-wrap:focus-within { border-color: var(--accent); }

  #question {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    resize: none;
    max-height: 120px;
    min-height: 24px;
    line-height: 1.5;
  }

  #question::placeholder { color: var(--text-muted); }

  .send-btn {
    width: 36px; height: 36px;
    background: var(--accent);
    border: none;
    border-radius: 8px;
    color: white;
    cursor: pointer;
    display: grid; place-items: center;
    font-size: 16px;
    flex-shrink: 0;
    transition: all 0.2s;
    align-self: flex-end;
  }

  .send-btn:hover { background: #5a52d5; transform: scale(1.05); }
  .send-btn:disabled { background: var(--border); cursor: not-allowed; transform: none; }

  .error-toast {
    position: fixed;
    bottom: 90px; right: 24px;
    background: #2d1b1b;
    border: 1px solid var(--red);
    color: var(--red);
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
    display: none;
    z-index: 100;
  }
</style>
</head>
<body>

<header>
  <div class="logo">🧠</div>
  <h1>DocuMind <span>RAG Chat</span></h1>
  <div class="status-dot" id="statusDot" title="System online"></div>
</header>

<div class="layout">
  <aside>
    <h2>Configuration</h2>
    <div class="token-section">
      <label>Access Token</label>
      <input type="password" id="token" class="token-input" placeholder="Paste JWT token..." oninput="checkToken()" />
      <div class="token-status empty" id="tokenStatus">⬤ No token</div>
    </div>

    <div class="divider"></div>

    <div class="hint-box">
      <strong>💡 How to use</strong>
      1. Paste your JWT token above<br>
      2. Type a question below<br>
      3. Press Enter or click Send<br><br>
      Answers stream in real-time from your uploaded documents.
    </div>
  </aside>

  <main>
    <div class="messages" id="messages">
      <div class="empty-state" id="emptyState">
        <div class="icon">🔍</div>
        <h3>Ask your documents anything</h3>
        <p>DocuMind searches your uploaded files and streams answers in real time.</p>
        <div class="quick-questions">
          <button class="quick-q" onclick="fillQ('What is a stack?')">What is a stack?</button>
          <button class="quick-q" onclick="fillQ('Explain linked lists')">Explain linked lists</button>
          <button class="quick-q" onclick="fillQ('What is BFS vs DFS?')">BFS vs DFS?</button>
          <button class="quick-q" onclick="fillQ('Time complexity of sorting algorithms')">Sorting complexity</button>
        </div>
      </div>
    </div>

    <div class="input-bar">
      <div class="input-wrap">
        <textarea id="question" rows="1" placeholder="Ask something about your documents..." onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
      </div>
      <button class="send-btn" id="sendBtn" onclick="ask()" title="Send (Enter)">➤</button>
    </div>
  </main>
</div>

<div class="error-toast" id="errorToast"></div>

<script>
function checkToken() {
  const t = document.getElementById('token').value.trim();
  const el = document.getElementById('tokenStatus');
  if (t.length > 20) {
    el.textContent = '⬤ Token set';
    el.className = 'token-status valid';
  } else {
    el.textContent = '⬤ No token';
    el.className = 'token-status empty';
  }
}

function fillQ(q) {
  document.getElementById('question').value = q;
  autoResize(document.getElementById('question'));
  document.getElementById('question').focus();
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); }
}

function showError(msg) {
  const t = document.getElementById('errorToast');
  t.textContent = '⚠ ' + msg;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 4000);
}

function addMsg(role, text) {
  const empty = document.getElementById('emptyState');
  if (empty) empty.remove();

  const msgs = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  const avatar = role === 'user' ? '👤' : '🧠';
  const name = role === 'user' ? 'You' : 'DocuMind';
  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-content">
      <div class="msg-name">${name}</div>
      <div class="msg-text" id="msgText_${Date.now()}"></div>
    </div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div.querySelector('.msg-text');
}

async function ask() {
  const token = document.getElementById('token').value.trim();
  const questionEl = document.getElementById('question');
  const question = questionEl.value.trim();
  const sendBtn = document.getElementById('sendBtn');

  if (!token) { showError('Please paste your JWT token in the sidebar'); return; }
  if (!question) { showError('Please type a question first'); return; }

  addMsg('user', question);
  questionEl.value = '';
  autoResize(questionEl);
  sendBtn.disabled = true;

  const botEl = addMsg('bot', '');
  const cursor = document.createElement('span');
  cursor.className = 'cursor';
  botEl.appendChild(cursor);

  const start = performance.now();
  let fullText = '';
  let chunkIds = [];

  try {
    const response = await fetch('/query/stream', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, top_k: 5, stream: true }),
    });

    if (!response.ok) {
      botEl.textContent = 'Error ' + response.status + ' — check logs';
      sendBtn.disabled = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      let value, done;
      try { ({ value, done } = await reader.read()); } catch(e) { break; }
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\\n\\n');
      buffer = parts.pop();

      for (const part of parts) {
        const lines = part.split('\\n');
        const eventLine = lines.find(l => l.startsWith('event:'));
        const dataLine = lines.find(l => l.startsWith('data:'));
        if (!dataLine) continue;
        const data = dataLine.slice(5).trim();
        const event = eventLine ? eventLine.slice(6).trim() : 'token';

        if (event === 'token') {
          fullText += data;
          botEl.textContent = fullText;
          botEl.appendChild(cursor);
          document.getElementById('messages').scrollTop = 99999;
        } else if (event === 'done') {
          try { chunkIds = JSON.parse(data); } catch(e) {}
        }
      }
    }
  } catch(e) {
    if (!fullText) botEl.textContent = 'Connection error: ' + e.message;
  }

  cursor.remove();
  if (!fullText) botEl.textContent = 'No response received.';

  const elapsed = Math.round(performance.now() - start);
  const meta = document.createElement('div');
  meta.className = 'latency';
  meta.textContent = elapsed + 'ms · ' + chunkIds.length + ' sources';
  botEl.parentElement.appendChild(meta);

  sendBtn.disabled = false;
  document.getElementById('question').focus();
}
</script>
</body>
</html>"""


@router.get("/chat", response_class=HTMLResponse)
async def chat_ui():
    return CHAT_HTML
