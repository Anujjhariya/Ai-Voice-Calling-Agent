/**
 * Binjwa IT Solutions — Embeddable AI Voice Widget
 * -------------------------------------------------
 * Add this single script tag to ANY website:
 *   <script src="https://your-ngrok-url/static/widget.js"></script>
 *
 * Optional config (add before the script tag):
 *   <script>
 *     window.BinjwaWidgetConfig = {
 *       lang: "hi",           // Default language: hi|en|mr|gu|pa
 *       position: "right",    // "right" or "left"
 *       primaryColor: "#6c63ff"
 *     };
 *   </script>
 */

(function () {
  "use strict";

  // ── Prevent double-init ────────────────────────────────────
  if (window.__BinjwaWidget) return;
  window.__BinjwaWidget = true;

  // ── Config ─────────────────────────────────────────────────
  const cfg = window.BinjwaWidgetConfig || {};
  const LANG     = cfg.lang          || "hi";
  const POSITION = cfg.position      || "right";
  const COLOR    = cfg.primaryColor  || "#6c63ff";
  const COLOR2   = cfg.accentColor   || "#a78bfa";

  // Derive WebSocket URL from current script src
  const scriptEl  = document.currentScript || (function () {
    const scripts = document.getElementsByTagName("script");
    return scripts[scripts.length - 1];
  })();
  const scriptSrc = scriptEl.src || window.location.origin + "/static/widget.js";
  const origin    = new URL(scriptSrc).origin;
  const WS_URL    = origin.replace(/^http/, "ws") + "/web-agent/ws";

  // ── Inject styles ──────────────────────────────────────────
  const style = document.createElement("style");
  style.textContent = `
    #bjw-root * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }

    /* ── Launcher Button ── */
    #bjw-launcher {
      position: fixed;
      ${POSITION === "left" ? "left: 24px;" : "right: 24px;"}
      bottom: 24px;
      width: 60px; height: 60px;
      border-radius: 50%;
      background: linear-gradient(135deg, ${COLOR}, ${COLOR2});
      box-shadow: 0 8px 32px rgba(108,99,255,0.45);
      cursor: pointer;
      border: none;
      display: flex; align-items: center; justify-content: center;
      z-index: 999998;
      transition: transform 0.25s ease, box-shadow 0.25s ease;
      animation: bjw-pop-in 0.5s cubic-bezier(0.34,1.56,0.64,1);
    }
    #bjw-launcher:hover { transform: scale(1.1); box-shadow: 0 12px 40px rgba(108,99,255,0.6); }
    #bjw-launcher:active { transform: scale(0.95); }

    /* Notification dot */
    #bjw-launcher .bjw-notif {
      position: absolute;
      top: 4px; right: 4px;
      width: 12px; height: 12px;
      border-radius: 50%;
      background: #f87171;
      border: 2px solid white;
      animation: bjw-pulse 1.5s ease infinite;
    }

    @keyframes bjw-pop-in {
      from { transform: scale(0); opacity: 0; }
      to   { transform: scale(1); opacity: 1; }
    }
    @keyframes bjw-pulse {
      0%, 100% { transform: scale(1); opacity: 1; }
      50%       { transform: scale(1.3); opacity: 0.7; }
    }

    /* ── Panel ── */
    #bjw-panel {
      position: fixed;
      ${POSITION === "left" ? "left: 16px;" : "right: 16px;"}
      bottom: 96px;
      width: 360px;
      max-height: 520px;
      background: #0d0f1a;
      border-radius: 20px;
      border: 1px solid rgba(255,255,255,0.08);
      box-shadow: 0 24px 64px rgba(0,0,0,0.5), 0 0 0 1px rgba(108,99,255,0.1);
      z-index: 999999;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      opacity: 0;
      pointer-events: none;
      transform: translateY(16px) scale(0.97);
      transform-origin: ${POSITION === "left" ? "bottom left" : "bottom right"};
      transition: opacity 0.25s ease, transform 0.25s cubic-bezier(0.34,1.2,0.64,1);
    }
    #bjw-panel.bjw-open {
      opacity: 1;
      pointer-events: all;
      transform: translateY(0) scale(1);
    }

    /* Panel Header */
    #bjw-header {
      padding: 16px 16px 14px;
      background: linear-gradient(135deg, rgba(108,99,255,0.15), rgba(167,139,250,0.08));
      border-bottom: 1px solid rgba(255,255,255,0.06);
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .bjw-avatar {
      width: 40px; height: 40px;
      border-radius: 50%;
      background: linear-gradient(135deg, ${COLOR}, ${COLOR2});
      display: flex; align-items: center; justify-content: center;
      font-size: 18px;
      flex-shrink: 0;
      box-shadow: 0 4px 16px rgba(108,99,255,0.3);
    }
    .bjw-avatar.bjw-speaking { animation: bjw-glow 1.2s ease-in-out infinite; }
    @keyframes bjw-glow {
      0%,100% { box-shadow: 0 4px 16px rgba(108,99,255,0.3); }
      50%      { box-shadow: 0 4px 28px rgba(108,99,255,0.7); }
    }

    .bjw-header-info { flex: 1; min-width: 0; }
    .bjw-header-name { font-size: 14px; font-weight: 600; color: #f1f5f9; }
    .bjw-header-status { font-size: 11px; color: #94a3b8; display: flex; align-items: center; gap: 5px; margin-top: 2px; }
    .bjw-status-dot { width: 6px; height: 6px; border-radius: 50%; background: #34d399; flex-shrink: 0; }
    .bjw-status-dot.bjw-active { animation: bjw-pulse 1s ease infinite; }

    .bjw-header-actions { display: flex; gap: 6px; align-items: center; }
    .bjw-hbtn {
      width: 28px; height: 28px;
      border-radius: 50%;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.04);
      color: #94a3b8;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      font-size: 12px;
      transition: all 0.2s;
    }
    .bjw-hbtn:hover { border-color: ${COLOR}; color: ${COLOR}; background: rgba(108,99,255,0.1); }

    /* Language selector */
    .bjw-lang {
      appearance: none;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      color: #f1f5f9;
      font-size: 11px;
      font-weight: 500;
      padding: 4px 22px 4px 8px;
      cursor: pointer;
      outline: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 6px center;
      transition: border-color 0.2s;
    }
    .bjw-lang:hover { border-color: ${COLOR}; }
    .bjw-lang option { background: #1e293b; }

    /* Chat messages */
    #bjw-messages {
      flex: 1;
      overflow-y: auto;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      scroll-behavior: smooth;
    }
    #bjw-messages::-webkit-scrollbar { width: 3px; }
    #bjw-messages::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }

    /* Bubbles */
    .bjw-msg { display: flex; gap: 8px; animation: bjw-fadein 0.3s ease; }
    .bjw-msg.bjw-user { flex-direction: row-reverse; }
    @keyframes bjw-fadein { from { opacity:0; transform: translateY(8px); } to { opacity:1; transform:translateY(0); } }

    .bjw-msg-av {
      width: 28px; height: 28px;
      border-radius: 50%;
      flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      font-size: 12px;
      margin-top: 2px;
    }
    .bjw-msg.bjw-ai   .bjw-msg-av { background: linear-gradient(135deg, ${COLOR}, ${COLOR2}); }
    .bjw-msg.bjw-user .bjw-msg-av { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.08); }

    .bjw-bubble {
      max-width: 230px;
      padding: 9px 12px;
      border-radius: 14px;
      font-size: 13px;
      line-height: 1.55;
      color: #e2e8f0;
      border: 1px solid transparent;
    }
    .bjw-msg.bjw-ai   .bjw-bubble { background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.07); border-top-left-radius: 3px; }
    .bjw-msg.bjw-user .bjw-bubble { background: rgba(108,99,255,0.18); border-color: rgba(108,99,255,0.25); border-top-right-radius: 3px; text-align: right; }

    /* Typing dots */
    .bjw-typing { display: flex; gap: 4px; padding: 10px 12px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.07); border-radius: 14px; border-top-left-radius: 3px; width: fit-content; }
    .bjw-tdot { width: 6px; height: 6px; border-radius: 50%; background: #475569; animation: bjw-bounce 1.2s ease infinite; }
    .bjw-tdot:nth-child(2) { animation-delay: 0.2s; }
    .bjw-tdot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bjw-bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-7px)} }

    /* Footer / Mic area */
    #bjw-footer {
      padding: 14px;
      border-top: 1px solid rgba(255,255,255,0.06);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
      background: rgba(0,0,0,0.2);
    }
    .bjw-hint { font-size: 11px; color: #475569; min-height: 16px; text-align: center; transition: color 0.2s; }
    .bjw-hint.bjw-active { color: #94a3b8; }

    /* Mic button */
    .bjw-mic-wrap { position: relative; display: flex; align-items: center; justify-content: center; }
    .bjw-ring {
      position: absolute;
      border-radius: 50%;
      border: 2px solid ${COLOR};
      opacity: 0;
      pointer-events: none;
    }
    .bjw-ring.r1 { width: 56px; height: 56px; }
    .bjw-ring.r2 { width: 72px; height: 72px; }

    #bjw-mic {
      width: 52px; height: 52px;
      border-radius: 50%;
      border: none;
      background: linear-gradient(135deg, ${COLOR}, ${COLOR2});
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 6px 24px rgba(108,99,255,0.4);
      transition: all 0.2s ease;
      position: relative;
      z-index: 1;
      -webkit-user-select: none; user-select: none;
      -webkit-tap-highlight-color: transparent;
    }
    #bjw-mic:hover:not(:disabled) { transform: scale(1.07); box-shadow: 0 8px 32px rgba(108,99,255,0.55); }
    #bjw-mic:disabled { opacity: 0.35; cursor: not-allowed; }
    #bjw-mic svg { width: 22px; height: 22px; pointer-events: none; }

    /* Recording */
    #bjw-mic.bjw-rec {
      background: linear-gradient(135deg, #dc2626, #f87171);
      box-shadow: 0 6px 24px rgba(220,38,38,0.4);
      animation: bjw-mic-pulse 1.5s ease infinite;
    }
    #bjw-mic.bjw-rec ~ .bjw-ring { opacity: 0.35; animation: bjw-ring-exp 1.5s ease-out infinite; }
    #bjw-mic.bjw-rec ~ .r2 { animation-delay: 0.35s; }
    @keyframes bjw-mic-pulse { 0%,100%{box-shadow:0 6px 24px rgba(220,38,38,0.4)} 50%{box-shadow:0 6px 36px rgba(220,38,38,0.7)} }
    @keyframes bjw-ring-exp { 0%{transform:scale(0.8);opacity:0.4} 100%{transform:scale(1.4);opacity:0} }

    /* Processing */
    #bjw-mic.bjw-proc {
      background: linear-gradient(135deg, #d97706, #fbbf24);
      animation: bjw-spin 2s linear infinite;
    }
    @keyframes bjw-spin { from{filter:hue-rotate(0deg)} to{filter:hue-rotate(60deg)} }

    /* Speaking waveform */
    .bjw-wave { display: none; gap: 3px; align-items: flex-end; height: 20px; }
    .bjw-wbar { width: 3px; border-radius: 2px; background: white; animation: bjw-wave-anim 0.8s ease-in-out infinite alternate; }
    .bjw-wbar:nth-child(1){height:30%;animation-delay:0s}
    .bjw-wbar:nth-child(2){height:70%;animation-delay:0.1s}
    .bjw-wbar:nth-child(3){height:100%;animation-delay:0.2s}
    .bjw-wbar:nth-child(4){height:60%;animation-delay:0.3s}
    .bjw-wbar:nth-child(5){height:40%;animation-delay:0.4s}
    @keyframes bjw-wave-anim { 0%{height:20%} 100%{height:100%} }
    #bjw-mic.bjw-spk .bjw-mic-icon { display:none; }
    #bjw-mic.bjw-spk .bjw-wave { display:flex; }

    /* Powered by */
    .bjw-powered { font-size: 10px; color: #334155; text-align: center; }
    .bjw-powered a { color: #6c63ff; text-decoration: none; }

    @media (max-width: 400px) {
      #bjw-panel { width: calc(100vw - 32px); right: 16px; left: 16px; }
    }
  `;
  document.head.appendChild(style);

  // ── Build HTML ─────────────────────────────────────────────
  const root = document.createElement("div");
  root.id = "bjw-root";
  root.innerHTML = `
    <!-- Floating launcher button -->
    <button id="bjw-launcher" title="Talk to our AI Assistant">
      <div class="bjw-notif"></div>
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
        <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
        <line x1="12" y1="19" x2="12" y2="23"/>
        <line x1="8" y1="23" x2="16" y2="23"/>
      </svg>
    </button>

    <!-- Chat panel -->
    <div id="bjw-panel">
      <!-- Header -->
      <div id="bjw-header">
        <div class="bjw-avatar" id="bjw-av">🤖</div>
        <div class="bjw-header-info">
          <div class="bjw-header-name">Binjwa IT Solutions</div>
          <div class="bjw-header-status">
            <div class="bjw-status-dot" id="bjw-sdot"></div>
            <span id="bjw-stext">Connecting…</span>
          </div>
        </div>
        <div class="bjw-header-actions">
          <select class="bjw-lang" id="bjw-lang">
            <option value="hi">हिंदी</option>
            <option value="en">English</option>
            <option value="mr">मराठी</option>
            <option value="gu">ગુજ.</option>
            <option value="pa">ਪੰਜਾਬੀ</option>
          </select>
          <button class="bjw-hbtn" id="bjw-clear-btn" title="Clear">🗑️</button>
          <button class="bjw-hbtn" id="bjw-close-btn" title="Close">✕</button>
        </div>
      </div>

      <!-- Messages -->
      <div id="bjw-messages"></div>

      <!-- Footer mic area -->
      <div id="bjw-footer">
        <div class="bjw-hint" id="bjw-hint">Connecting to AI…</div>
        <div class="bjw-mic-wrap">
          <button id="bjw-mic" disabled>
            <span class="bjw-mic-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="23"/>
                <line x1="8" y1="23" x2="16" y2="23"/>
              </svg>
            </span>
            <div class="bjw-wave">
              <div class="bjw-wbar"></div><div class="bjw-wbar"></div>
              <div class="bjw-wbar"></div><div class="bjw-wbar"></div>
              <div class="bjw-wbar"></div>
            </div>
          </button>
          <div class="bjw-ring r1"></div>
          <div class="bjw-ring r2"></div>
        </div>
        <div class="bjw-powered">Powered by <a href="#">Binjwa AI</a></div>
      </div>
    </div>
  `;
  document.body.appendChild(root);

  // ── Element refs ───────────────────────────────────────────
  const launcher  = document.getElementById("bjw-launcher");
  const panel     = document.getElementById("bjw-panel");
  const micBtn    = document.getElementById("bjw-mic");
  const messages  = document.getElementById("bjw-messages");
  const hintEl    = document.getElementById("bjw-hint");
  const sdot      = document.getElementById("bjw-sdot");
  const stext     = document.getElementById("bjw-stext");
  const avatar    = document.getElementById("bjw-av");
  const langSel   = document.getElementById("bjw-lang");

  langSel.value = LANG;

  langSel.addEventListener("change", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "clear" }));
      messages.innerHTML = "";
      stopAudio();
      ws.send(JSON.stringify({ type: "open", lang: langSel.value }));
    }
  });

  // ── State ──────────────────────────────────────────────────
  let ws           = null;
  let isOpen       = false;
  let isRecording  = false;
  let mediaRec     = null;
  let audioChunks  = [];
  let currentAudio = null;
  let hasOpened    = false; // trigger greeting only once per page load

  // ── Panel toggle ───────────────────────────────────────────
  launcher.addEventListener("click", () => {
    isOpen = !isOpen;
    panel.classList.toggle("bjw-open", isOpen);
    // Remove notification dot on first open
    const dot = launcher.querySelector(".bjw-notif");
    if (dot) dot.remove();

    if (isOpen && !ws) {
      connectWS();
    } else if (isOpen && ws && ws.readyState === WebSocket.OPEN && !hasOpened) {
      triggerGreeting();
    }
  });

  document.getElementById("bjw-close-btn").addEventListener("click", () => {
    isOpen = false;
    panel.classList.remove("bjw-open");
  });

  document.getElementById("bjw-clear-btn").addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "clear" }));
    }
    messages.innerHTML = "";
    stopAudio();
  });

  // ── WebSocket ──────────────────────────────────────────────
  function connectWS() {
    setStatus("Connecting…", false);
    setHint("Connecting to AI…");
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setStatus("Online", true);
      micBtn.disabled = false;
      setHint("Hold button to speak");
      triggerGreeting();
    };

    ws.onmessage = (e) => handleMsg(JSON.parse(e.data));

    ws.onclose = () => {
      setStatus("Reconnecting…", false);
      micBtn.disabled = true;
      setHint("Reconnecting…");
      setTimeout(connectWS, 3000);
    };

    ws.onerror = () => {};
  }

  function triggerGreeting() {
    if (hasOpened) return;
    hasOpened = true;
    const context = {
      url: window.location.href,
      title: document.title || "",
      description: document.querySelector('meta[name="description"]')?.content || "",
      bodyText: (document.body ? document.body.innerText : "").substring(0, 3000)
    };
    ws.send(JSON.stringify({ type: "open", lang: langSel.value, context: context }));
  }

  // ── Message handler ────────────────────────────────────────
  function handleMsg(msg) {
    switch (msg.type) {
      case "status":
        const map = {
          idle:       ["Ready",      "Hold button to speak",         false, false, false],
          listening:  ["Listening…", "🔴 Recording — release to send", false, false, false],
          processing: ["Thinking…",  "✨ Processing…",               false, false, false],
          speaking:   ["Speaking…",  "🔊 AI is speaking",            true,  false, false],
        };
        const [label, hint, speaking] = map[msg.state] || ["Ready", "", false];
        setStatus(label, msg.state !== "idle");
        setHint(msg.message || hint);
        avatar.classList.toggle("bjw-speaking", speaking);
        updateMicClass(msg.state);
        if (msg.state !== "processing") micBtn.disabled = (msg.state === "processing");
        break;

      case "reply":
        removeTyping();
        addBubble("ai", msg.text);
        break;

      case "transcript":
        addBubble("user", msg.text);
        addTypingIndicator();
        break;

      case "audio":
        playAudio(msg.data, msg.format || "wav");
        break;

      case "error":
        removeTyping();
        setHint("⚠️ " + msg.message);
        updateMicClass("idle");
        break;
    }
  }

  // ── Recording ──────────────────────────────────────────────
  async function startRec() {
    if (isRecording || !ws || ws.readyState !== WebSocket.OPEN) return;
    stopAudio();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus" : "audio/webm";
      mediaRec = new MediaRecorder(stream, { mimeType: mime });
      mediaRec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          const reader = new FileReader();
          reader.onload = () => {
            const arr = new Uint8Array(reader.result);
            let bin = "";
            arr.forEach(b => bin += String.fromCharCode(b));
            ws.send(JSON.stringify({ type: "audio", data: btoa(bin) }));
          };
          reader.readAsArrayBuffer(e.data);
        }
      };
      ws.send(JSON.stringify({ type: "start", lang: langSel.value }));
      mediaRec.start(200);
      isRecording = true;
      mediaRec.onstop = () => stream.getTracks().forEach(t => t.stop());
    } catch (err) {
      setHint("⚠️ Mic access denied");
    }
  }

  function stopRec() {
    if (!isRecording || !mediaRec) return;
    isRecording = false;
    mediaRec.stop();
    mediaRec = null;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
    }
  }

  // Hold to talk
  micBtn.addEventListener("mousedown",  startRec);
  micBtn.addEventListener("mouseup",    stopRec);
  micBtn.addEventListener("mouseleave", stopRec);
  micBtn.addEventListener("touchstart", (e) => { e.preventDefault(); startRec(); }, { passive: false });
  micBtn.addEventListener("touchend",   (e) => { e.preventDefault(); stopRec(); },  { passive: false });
  micBtn.addEventListener("contextmenu", e => e.preventDefault());

  // ── Audio playback ─────────────────────────────────────────
  function playAudio(b64, format) {
    stopAudio();
    const mime   = format === "wav" ? "audio/wav" : "audio/mpeg";
    const bin    = atob(b64);
    const bytes  = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const blob   = new Blob([bytes], { type: mime });
    const url    = URL.createObjectURL(blob);
    currentAudio = new Audio(url);
    currentAudio.onended = () => {
      URL.revokeObjectURL(url);
      updateMicClass("idle");
      setStatus("Ready", false);
      setHint("Hold button to speak");
      avatar.classList.remove("bjw-speaking");
      currentAudio = null;
    };
    currentAudio.play().catch(() => {});
  }

  function stopAudio() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
  }

  // ── UI helpers ─────────────────────────────────────────────
  function setStatus(text, active) {
    stext.textContent = text;
    sdot.classList.toggle("bjw-active", active);
  }

  function setHint(text) {
    hintEl.textContent = text;
    hintEl.classList.toggle("bjw-active", !!text);
  }

  function updateMicClass(state) {
    micBtn.className = "";
    micBtn.removeAttribute("class");
    if (state === "listening")  micBtn.classList.add("bjw-rec");
    if (state === "processing") { micBtn.classList.add("bjw-proc"); micBtn.disabled = true; }
    if (state === "speaking")   micBtn.classList.add("bjw-spk");
    if (state === "idle" || state === "speaking") micBtn.disabled = false;
  }

  function addBubble(role, text) {
    const el = document.createElement("div");
    el.className = `bjw-msg bjw-${role}`;
    el.innerHTML = `
      <div class="bjw-msg-av">${role === "ai" ? "🤖" : "👤"}</div>
      <div class="bjw-bubble">${esc(text)}</div>
    `;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  function addTypingIndicator() {
    removeTyping();
    const el = document.createElement("div");
    el.className = "bjw-msg bjw-ai";
    el.id = "bjw-typing";
    el.innerHTML = `
      <div class="bjw-msg-av">🤖</div>
      <div class="bjw-typing"><div class="bjw-tdot"></div><div class="bjw-tdot"></div><div class="bjw-tdot"></div></div>
    `;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  function removeTyping() {
    const el = document.getElementById("bjw-typing");
    if (el) el.remove();
  }

  function esc(t) {
    return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/\n/g,"<br>");
  }

})();
