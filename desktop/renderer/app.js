/* ══════════════════════════════════════════════
   YOLO DESKTOP — Renderer Logic
   Shares sessions with Telegram/CLI via the
   same SessionManager → SQLite backend.
   ══════════════════════════════════════════════ */

(() => {
  'use strict';

  // ── State ──
  const state = {
    userId: 1,
    messages: [],       // { role, content, timestamp }
    isLoading: false,
    yoloMode: false,
    thinkMode: false,
    theme: 'dark',
  };

  // ── DOM refs ──
  const $ = (sel) => document.querySelector(sel);
  const dom = {
    app: $('#app'),
    sidebar: $('#sidebar'),
    sidebarToggle: $('#sidebar-toggle'),
    mobileMenu: $('#mobile-menu-btn'),
    newChatBtn: $('#new-chat-btn'),
    chatList: $('#chat-list'),
    chatTitle: $('#chat-title'),
    chatSubtitle: $('#chat-subtitle'),
    messagesContainer: $('#messages-container'),
    messages: $('#messages'),
    welcome: $('#welcome-screen'),
    input: $('#message-input'),
    sendBtn: $('#send-btn'),
    attachBtn: $('#attach-btn'),
    modeToggle: $('#mode-toggle'),
    statusBar: $('#status-bar'),
    statusText: $('#status-text'),
    settingsBtn: $('#settings-btn'),
    settingsModal: $('#settings-modal'),
    closeSettings: $('#close-settings'),
    settingUserId: $('#setting-user-id'),
    settingMode: $('#setting-mode'),
    settingTheme: $('#setting-theme'),
  };

  // ── Init ──
  function init() {
    loadPrefs();
    applyTheme();
    bindEvents();
    pollHealth(); // Detects user_id from backend, then hydrates session
  }

  function loadPrefs() {
    try {
      const saved = localStorage.getItem('yolo-desktop-prefs');
      if (saved) {
        const p = JSON.parse(saved);
        state.userId = p.userId || 1;
        state.theme = p.theme || 'dark';
      }
    } catch {}
  }

  function savePrefs() {
    try {
      localStorage.setItem('yolo-desktop-prefs', JSON.stringify({
        userId: state.userId,
        theme: state.theme,
      }));
    } catch {}
  }

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', state.theme);
    dom.settingTheme.value = state.theme;
  }

  // ── Hydrate session from backend (shared with Telegram/CLI) ──
  async function hydrateFromSession() {
    try {
      const data = await window.yoloAPI.getSession({ userId: state.userId });
      if (data && data.messages) {
        state.yoloMode = data.yolo_mode || false;
        state.thinkMode = data.think_mode || false;
        state.messages = data.messages.map(m => ({
          role: m.role,
          content: m.content,
          timestamp: null,
        }));

        // Sync mode badge
        const label = dom.modeToggle.querySelector('.mode-label');
        label.textContent = state.yoloMode ? 'YOLO' : 'Safe';
        label.classList.toggle('yolo', state.yoloMode);

        // Update subtitle
        dom.chatSubtitle.textContent = `${data.history_length} msgs · ${data.total_tokens} tokens · ${data.llm_call_count} LLM calls`;
      }
    } catch {}
    renderMessages();
  }

  // ── Rendering ──
  function renderMessages() {
    dom.messages.innerHTML = '';

    if (state.messages.length === 0) {
      dom.messages.appendChild(createWelcomeScreen());
      return;
    }

    state.messages.forEach(msg => {
      dom.messages.appendChild(createMessageEl(msg));
    });
    scrollToBottom();
  }

  function createWelcomeScreen() {
    const div = document.createElement('div');
    div.className = 'welcome-screen';
    div.innerHTML = `
      <div class="welcome-icon">
        <div class="welcome-glow"></div>
        <span>Y</span>
      </div>
      <h1>Welcome to Yolo</h1>
      <p>Your autonomous AI agent. Ask anything — code, research, system control, and more.</p>
      <p style="font-size:12px; color:var(--text-muted); margin-top:8px;">Session is shared with Telegram &amp; CLI. Type <kbd>/</kbd> for commands.</p>
      <div class="quick-actions">
        <button class="quick-action" data-prompt="Help me write a Python script">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 18l6-6-6-6"/><path d="M8 6l-6 6 6 6"/></svg>
          Write Code
        </button>
        <button class="quick-action" data-prompt="Search the web for the latest AI news">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          Web Search
        </button>
        <button class="quick-action" data-prompt="Analyze the files in my current project">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          Analyze Files
        </button>
        <button class="quick-action" data-prompt="What can you do?">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          Capabilities
        </button>
      </div>
    `;
    div.querySelectorAll('.quick-action').forEach(btn => {
      btn.addEventListener('click', () => sendMessage(btn.dataset.prompt));
    });
    return div;
  }

  function createMessageEl(msg) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${msg.role}`;

    if (msg.role === 'assistant') {
      wrapper.innerHTML = `<div class="msg-avatar">Y</div>`;
    }

    const content = document.createElement('div');
    content.className = 'msg-content';

    if (msg.role === 'assistant') {
      content.innerHTML = renderMarkdown(msg.content);
      content.querySelectorAll('pre code').forEach(block => {
        try { hljs.highlightElement(block); } catch {}
      });
    } else {
      content.textContent = msg.content;
    }

    wrapper.appendChild(content);

    if (msg.timestamp) {
      const ts = document.createElement('div');
      ts.className = 'msg-timestamp';
      ts.textContent = formatTime(msg.timestamp);
      wrapper.appendChild(ts);
    }

    return wrapper;
  }

  function showTypingIndicator() {
    removeTypingIndicator();
    const el = document.createElement('div');
    el.className = 'typing-indicator';
    el.id = 'typing';
    el.innerHTML = `
      <div class="msg-avatar">Y</div>
      <div class="typing-dots"><span></span><span></span><span></span></div>
    `;
    dom.messages.appendChild(el);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    const el = document.getElementById('typing');
    if (el) el.remove();
  }

  // ── Slash commands registry ──
  const SLASH_COMMANDS = [
    { cmd: 'start',       desc: 'Reset the current session',       icon: '🔄' },
    { cmd: 'status',      desc: 'Show session status report',      icon: '📊' },
    { cmd: 'mode',        desc: 'Toggle Safe/YOLO mode',           icon: '⚡', hasArgs: true, hint: 'yolo | safe' },
    { cmd: 'think',       desc: 'Toggle think mode',               icon: '🧠', hasArgs: true, hint: 'on | off | auto' },
    { cmd: 'compact',     desc: 'Compact conversation history',    icon: '📦' },
    { cmd: 'tools',       desc: 'List all available tools',        icon: '🔧' },
    { cmd: 'experiences', desc: 'Show technical lessons learned',   icon: '📖' },
    { cmd: 'schedules',   desc: 'Show scheduled tasks',            icon: '📅' },
    { cmd: 'memories',    desc: 'Show stored user memories',       icon: '💾' },
    { cmd: 'facts',       desc: 'Show auto-injected basic facts',  icon: '📌' },
    { cmd: 'forget',      desc: 'Wipe all stored memories',        icon: '🗑️' },
    { cmd: 'cancel',      desc: 'Cancel pending confirmations',    icon: '❌' },
  ];

  function parseSlashCommand(text) {
    if (!text.startsWith('/')) return null;
    const parts = text.trim().split(/\s+/);
    const cmd = parts[0].slice(1).toLowerCase();
    const args = parts.slice(1);
    const match = SLASH_COMMANDS.find(c => c.cmd === cmd);
    if (!match) return null;
    return { command: cmd, args };
  }

  // ── Command palette ──
  function createCommandPalette() {
    const palette = document.createElement('div');
    palette.id = 'command-palette';
    palette.className = 'command-palette hidden';
    document.querySelector('.input-wrapper').prepend(palette);
    return palette;
  }

  const commandPalette = createCommandPalette();

  function showCommandPalette(filter) {
    const query = (filter || '').toLowerCase();
    const matches = SLASH_COMMANDS.filter(c =>
      c.cmd.includes(query) || c.desc.toLowerCase().includes(query)
    );
    if (matches.length === 0) { commandPalette.classList.add('hidden'); return; }
    commandPalette.innerHTML = matches.map(c => `
      <div class="cmd-option" data-cmd="${c.cmd}" data-has-args="${!!c.hasArgs}">
        <span class="cmd-icon">${c.icon}</span>
        <div class="cmd-info">
          <span class="cmd-name">/${c.cmd}${c.hint ? ' <span class="cmd-hint">' + c.hint + '</span>' : ''}</span>
          <span class="cmd-desc">${c.desc}</span>
        </div>
      </div>
    `).join('');
    commandPalette.classList.remove('hidden');

    commandPalette.querySelectorAll('.cmd-option').forEach(opt => {
      opt.addEventListener('click', () => {
        const cmd = opt.dataset.cmd;
        if (opt.dataset.hasArgs === 'true') {
          dom.input.value = `/${cmd} `;
          dom.input.focus();
        } else {
          dom.input.value = `/${cmd}`;
          sendMessage(`/${cmd}`);
        }
        commandPalette.classList.add('hidden');
      });
    });
  }

  function hideCommandPalette() { commandPalette.classList.add('hidden'); }

  // ── Send message (with slash-command support) ──
  async function sendMessage(text) {
    if (!text || !text.trim() || state.isLoading) return;
    text = text.trim();

    const slashCmd = parseSlashCommand(text);

    // Add user message to local state
    const userMsg = { role: 'user', content: text, timestamp: Date.now() };
    state.messages.push(userMsg);

    renderMessages();
    dom.input.value = '';
    dom.input.style.height = 'auto';
    dom.sendBtn.disabled = true;
    hideCommandPalette();

    state.isLoading = true;
    showTypingIndicator();

    try {
      let result;
      if (slashCmd) {
        result = await window.yoloAPI.runCommand({
          command: slashCmd.command,
          args: slashCmd.args,
          userId: state.userId,
        });
        // Sync UI state for mode/think/start
        if (slashCmd.command === 'mode' && slashCmd.args.length) {
          const m = slashCmd.args[0].toLowerCase();
          if (m === 'yolo') state.yoloMode = true;
          else if (m === 'safe') state.yoloMode = false;
          syncModeBadge();
        }
        if (slashCmd.command === 'start') {
          state.messages = [userMsg];
        }
      } else {
        result = await window.yoloAPI.sendMessage({
          message: text,
          userId: state.userId,
        });
      }

      removeTypingIndicator();

      const response = result.response || result.error || 'No response received.';
      const assistantMsg = { role: 'assistant', content: response, timestamp: Date.now() };
      state.messages.push(assistantMsg);
      dom.messages.appendChild(createMessageEl(assistantMsg));

      // Refresh subtitle stats
      refreshSessionMeta();
      scrollToBottom();
    } catch (err) {
      removeTypingIndicator();
      const errMsg = { role: 'assistant', content: `⚠️ Connection error: ${err.message}`, timestamp: Date.now() };
      state.messages.push(errMsg);
      dom.messages.appendChild(createMessageEl(errMsg));
      scrollToBottom();
    } finally {
      state.isLoading = false;
    }
  }

  function syncModeBadge() {
    const label = dom.modeToggle.querySelector('.mode-label');
    label.textContent = state.yoloMode ? 'YOLO' : 'Safe';
    label.classList.toggle('yolo', state.yoloMode);
  }

  async function refreshSessionMeta() {
    try {
      const data = await window.yoloAPI.getSession({ userId: state.userId });
      if (data) {
        dom.chatSubtitle.textContent = `${data.history_length} msgs · ${data.total_tokens} tokens · ${data.llm_call_count} LLM calls`;
      }
    } catch {}
  }

  // ── Events ──
  function bindEvents() {
    dom.sendBtn.addEventListener('click', () => sendMessage(dom.input.value));
    dom.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(dom.input.value); }
    });

    dom.input.addEventListener('input', () => {
      dom.sendBtn.disabled = !dom.input.value.trim();
      dom.input.style.height = 'auto';
      dom.input.style.height = Math.min(dom.input.scrollHeight, 150) + 'px';
      const val = dom.input.value;
      if (val.startsWith('/') && !val.includes('\n')) {
        showCommandPalette(val.slice(1).split(/\s/)[0]);
      } else {
        hideCommandPalette();
      }
    });

    dom.input.addEventListener('blur', () => setTimeout(hideCommandPalette, 200));

    // New Chat = /start (resets shared session)
    dom.newChatBtn.addEventListener('click', () => sendMessage('/start'));

    dom.sidebarToggle.addEventListener('click', () => dom.sidebar.classList.toggle('collapsed'));
    if (dom.mobileMenu) dom.mobileMenu.addEventListener('click', () => dom.sidebar.classList.toggle('collapsed'));

    dom.modeToggle.addEventListener('click', () => {
      const newMode = state.yoloMode ? 'safe' : 'yolo';
      sendMessage(`/mode ${newMode}`);
    });

    // Settings
    dom.settingsBtn.addEventListener('click', () => {
      dom.settingUserId.value = state.userId;
      dom.settingMode.value = state.yoloMode ? 'yolo' : 'safe';
      dom.settingsModal.classList.remove('hidden');
    });
    dom.closeSettings.addEventListener('click', () => dom.settingsModal.classList.add('hidden'));
    dom.settingsModal.addEventListener('click', (e) => {
      if (e.target === dom.settingsModal) dom.settingsModal.classList.add('hidden');
    });
    dom.settingUserId.addEventListener('change', () => {
      state.userId = parseInt(dom.settingUserId.value) || 1;
      localStorage.setItem('yolo-manual-user-id', String(state.userId));
      savePrefs();
      hydrateFromSession(); // Reload for new user
    });
    dom.settingMode.addEventListener('change', () => {
      sendMessage(`/mode ${dom.settingMode.value}`);
    });
    dom.settingTheme.addEventListener('change', () => {
      state.theme = dom.settingTheme.value;
      applyTheme();
      savePrefs();
    });

    // Bridge status
    if (window.yoloAPI?.onBridgeStatus) {
      window.yoloAPI.onBridgeStatus((status) => {
        updateStatus(status === 'connected' ? 'connected' : 'disconnected');
        if (status === 'connected') hydrateFromSession();
      });
    }
  }

  // ── Health polling + auto-detect user ID ──
  async function pollHealth() {
    const check = async () => {
      try {
        const res = await window.yoloAPI.healthCheck();
        if (res.status === 'ok') {
          updateStatus('connected');
          // Auto-detect user ID from backend on first connect
          if (res.default_user_id && !localStorage.getItem('yolo-manual-user-id')) {
            state.userId = res.default_user_id;
          }
        } else {
          updateStatus('disconnected');
        }
      } catch { updateStatus('disconnected'); }
    };
    await check();
    // Hydrate AFTER we know the correct user_id
    await hydrateFromSession();
    setInterval(check, 10000);
  }

  function updateStatus(status) {
    dom.statusBar.className = `status-bar status-${status}`;
    const labels = {
      connected: 'Connected — session shared with Telegram & CLI',
      connecting: 'Connecting to Yolo agent...',
      disconnected: 'Agent offline — start the bridge',
    };
    dom.statusText.textContent = labels[status] || labels.connecting;
    if (status === 'connected') setTimeout(() => dom.statusBar.classList.add('hidden'), 3000);
    else dom.statusBar.classList.remove('hidden');
  }

  // ── Utilities ──
  function renderMarkdown(text) {
    if (!text) return '';
    try {
      if (typeof marked !== 'undefined') { marked.setOptions({ breaks: true, gfm: true }); return marked.parse(text); }
    } catch {}
    return escapeHtml(text).replace(/\n/g, '<br>');
  }

  function escapeHtml(str) { const d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML; }
  function formatTime(ts) { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  function scrollToBottom() { requestAnimationFrame(() => { dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight; }); }

  init();
})();
