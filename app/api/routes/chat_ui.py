from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["chat-ui"])

CHAT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DocuMind</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f1117;--sf:#1a1d27;--sf2:#22263a;--bd:#2e3248;
  --ac:#6c63ff;--ac2:#4ade80;--tx:#e8eaf0;--mu:#7b82a0;
  --rd:#f87171;--yw:#fbbf24;
  --mono:Consolas,monospace;--sans:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
body{background:var(--bg);color:var(--tx);font-family:var(--sans);min-height:100vh;display:flex;flex-direction:column}

/* LOGIN PAGE */
#loginPage{flex:1;display:flex;align-items:center;justify-content:center}
.login-card{background:var(--sf);border:1px solid var(--bd);border-radius:14px;padding:36px 32px;width:360px;display:flex;flex-direction:column;gap:16px}
.login-card h2{font-size:20px;font-weight:700;text-align:center}
.login-card p{font-size:13px;color:var(--mu);text-align:center}
.field{display:flex;flex-direction:column;gap:5px}
.field label{font-size:12px;color:var(--mu)}
.field input{background:var(--sf2);border:1px solid var(--bd);border-radius:7px;padding:9px 12px;font-size:13px;color:var(--tx);outline:none;transition:border-color .2s}
.field input:focus{border-color:var(--ac)}
.login-btn{background:var(--ac);color:#fff;border:none;border-radius:8px;padding:11px;font-size:14px;font-weight:600;cursor:pointer;transition:background .2s}
.login-btn:hover{background:#5a52d5}
.login-err{font-size:12px;color:var(--rd);text-align:center;min-height:16px}
.login-toggle{font-size:12px;color:var(--mu);text-align:center;cursor:pointer}
.login-toggle span{color:var(--ac)}

/* APP */
#app{display:none;flex-direction:column;flex:1}
header{display:flex;align-items:center;gap:10px;padding:12px 20px;border-bottom:1px solid var(--bd);background:var(--sf);flex-shrink:0}
.logo{width:28px;height:28px;background:var(--ac);border-radius:7px;display:grid;place-items:center;font-size:14px}
header h1{font-size:15px;font-weight:600}
header span{font-size:11px;color:var(--mu);margin-left:3px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ac2);margin-left:auto;box-shadow:0 0 5px var(--ac2)}
.user-info{font-size:11px;color:var(--mu);margin-left:8px}
.logout-btn{background:none;border:1px solid var(--bd);border-radius:5px;padding:4px 10px;font-size:11px;color:var(--mu);cursor:pointer;transition:all .2s}
.logout-btn:hover{border-color:var(--rd);color:var(--rd)}
.layout{display:flex;flex:1;overflow:hidden;height:calc(100vh - 53px)}

/* SIDEBAR */
aside{width:250px;background:var(--sf);border-right:1px solid var(--bd);display:flex;flex-direction:column;overflow-y:auto;flex-shrink:0}
.side-sec{padding:12px 12px 0}
.slabel{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--mu);margin-bottom:7px}
.nav-btn{display:flex;align-items:center;gap:7px;padding:7px 8px;border-radius:6px;cursor:pointer;font-size:12px;color:var(--mu);transition:all .2s;border:none;background:none;width:100%;text-align:left}
.nav-btn:hover,.nav-btn.active{background:var(--sf2);color:var(--tx)}
.nav-btn .ic{font-size:14px}
.div{height:1px;background:var(--bd);margin:10px 12px}
.upload-area{border:2px dashed var(--bd);border-radius:7px;padding:12px;text-align:center;cursor:pointer;transition:all .2s;margin:0 12px}
.upload-area:hover{border-color:var(--ac)}
.upload-area input{display:none}
.upload-area p{font-size:11px;color:var(--mu);margin-top:3px}
.doc-list{padding:6px 12px 12px;display:flex;flex-direction:column;gap:4px}
.doc-item{background:var(--sf2);border:1px solid var(--bd);border-radius:6px;padding:7px 9px;font-size:11px;display:flex;align-items:flex-start;gap:7px;position:relative}
.doc-info{flex:1;min-width:0}
.doc-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;color:var(--tx)}
.doc-st{font-size:10px;padding:1px 5px;border-radius:3px;font-weight:600;display:inline-block;margin-top:2px}
.doc-st.ready{background:#14532d;color:var(--ac2)}
.doc-st.pending,.doc-st.processing{background:#451a03;color:var(--yw)}
.doc-st.failed{background:#450a0a;color:var(--rd)}
.doc-sug{font-size:10px;color:var(--ac);cursor:pointer;margin-top:2px}
.doc-sug:hover{text-decoration:underline}
.doc-cmp{font-size:10px;cursor:pointer;color:var(--mu);margin-top:2px}
.doc-cmp.selected{color:var(--ac2);font-weight:600}
.doc-del{background:none;border:none;color:var(--mu);cursor:pointer;font-size:12px;padding:1px 3px;border-radius:3px;transition:all .2s;flex-shrink:0}
.doc-del:hover{background:#450a0a;color:var(--rd)}
.hint-box{background:var(--sf2);border:1px solid var(--bd);border-radius:7px;padding:10px 11px;font-size:11px;color:var(--mu);line-height:1.6;margin:0 12px 12px}
.hint-box strong{color:var(--tx);display:block;margin-bottom:2px}

/* MAIN */
main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.panel{flex:1;overflow-y:auto;padding:18px 24px;display:flex;flex-direction:column;gap:14px}
.panel::-webkit-scrollbar{width:3px}
.panel::-webkit-scrollbar-thumb{background:var(--bd);border-radius:2px}
.ph{font-size:13px;font-weight:600;color:var(--tx);margin-bottom:2px}

/* CHAT */
.empty-state{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;color:var(--mu);text-align:center}
.ei{font-size:34px;opacity:.4}
.empty-state h3{font-size:14px;font-weight:500;color:var(--tx)}
.empty-state p{font-size:12px;max-width:260px;line-height:1.6}
.qbtns{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:5px}
.qbtn{background:var(--sf);border:1px solid var(--bd);border-radius:14px;padding:4px 11px;font-size:11px;color:var(--tx);cursor:pointer;transition:all .2s}
.qbtn:hover{border-color:var(--ac);color:var(--ac)}

/* MESSAGES */
.msg{display:flex;gap:9px;animation:fi .22s ease}
@keyframes fi{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
.av{width:28px;height:28px;border-radius:7px;display:grid;place-items:center;font-size:12px;flex-shrink:0;margin-top:2px}
.msg.user .av{background:var(--sf2);border:1px solid var(--bd)}
.msg.bot .av{background:var(--ac)}
.mb{flex:1}
.mn{font-size:10px;font-weight:600;color:var(--mu);margin-bottom:4px}
.mt{
  font-size:13px;
  line-height:1.75;
  color:var(--tx);
  white-space:pre-wrap;
  word-break:break-word;
  background:var(--sf);
  border:1px solid var(--bd);
  border-radius:0 10px 10px 10px;
  padding:10px 13px;
  max-width:760px;
  box-shadow:0 4px 14px rgba(0,0,0,.12);
}
.msg.user .mt{background:var(--sf2);border:1px solid var(--bd);border-radius:0 9px 9px 9px;padding:7px 11px;display:inline-block}
.mm{margin-top:5px;font-size:10px;color:var(--mu);font-family:var(--mono);display:flex;align-items:center;gap:8px}
.copy-btn{background:none;border:1px solid var(--bd);border-radius:4px;padding:2px 7px;font-size:10px;color:var(--mu);cursor:pointer;transition:all .2s}
.copy-btn:hover{border-color:var(--ac);color:var(--ac)}
.src-list{
  margin-top:10px;
  display:flex;
  flex-direction:column;
  gap:6px;
  max-width:620px;
}

.src-list::before{
  content:"Sources";
  font-size:10px;
  font-weight:700;
  text-transform:uppercase;
  letter-spacing:.08em;
  color:var(--mu);
  margin-bottom:1px;
}

.src-chip{
  background:linear-gradient(135deg,var(--sf2),var(--sf));
  border:1px solid var(--bd);
  border-radius:8px;
  padding:8px 10px;
  font-size:11px;
  cursor:pointer;
  transition:all .2s ease;
  display:flex;
  align-items:center;
  gap:8px;
  min-height:36px;
}

.src-chip:hover{
  border-color:var(--ac);
  transform:translateX(2px);
}

.sc-i{
  color:var(--ac);
  font-weight:700;
  font-family:var(--mono);
  min-width:22px;
}

.sc-f{
  color:var(--tx);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  flex:1;
  min-width:0;
}

.sc-s{
  margin-left:auto;
  color:var(--ac2);
  font-family:var(--mono);
  font-size:10px;
  font-weight:600;
  background:rgba(74,222,128,.08);
  border:1px solid rgba(74,222,128,.2);
  padding:2px 6px;
  border-radius:4px;
}
.typing{display:flex;gap:3px;align-items:center;padding:5px 0}
.typing span{width:5px;height:5px;border-radius:50%;background:var(--ac);animation:bn 1s infinite}
.typing span:nth-child(2){animation-delay:.2s}.typing span:nth-child(3){animation-delay:.4s}
@keyframes bn{0%,80%,100%{transform:scale(.7);opacity:.5}40%{transform:scale(1);opacity:1}}

/* COMPARE MODE */
.cmp-bar{background:var(--sf2);border:1px solid var(--bd);border-radius:7px;padding:8px 12px;font-size:12px;display:flex;align-items:center;gap:8px;flex-shrink:0;margin:0 24px}
.cmp-bar .cmp-docs{flex:1;color:var(--mu)}
.cmp-bar .cmp-docs span{color:var(--ac2);font-weight:600}
.cmp-cancel{background:none;border:1px solid var(--bd);border-radius:5px;padding:3px 9px;font-size:11px;color:var(--mu);cursor:pointer}
.cmp-cancel:hover{border-color:var(--rd);color:var(--rd)}

/* HISTORY */
.hi{background:var(--sf2);border:1px solid var(--bd);border-radius:7px;padding:10px;display:flex;flex-direction:column;gap:5px}
.hi-q{font-size:12px;font-weight:500;color:var(--tx)}
.hi-a{font-size:11px;color:var(--mu);line-height:1.5;max-height:50px;overflow:hidden}
.hi-m{font-size:10px;color:var(--mu);font-family:var(--mono);display:flex;gap:8px}
.pg{display:flex;align-items:center;gap:6px;justify-content:center;margin-top:8px}
.pg-btn{background:var(--sf2);border:1px solid var(--bd);border-radius:5px;padding:4px 10px;font-size:11px;color:var(--tx);cursor:pointer;transition:all .2s}
.pg-btn:hover:not(:disabled){border-color:var(--ac)}
.pg-btn:disabled{opacity:.4;cursor:not-allowed}
.pg-info{font-size:11px;color:var(--mu)}

/* STATS */
.stats-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px}
.sc{background:var(--sf2);border:1px solid var(--bd);border-radius:8px;padding:14px}
.sv{font-size:22px;font-weight:700;color:var(--ac)}
.sl{font-size:10px;color:var(--mu);margin-top:2px}

/* INPUT BAR */
.input-bar{border-top:1px solid var(--bd);padding:10px 20px;background:var(--sf);display:flex;gap:9px;align-items:flex-end;flex-shrink:0}
.iw{flex:1;background:var(--sf2);border:1px solid var(--bd);border-radius:9px;padding:9px 13px;display:flex;align-items:flex-end;transition:border-color .2s}
.iw:focus-within{border-color:var(--ac)}
#question{flex:1;background:transparent;border:none;outline:none;color:var(--tx);font-family:var(--sans);font-size:13px;resize:none;max-height:90px;min-height:20px;line-height:1.5}
#question::placeholder{color:var(--mu)}
.sbtn{width:32px;height:32px;background:var(--ac);border:none;border-radius:7px;color:#fff;cursor:pointer;display:grid;place-items:center;font-size:14px;flex-shrink:0;transition:all .2s;margin-left:9px}
.sbtn:hover{background:#5a52d5}
.sbtn:disabled{background:var(--bd);cursor:not-allowed}

/* MODAL */
.modal{position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;z-index:100;animation:fi .18s}
.modal-box{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:18px;max-width:520px;width:90%;max-height:65vh;overflow-y:auto}
.modal-box h3{font-size:13px;margin-bottom:5px;color:var(--tx)}
.modal-meta{font-size:10px;color:var(--mu);margin-bottom:9px;font-family:var(--mono)}
.modal-box pre{font-size:11px;line-height:1.6;color:var(--tx);white-space:pre-wrap;background:var(--sf2);border:1px solid var(--bd);border-radius:6px;padding:10px}
.close-btn{margin-top:10px;background:var(--sf2);border:1px solid var(--bd);border-radius:6px;padding:5px 13px;color:var(--tx);cursor:pointer;font-size:11px}

/* TOAST */
.toast{position:fixed;bottom:70px;right:16px;padding:8px 14px;border-radius:7px;font-size:12px;z-index:200;display:none;animation:fi .2s}
.toast.ok{background:#14532d;border:1px solid var(--ac2);color:var(--ac2)}
.toast.err{background:#450a0a;border:1px solid var(--rd);color:var(--rd)}
.toast.info{background:var(--sf2);border:1px solid var(--bd);color:var(--tx)}
</style>
</head>
<body>

<!-- LOGIN PAGE -->
<div id="loginPage">
  <div style="display:flex;flex-direction:column;align-items:center;gap:20px">
    <div style="text-align:center">
      <div style="font-size:36px">🧠</div>
      <div style="font-size:20px;font-weight:700;margin-top:6px">DocuMind</div>
      <div style="font-size:12px;color:var(--mu)">Multi-tenant RAG Chat</div>
    </div>
    <div class="login-card">
      <div id="loginErr" class="login-err"></div>
      <div class="field"><label>Email</label><input type="email" id="lemail" placeholder="you@example.com" onkeydown="if(event.key==='Enter')doAuth()"/></div>
      <div class="field"><label>Password</label><input type="password" id="lpwd" placeholder="••••••••" onkeydown="if(event.key==='Enter')doAuth()"/></div>
      <div id="signupExtra" style="display:none"><div class="field"><label>Organisation Name</label><input type="text" id="ltenant" placeholder="My Company"/></div></div>
      <button class="login-btn" onclick="doAuth()" id="authBtn">Sign In</button>
      <div class="login-toggle" onclick="toggleMode()" id="modeToggle">No account? <span>Sign up</span></div>
    </div>
  </div>
</div>

<!-- MAIN APP -->
<div id="app">
  <header>
    <div class="logo">🧠</div>
    <h1>DocuMind <span>RAG Chat</span></h1>
    <div class="dot"></div>
    <div class="user-info" id="userEmail"></div>
    <button class="logout-btn" onclick="logout()">Logout</button>
  </header>

  <div class="layout">
    <aside>
      <div class="side-sec">
        <div class="slabel">Navigation</div>
        <button class="nav-btn active" id="nav-chat" onclick="showPanel('chat')"><span class="ic">💬</span> Chat</button>
        <button class="nav-btn" id="nav-compare" onclick="showPanel('compare')"><span class="ic">🔀</span> Compare Docs</button>
        <button class="nav-btn" id="nav-history" onclick="showPanel('history')"><span class="ic">📜</span> History</button>
        <button class="nav-btn" id="nav-stats" onclick="showPanel('stats')"><span class="ic">📊</span> Stats</button>
        <button class="nav-btn" id="nav-docs" onclick="showPanel('docs')"><span class="ic">📁</span> All Documents</button>
      </div>

      <div class="div"></div>

      <div class="side-sec" style="padding-bottom:8px">
        <div class="slabel">Upload Document</div>
        <div class="upload-area" onclick="document.getElementById('fi').click()">
          <input type="file" id="fi" accept=".pdf,.docx" onchange="uploadFile(this)"/>
          <div style="font-size:18px">📄</div>
          <p>PDF or DOCX · Max 10 MB</p>
        </div>
      </div>

      <div class="doc-list" id="docList">
        <div style="font-size:11px;color:var(--mu)">Loading...</div>
      </div>

      <div class="div"></div>
      <div class="hint-box">
        <strong>💡 Tips</strong>
        Ask in English, Hindi, or Hinglish.<br>
        Select docs to compare them.<br>
        Click [1] sources for full text.
      </div>
    </aside>

    <main>
      <!-- Compare mode bar -->
      <div class="cmp-bar" id="cmpBar" style="display:none">
        <div class="cmp-docs">Comparing: <span id="cmpDocNames">0 docs selected</span></div>
        <button class="cmp-cancel" onclick="clearCompare()">✕ Cancel</button>
        <button class="login-btn" style="padding:4px 12px;font-size:11px" onclick="runCompare()">Compare →</button>
      </div>

      <!-- Chat Panel -->
      <div class="panel" id="panel-chat" style="flex-direction:column">
        <div class="empty-state" id="emptyState">
          <div class="ei">🔍</div>
          <h3>Ask your documents anything</h3>
          <p>Upload a PDF or DOCX, then ask questions in English, Hindi, or Hinglish.</p>
          <div class="qbtns">
            <button class="qbtn" onclick="sendQ('What is a stack?')">What is a stack?</button>
            <button class="qbtn" onclick="sendQ('Linked list kya hoti hai?')">Linked list kya hai?</button>
            <button class="qbtn" onclick="sendQ('BFS vs DFS difference?')">BFS vs DFS?</button>
            <button class="qbtn" onclick="sendQ('Sorting algorithms ka complexity?')">Sorting complexity</button>
          </div>
        </div>
      </div>

      <!-- Compare Panel -->
      <div class="panel" id="panel-compare" style="display:none;flex-direction:column">
        <div class="ph">Multi-Document Comparison</div>
        <div style="font-size:12px;color:var(--mu);line-height:1.6">Select 2–5 documents from the sidebar (click the checkbox next to each), then type your comparison question and click Compare.</div>
        <div id="cmpResult"></div>
      </div>

      <!-- History Panel -->
      <div class="panel" id="panel-history" style="display:none;flex-direction:column">
        <div class="ph">Query History</div>
        <div id="historyList"><div style="color:var(--mu);font-size:12px">Loading...</div></div>
        <div class="pg" id="histPg"></div>
      </div>

      <!-- Stats Panel -->
      <div class="panel" id="panel-stats" style="display:none;flex-direction:column">
        <div class="ph">Analytics Dashboard</div>
        <div class="stats-grid" id="statsGrid"><div style="color:var(--mu);font-size:12px">Loading...</div></div>
      </div>

      <!-- Docs Panel -->
      <div class="panel" id="panel-docs" style="display:none;flex-direction:column">
        <div class="ph">All Documents</div>
        <div id="docsDetail"><div style="color:var(--mu);font-size:12px">Loading...</div></div>
        <div class="pg" id="docsPg"></div>
      </div>

      <div class="input-bar">
        <div class="iw">
          <textarea id="question" rows="1" placeholder="Ask in English, Hindi, or Hinglish..." onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
        </div>
        <button class="sbtn" id="sendBtn" onclick="ask()">&#10148;</button>
      </div>
    </main>
  </div>
</div>

<!-- Source Modal -->
<div class="modal" id="srcModal" style="display:none" onclick="if(event.target===this)this.style.display='none'">
  <div class="modal-box">
    <h3 id="mTitle"></h3>
    <div class="modal-meta" id="mMeta"></div>
    <pre id="mText"></pre>
    <button class="close-btn" onclick="document.getElementById('srcModal').style.display='none'">Close</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
// ── Auth ─────────────────────────────────────────────────────────────────────
let isSignup = false;
let currentSources = [];
let compareDocIds = {};  // {doc_id: filename}
let histPage = 1, docsPage = 1;

function toggleMode() {
  isSignup = !isSignup;
  document.getElementById('signupExtra').style.display = isSignup ? '' : 'none';
  document.getElementById('authBtn').textContent = isSignup ? 'Sign Up' : 'Sign In';
  document.getElementById('modeToggle').innerHTML = isSignup
    ? 'Already have an account? <span>Sign in</span>'
    : 'No account? <span>Sign up</span>';
  document.getElementById('loginErr').textContent = '';
}

async function doAuth() {
  const email = document.getElementById('lemail').value.trim();
  const pwd = document.getElementById('lpwd').value;
  const errEl = document.getElementById('loginErr');
  errEl.textContent = '';
  if (!email || !pwd) { errEl.textContent = 'Email and password are required.'; return; }

  let url = '/auth/login';
  let body = { email, password: pwd };
  if (isSignup) {
    const tenant = document.getElementById('ltenant').value.trim() || 'My Organisation';
    url = '/auth/signup';
    body = { email, password: pwd, tenant_name: tenant };
  }

  try {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.detail || 'Authentication failed.'; return; }
    sessionStorage.setItem('dm_token', data.access_token);
    sessionStorage.setItem('dm_email', email);
    bootApp();
  } catch(e) {
    errEl.textContent = 'Network error. Is the server running?';
  }
}

function logout() {
  sessionStorage.removeItem('dm_token');
  sessionStorage.removeItem('dm_email');
  document.getElementById('app').style.display = 'none';
  document.getElementById('loginPage').style.display = 'flex';
}

function bootApp() {
  document.getElementById('loginPage').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  const email = sessionStorage.getItem('dm_email') || '';
  document.getElementById('userEmail').textContent = email;
  loadDocs();
}

function getToken() { return sessionStorage.getItem('dm_token') || ''; }

function hdrs(extra) {
  return { 'Authorization': 'Bearer ' + getToken(), 'Content-Type': 'application/json', ...extra };
}

async function apiFetch(url, opts = {}) {
  const res = await fetch(url, { ...opts, headers: hdrs(opts.headers || {}) });
  if (res.status === 401) { logout(); throw new Error('Session expired. Please log in again.'); }
  return res;
}

// ── Toast ────────────────────────────────────────────────────────────────────
function toast(msg, type='ok') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast ' + type; t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3500);
}

// ── Panels ───────────────────────────────────────────────────────────────────
function showPanel(name) {
  ['chat','compare','history','stats','docs'].forEach(p => {
    const el = document.getElementById('panel-'+p);
    el.style.display = p === name ? 'flex' : 'none';
    if (p === name) el.style.flexDirection = 'column';
    document.getElementById('nav-'+p).className = 'nav-btn' + (p === name ? ' active' : '');
  });
  if (name === 'history') loadHistory(1);
  if (name === 'stats') loadStats();
  if (name === 'docs') loadDocsPanel(1);
  if (name === 'compare') document.getElementById('cmpResult').innerHTML = '';
}

// ── Documents ─────────────────────────────────────────────────────────────────
async function loadDocs() {
  try {
    const res = await apiFetch('/documents?page=1&limit=50');
    const data = await res.json();
    const docs = data.items || [];
    const el = document.getElementById('docList');
    if (!docs.length) { el.innerHTML = '<div style="font-size:11px;color:var(--mu)">No documents yet.</div>'; return; }
    el.innerHTML = docs.map(d => {
      const sel = compareDocIds[d.id];
      return `<div class="doc-item" id="di-${d.id}">
        <div class="doc-info">
          <div class="doc-name" title="${d.filename}">${d.filename}</div>
          <span class="doc-st ${d.status}">${d.status}</span>
          ${d.status==='ready' ? `
            <div class="doc-sug" onclick="getSuggestions('${d.id}','${d.filename}')">💡 Suggestions</div>
            <div class="doc-sug" onclick="reindexDoc('${d.id}','${d.filename}')" style="color:var(--yw)">🔄 Re-index</div>
            <div class="doc-cmp ${sel?'selected':''}" onclick="toggleCompare('${d.id}','${d.filename}')" id="cmp-${d.id}">${sel?'☑':'☐'} Compare</div>
          ` : d.status==='failed' ? `
            <div class="doc-sug" onclick="reindexDoc('${d.id}','${d.filename}')" style="color:var(--yw)">🔄 Retry Re-index</div>
          ` : ''}
        </div>
        <button class="doc-del" onclick="delDoc('${d.id}','${d.filename}')" title="Delete">🗑</button>
      </div>`;
    }).join('');
  } catch(e) { console.error(e); }
}

async function delDoc(id, name) {
  if (!confirm('Delete "' + name + '"? This also removes its vectors from search.')) return;
  try {
    const res = await apiFetch('/documents/'+id, { method: 'DELETE' });
    if (res.ok) { toast('Deleted: ' + name); loadDocs(); }
    else { const e = await res.json(); toast(e.detail || 'Delete failed.', 'err'); }
  } catch(e) { toast(e.message, 'err'); }
}

async function reindexDoc(id, name) {
  if (!confirm('Re-index "' + name + '"?\n\nThis will delete existing vectors and re-process the document from scratch.')) return;
  toast('Re-indexing started...', 'info');
  try {
    const res = await apiFetch('/documents/'+id+'/reindex', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      toast('Re-indexing in progress: ' + name);
      // Refresh doc list after a short delay to show updated status
      setTimeout(loadDocs, 1500);
    } else {
      toast(data.detail || 'Re-index failed.', 'err');
    }
  } catch(e) { toast(e.message, 'err'); }
}

async function uploadFile(inp) {
  const file = inp.files[0]; if (!file) return;
  const allowed = ['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
  if (!allowed.includes(file.type)) { toast('Only PDF and DOCX allowed.', 'err'); inp.value=''; return; }
  if (file.size > 10*1024*1024) { toast('File exceeds 10 MB limit.', 'err'); inp.value=''; return; }
  const form = new FormData(); form.append('file', file);
  toast('Uploading...', 'info');
  try {
    const res = await fetch('/documents', { method:'POST', headers:{'Authorization':'Bearer '+getToken()}, body:form });
    if (res.status === 401) { logout(); return; }
    if (res.ok) { toast('Uploaded! Processing in background...'); setTimeout(loadDocs, 2000); }
    else { const e = await res.json(); toast(e.detail || 'Upload failed.', 'err'); }
  } catch(e) { toast('Upload error: '+e.message, 'err'); }
  inp.value = '';
}

async function getSuggestions(docId, fname) {
  toast('Generating suggestions...', 'info');
  try {
    const res = await apiFetch('/documents/'+docId+'/suggestions');
    if (!res.ok) { toast('Could not generate suggestions.', 'err'); return; }
    const data = await res.json();
    const old = document.getElementById('sug-'+docId); if (old) old.remove();
    const c = document.createElement('div'); c.id = 'sug-'+docId;
    c.style.cssText = 'padding:4px 0 0;display:flex;flex-direction:column;gap:3px';
    c.innerHTML = data.suggestions.map(s => `<button onclick="sendQ('${s.replace(/'/g,"\\'")}')" style="background:var(--sf);border:1px solid var(--bd);border-radius:4px;padding:3px 7px;font-size:10px;color:var(--mu);cursor:pointer;text-align:left;transition:all .2s" onmouseover="this.style.borderColor='var(--ac)'" onmouseout="this.style.borderColor='var(--bd)'">${s}</button>`).join('');
    const di = document.getElementById('di-'+docId);
    if (di) di.parentNode.insertBefore(c, di.nextSibling);
    toast('Suggestions ready!');
    showPanel('chat');
  } catch(e) { toast(e.message, 'err'); }
}

// ── Compare ───────────────────────────────────────────────────────────────────
function toggleCompare(docId, fname) {
  if (compareDocIds[docId]) { delete compareDocIds[docId]; }
  else { if (Object.keys(compareDocIds).length >= 5) { toast('Max 5 documents for comparison.', 'err'); return; } compareDocIds[docId] = fname; }
  updateCompareBadge();
  loadDocs();
}

function updateCompareBadge() {
  const n = Object.keys(compareDocIds).length;
  const bar = document.getElementById('cmpBar');
  bar.style.display = n >= 2 ? 'flex' : 'none';
  document.getElementById('cmpDocNames').textContent = Object.values(compareDocIds).join(', ');
}

function clearCompare() { compareDocIds = {}; updateCompareBadge(); loadDocs(); }

async function runCompare() {
  const ids = Object.keys(compareDocIds);
  if (ids.length < 2) { toast('Select at least 2 documents.', 'err'); return; }
  const q = document.getElementById('question').value.trim() || 'Compare these documents and highlight key differences and similarities.';
  showPanel('compare');
  document.getElementById('cmpResult').innerHTML = '<div style="color:var(--mu);font-size:13px"><div class="typing" style="display:inline-flex"><span></span><span></span><span></span></div> Comparing documents...</div>';
  try {
    const res = await apiFetch('/query/compare', { method:'POST', body: JSON.stringify({ question: q, document_ids: ids }) });
    const data = await res.json();
    if (!res.ok) { document.getElementById('cmpResult').innerHTML = `<div style="color:var(--rd);font-size:13px">Error: ${data.detail}</div>`; return; }
    document.getElementById('cmpResult').innerHTML = `
      <div style="font-size:13px;line-height:1.7;white-space:pre-wrap;color:var(--tx)">${data.answer}</div>
      <div style="margin-top:10px;font-size:11px;color:var(--mu);font-family:var(--mono)">${data.latency_ms}ms · ${data.documents_compared.map(d=>d.filename+' ('+d.chunks_found+' chunks)').join(', ')}</div>
      <div style="margin-top:8px;display:flex;flex-direction:column;gap:4px">
        ${(data.sources||[]).map((s,i)=>`<div class="src-chip" onclick="openSrc(${i},[${JSON.stringify(data.sources)}])"><span class="sc-i">[${i+1}]</span><span class="sc-f" title="${s.filename}">${s.filename}</span><span class="sc-s">${(s.score*100).toFixed(0)}%</span></div>`).join('')}
      </div>`;
  } catch(e) { document.getElementById('cmpResult').innerHTML = `<div style="color:var(--rd);font-size:13px">Error: ${e.message}</div>`; }
}

// ── Chat ─────────────────────────────────────────────────────────────────────
function sendQ(q) { document.getElementById('question').value = q; ask(); }
function autoResize(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,90)+'px'; }
function handleKey(e) { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();} }

function addMsg(role, html) {
  const es = document.getElementById('emptyState'); if(es) es.remove();
  const p = document.getElementById('panel-chat');
  const d = document.createElement('div'); d.className='msg '+role;
  d.innerHTML=`<div class="av">${role==='user'?'👤':'🧠'}</div><div class="mb"><div class="mn">${role==='user'?'You':'DocuMind'}</div><div class="mt">${html}</div></div>`;
  p.appendChild(d); p.scrollTop=99999;
  return d.querySelector('.mt');
}

function showSources(sources, botEl) {
  if (!sources||!sources.length) return;
  currentSources = sources;
  const container = document.createElement('div'); container.className='src-list';
  container.innerHTML = sources.map((s,i)=>`<div class="src-chip" onclick="openSrcC(${i})"><span class="sc-i">[${i+1}]</span><span class="sc-f" title="${s.filename||''}">${s.filename||'Document'}</span><span class="sc-s">SIM ${(s.score*100).toFixed(0)}%</span></div>`).join('');
  botEl.parentElement.appendChild(container);
}

function openSrcC(idx) { openSrc(idx, currentSources); }

function openSrc(idx, sources) {
  const s = sources[idx];
  document.getElementById('mTitle').textContent = s.filename||'Source '+(idx+1);
  document.getElementById('mMeta').textContent = 'Relevance: '+(s.score*100).toFixed(1)+'% | Doc: '+s.document_id.slice(0,8)+'...';
  document.getElementById('mText').textContent = s.text;
  document.getElementById('srcModal').style.display = 'flex';
}


let _streamAbortController = null;

function cancelStream() {
  if (_streamAbortController) { _streamAbortController.abort(); _streamAbortController = null; }
}

async function ask() {
  const q = document.getElementById('question').value.trim(); if(!q) return;
  addMsg('user', q);
  document.getElementById('question').value=''; autoResize(document.getElementById('question'));

  const sendBtn = document.getElementById('sendBtn');
  sendBtn.innerHTML = '&#9632;'; sendBtn.title = 'Cancel'; sendBtn.onclick = cancelStream;
  sendBtn.style.background = 'var(--rd)'; sendBtn.disabled = false;

  const botEl = addMsg('bot', '<div class="typing"><span></span><span></span><span></span></div>');
  const start = performance.now();
  let fullText = '', streamedSources = [], cursor = null;

  function resetBtn() {
    sendBtn.innerHTML = '&#10148;'; sendBtn.title = 'Send';
    sendBtn.onclick = ask; sendBtn.style.background = ''; sendBtn.disabled = false;
  }
  function addCursor(el) {
    cursor = document.createElement('span');
    cursor.style.cssText = 'display:inline-block;width:2px;height:14px;background:var(--ac);margin-left:2px;vertical-align:middle;animation:bn 0.7s infinite';
    el.appendChild(cursor);
  }
  function removeCursor() { if(cursor){cursor.remove();cursor=null;} }

  _streamAbortController = new AbortController();

  try {
    const res = await fetch('/query/stream', {
      method:'POST',
      headers:{'Authorization':'Bearer '+getToken(),'Content-Type':'application/json'},
      body:JSON.stringify({question:q,top_k:5,stream:true}),
      signal:_streamAbortController.signal,
    });

    if(res.status===401){logout();return;}
    if(!res.ok){
      const err = await res.json().catch(()=>({}));
      botEl.textContent = 'Error '+res.status+': '+(err.detail||'Request failed');
      resetBtn(); return;
    }

    botEl.innerHTML=''; addCursor(botEl);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const panel = document.getElementById('panel-chat');

    while(true){
      let value, done;
      try { ({value,done} = await reader.read()); }
      catch(e){
        if(e.name==='AbortError'){
          removeCursor();
          botEl.insertAdjacentText('beforeend', fullText ? ' [cancelled]' : '[Cancelled]');
          break;
        }
        throw e;
      }
      if(done) break;

      buffer += decoder.decode(value,{stream:true});
      const parts = buffer.split('\n\n');
      buffer = parts.pop();

      for(const part of parts){
        if(!part.trim()) continue;
        const lines = part.split('\n');
        const evLine = lines.find(l=>l.startsWith('event:'));
        const dataLine = lines.find(l=>l.startsWith('data:'));
        if(!dataLine) continue;
        const evType = evLine ? evLine.slice(6).trim() : 'token';
        const data = dataLine.slice(5).trim();

        if(evType==='token'){
          const tok = data.replace(/\\n/g,'\n');
          fullText += tok;
          removeCursor(); botEl.textContent=fullText; addCursor(botEl);
          panel.scrollTop=99999;
        } else if(evType==='done'){
          removeCursor();
          try{streamedSources=JSON.parse(data);}catch(e){}
        } else if(evType==='error'){
          removeCursor();
          let detail=data; try{detail=JSON.parse(data).detail||data;}catch(e){}
          botEl.insertAdjacentText('beforeend', fullText ? '\n\n[Error: '+detail+']' : 'Error: '+detail);
        }
      }
    }

    removeCursor();
    const elapsed = Math.round(performance.now()-start);

    if(fullText){
      botEl.textContent = fullText;
      const meta = document.createElement('div'); meta.className='mm';
      meta.innerHTML = '<span>'+elapsed+'ms \xb7 '+streamedSources.length+' sources \xb7 streamed</span>'
        +'<button class="copy-btn" onclick="navigator.clipboard.writeText(this.dataset.t);toast(\'Copied!\')" data-t="">Copy</button>';
      meta.querySelector('.copy-btn').dataset.t = fullText;
      botEl.parentElement.appendChild(meta);
      if(streamedSources.length) showSources(streamedSources, botEl);
    } else if(!botEl.textContent||botEl.textContent==='[Cancelled]'){
      // fallback to non-streaming
      botEl.innerHTML='<div class="typing"><span></span><span></span><span></span></div>';
      try{
        const r2=await apiFetch('/query',{method:'POST',body:JSON.stringify({question:q,top_k:5,stream:false})});
        const d2=await r2.json(); const t2=Math.round(performance.now()-start);
        botEl.textContent=d2.answer||'No answer returned.';
        const m2=document.createElement('div');m2.className='mm';
        m2.innerHTML='<span>'+t2+'ms \xb7 '+(d2.sources||[]).length+' sources</span>';
        botEl.parentElement.appendChild(m2);
        showSources(d2.sources||[],botEl);
      }catch(e2){botEl.textContent='No response received.';}
    }

  } catch(e){
    removeCursor();
    if(e.name!=='AbortError') botEl.textContent='Stream error: '+e.message;
  }

  _streamAbortController=null; resetBtn();
  document.getElementById('panel-chat').scrollTop=99999;
}


// ── History ───────────────────────────────────────────────────────────────────
async function loadHistory(page=1) {
  histPage=page;
  try {
    const res = await apiFetch('/queries?page='+page+'&limit=10');
    const data = await res.json();
    const el = document.getElementById('historyList');
    if(!data.items.length) { el.innerHTML='<div style="color:var(--mu);font-size:12px">No queries yet.</div>'; return; }
    el.innerHTML=data.items.map(h=>`<div class="hi">
      <div class="hi-q">Q: ${h.question}</div>
      <div class="hi-a">${h.answer}</div>
      <div class="hi-m"><span>${new Date(h.created_at).toLocaleString()}</span><span>${h.latency_ms}ms</span><span>${h.input_tokens+h.output_tokens} tokens</span></div>
    </div>`).join('');
    renderPg('histPg', data, loadHistory);
  } catch(e) { console.error(e); }
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const res = await apiFetch('/stats');
    const s = await res.json();
    document.getElementById('statsGrid').innerHTML=`
      <div class="sc"><div class="sv">${s.documents.total}</div><div class="sl">Total Documents</div></div>
      <div class="sc"><div class="sv" style="color:var(--ac2)">${s.documents.ready}</div><div class="sl">Ready</div></div>
      <div class="sc"><div class="sv" style="color:var(--rd)">${s.documents.failed}</div><div class="sl">Failed</div></div>
      <div class="sc"><div class="sv">${s.queries.total}</div><div class="sl">Total Queries</div></div>
      <div class="sc"><div class="sv" style="color:var(--yw)">${s.queries.avg_latency_ms}ms</div><div class="sl">Avg Latency</div></div>
      <div class="sc"><div class="sv">${(s.queries.total_tokens_used/1000).toFixed(1)}K</div><div class="sl">Tokens Used</div></div>`;
  } catch(e) { console.error(e); }
}

// ── Docs panel ────────────────────────────────────────────────────────────────
  async function loadDocsPanel(page=1) {
  docsPage = page;
  try {
    const res = await apiFetch('/documents');
    const data = await res.json();

    const docs = Array.isArray(data) ? data : (data.items || []);
    const el = document.getElementById('docsDetail');

    if (!docs.length) {
      el.innerHTML = '<div style="color:var(--mu);font-size:12px">No documents.</div>';
      return;
    }

    el.innerHTML = docs.map(d => `<div class="hi">
      <div style="display:flex;align-items:center;gap:8px">
        <span>${d.filename.endsWith('.pdf') ? '📄' : '📄'}</span>
        <span style="font-weight:500;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${d.filename}</span>
        <span class="doc-st ${d.status}">${d.status}</span>
      </div>
      <div style="font-size:10px;color:var(--mu);font-family:var(--mono)">${new Date(d.created_at).toLocaleString()}</div>
      <div style="display:flex;gap:6px;margin-top:4px">
        ${d.status==='ready' ? `<button onclick="getSuggestions('${d.id}','${d.filename}');showPanel('chat')" style="background:var(--sf2);border:1px solid var(--bd);border-radius:4px;padding:3px 8px;font-size:10px;color:var(--mu);cursor:pointer">💡 Suggestions</button>` : ''}
        <button onclick="reindexDoc('${d.id}','${d.filename}').then(()=>loadDocsPanel(${page}))" style="background:none;border:1px solid var(--yw);border-radius:4px;padding:3px 8px;font-size:10px;color:var(--yw);cursor:pointer">🔄 Re-index</button>
        <button onclick="delDoc('${d.id}','${d.filename}');loadDocsPanel(${page})" style="background:none;border:1px solid var(--rd);border-radius:4px;padding:3px 8px;font-size:10px;color:var(--rd);cursor:pointer">🗑 Delete</button>
      </div>
    </div>`).join('');

    // API currently returns a plain array, so no pagination data is available.
    const pg = document.getElementById('docsPg');
    if (pg) pg.innerHTML = '';

  } catch(e) {
    console.error('loadDocsPanel failed:', e);
    const el = document.getElementById('docsDetail');
    if (el) {
      el.innerHTML = '<div style="color:var(--rd);font-size:12px">Failed to load documents.</div>';
    }
  }
}s

function renderPg(elId, data, fn) {
  const el = document.getElementById(elId); if(!el) return;
  if(data.total_pages<=1) { el.innerHTML=''; return; }
  el.innerHTML=`<button class="pg-btn" ${data.page<=1?'disabled':''} onclick="${fn.name}(${data.page-1})">‹</button>
    <span class="pg-info">Page ${data.page} / ${data.total_pages}</span>
    <button class="pg-btn" ${data.page>=data.total_pages?'disabled':''} onclick="${fn.name}(${data.page+1})">›</button>`;
}

// ── Boot ─────────────────────────────────────────────────────────────────────
if (sessionStorage.getItem('dm_token')) { bootApp(); }

// Auto-refresh doc list every 8s when app is visible
setInterval(() => { if(sessionStorage.getItem('dm_token')) loadDocs(); }, 8000);
</script>
</body>
</html>"""


@router.get("/chat", response_class=HTMLResponse)
async def chat_ui():
    return CHAT_HTML
