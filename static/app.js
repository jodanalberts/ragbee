const $ = (id) => document.getElementById(id);

const state = {
  collections: [],
  threads: [],
  activeCollection: null,
  activeThread: null,
  mode: "chat", // "chat" | "ingest"
  streaming: false,
};

// ── API helper ─────────────────────────────────────────────
async function api(path, opts = {}) {
  const { headers: extraHeaders, ...rest } = opts;
  const res = await fetch(path, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(extraHeaders || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function toast(msg, kind = "") {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (kind ? " " + kind : "");
  t.hidden = false;
  setTimeout(() => { t.hidden = true; }, 2500);
}

// ── Collections ────────────────────────────────────────────
async function loadCollections() {
  state.collections = await api("/api/collections");
  renderCollections();
}

function renderCollections() {
  const ul = $("collections-list");
  ul.innerHTML = state.collections.map(c => `
    <li data-id="${c.id}" class="${state.activeCollection?.id === c.id ? "active" : ""}">
      <span class="name">${escapeHtml(c.name)}</span>
      <span class="count">${c.chunk_count}</span>
    </li>
  `).join("");
  ul.querySelectorAll("li").forEach(li => {
    li.onclick = () => selectCollection(li.dataset.id);
  });
}

async function selectCollection(cid) {
  state.activeCollection = state.collections.find(c => c.id === cid);
  state.activeThread = null;
  localStorage.setItem("activeId", JSON.stringify({ kind: "collection", id: cid }));
  renderCollections();
  renderThreads();
  showCollectionView();
  await loadChunks();
}

async function createCollection() {
  const input = $("new-collection-input");
  const err = $("new-collection-error");
  input.value = "";
  err.hidden = true;
  $("new-collection-modal").hidden = false;
  input.focus();
}

async function submitNewCollection() {
  const input = $("new-collection-input");
  const err = $("new-collection-error");
  const name = input.value.trim();
  if (!name) {
    err.textContent = "Please enter a name.";
    err.hidden = false;
    input.focus();
    return;
  }
  const btn = $("new-collection-create");
  btn.disabled = true;
  try {
    const { id } = await api("/api/collections", { method: "POST", body: JSON.stringify({ name }) });
    $("new-collection-modal").hidden = true;
    await loadCollections();
    selectCollection(id);
  } catch (e) {
    err.textContent = e.message;
    err.hidden = false;
  } finally {
    btn.disabled = false;
  }
}

function closeNewCollection() {
  $("new-collection-modal").hidden = true;
}

async function deleteCollection() {
  if (!state.activeCollection) return;
  if (!confirm(`Delete "${state.activeCollection.name}" and all its chunks?`)) return;
  await api(`/api/collections/${state.activeCollection.id}`, { method: "DELETE" });
  state.activeCollection = null;
  localStorage.removeItem("activeId");
  showEmptyState();
  await loadCollections();
}

function showCollectionView() {
  $("empty-state").hidden = true;
  $("thread-view").hidden = true;
  $("collection-view").hidden = false;
  $("collection-name").textContent = state.activeCollection.name;
}

function showEmptyState() {
  $("collection-view").hidden = true;
  $("thread-view").hidden = true;
  $("empty-state").hidden = false;
}

// ── Chunks ─────────────────────────────────────────────────
async function loadChunks() {
  if (!state.activeCollection) return;
  const chunks = await api(`/api/collections/${state.activeCollection.id}/chunks`);
  renderChunks(chunks);
}

function renderChunks(chunks) {
  const list = $("chunks-list");
  if (!chunks.length) {
    list.innerHTML = `<p style="color: var(--text-muted); text-align: center; padding: 24px;">No chunks yet. Upload a file or add a note above.</p>`;
    return;
  }
  list.innerHTML = chunks.map(c => `
    <div class="chunk-card" data-id="${c.id}">
      <span class="chunk-source">${escapeHtml(c.source)}</span>
      <div class="chunk-text">${escapeHtml(c.text)}</div>
      <button class="chunk-delete" title="Delete">✕</button>
    </div>
  `).join("");
  list.querySelectorAll(".chunk-delete").forEach(btn => {
    btn.onclick = async (e) => {
      const card = e.target.closest(".chunk-card");
      const ckid = card.dataset.id;
      await api(`/api/collections/${state.activeCollection.id}/chunks/${ckid}`, { method: "DELETE" });
      await loadChunks();
      await loadCollections();
    };
  });
}

async function uploadFiles(files) {
  if (!state.activeCollection || !files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await fetch(`/api/collections/${state.activeCollection.id}/files`, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    toast(err.detail || "Upload failed", "error");
    return;
  }
  const { added } = await res.json();
  toast(`Added ${added} chunk${added !== 1 ? "s" : ""}`, "success");
  await loadChunks();
  await loadCollections();
}

async function addNote() {
  if (!state.activeCollection) return;
  const text = $("note-input").value.trim();
  if (!text) return;
  await api(`/api/collections/${state.activeCollection.id}/notes`, { method: "POST", body: JSON.stringify({ text }) });
  $("note-input").value = "";
  toast("Note added", "success");
  await loadChunks();
  await loadCollections();
}

// ── Threads ────────────────────────────────────────────────
async function loadThreads() {
  state.threads = await api("/api/threads");
  renderThreads();
}

function renderThreads() {
  const ul = $("threads-list");
  ul.innerHTML = state.threads.map(t => `
    <li data-id="${t.id}" class="${state.activeThread?.id === t.id ? "active" : ""}">
      <span class="name">${escapeHtml(t.title)}</span>
      <span class="count">${t.collection_name || "—"}</span>
    </li>
  `).join("");
  ul.querySelectorAll("li").forEach(li => {
    li.onclick = () => selectThread(li.dataset.id);
  });
}

async function selectThread(tid) {
  state.activeThread = state.threads.find(t => t.id === tid);
  state.activeCollection = null;
  localStorage.setItem("activeId", JSON.stringify({ kind: "thread", id: tid }));
  renderCollections();
  renderThreads();
  showThreadView();
  await loadMessages();
  populateThreadCollectionSelect();
}

async function createThread() {
  const input = $("new-thread-input");
  const sel = $("new-thread-collection");
  const err = $("new-thread-error");
  input.value = "";
  sel.innerHTML = `<option value="">(none — plain chat)</option>` +
    state.collections.map(c =>
      `<option value="${c.id}">${escapeHtml(c.name)}</option>`
    ).join("");
  err.hidden = true;
  $("new-thread-modal").hidden = false;
  input.focus();
}

async function submitNewThread() {
  const input = $("new-thread-input");
  const sel = $("new-thread-collection");
  const err = $("new-thread-error");
  const title = input.value.trim() || "New thread";
  const collection_id = sel.value || null;
  const btn = $("new-thread-create");
  btn.disabled = true;
  try {
    const { id } = await api("/api/threads", {
      method: "POST",
      body: JSON.stringify({ title, collection_id }),
    });
    $("new-thread-modal").hidden = true;
    await loadThreads();
    const found = state.threads.find(t => t.id === id);
    if (!found) {
      err.textContent = "Thread created but couldn't be loaded. Try clicking it in the sidebar.";
      err.hidden = false;
      return;
    }
    selectThread(id);
    toast("Thread created", "success");
  } catch (e) {
    err.textContent = e.message;
    err.hidden = false;
  } finally {
    btn.disabled = false;
  }
}

function closeNewThread() {
  $("new-thread-modal").hidden = true;
}

async function deleteThread() {
  if (!state.activeThread) return;
  if (!confirm(`Delete thread "${state.activeThread.title}"?`)) return;
  await api(`/api/threads/${state.activeThread.id}`, { method: "DELETE" });
  state.activeThread = null;
  localStorage.removeItem("activeId");
  showEmptyState();
  await loadThreads();
}

function showThreadView() {
  $("empty-state").hidden = true;
  $("collection-view").hidden = true;
  $("thread-view").hidden = false;
  $("thread-title").textContent = state.activeThread.title;
}

async function loadMessages() {
  if (!state.activeThread) return;
  const messages = await api(`/api/threads/${state.activeThread.id}/messages`);
  renderMessages(messages);
}

function renderMessages(messages) {
  const box = $("messages");
  box.innerHTML = messages.map(m => messageHtml(m.role, m.content)).join("");
  box.scrollTop = box.scrollHeight;
}

function messageHtml(role, content) {
  const roleLabel = role === "user" ? "You" : role === "assistant" ? "🐝 RAGbee" : "system";
  return `<div class="message ${role}"><span class="role">${roleLabel}</span>${escapeHtml(content)}</div>`;
}

function appendMessage(role, content) {
  const box = $("messages");
  box.insertAdjacentHTML("beforeend", messageHtml(role, content));
  box.scrollTop = box.scrollHeight;
  return box.lastElementChild;
}

function updateLastMessage(role, text) {
  const box = $("messages");
  const last = box.lastElementChild;
  if (last && last.classList.contains(role)) {
    const textNode = last.childNodes[1] || last;
    last.innerHTML = `<span class="role">${role === "user" ? "You" : "🐝 RAGbee"}</span>${escapeHtml(text)}`;
    box.scrollTop = box.scrollHeight;
  }
}

function populateThreadCollectionSelect() {
  const sel = $("thread-collection");
  sel.innerHTML = `<option value="">(none)</option>` +
    state.collections.map(c => `<option value="${c.id}" ${state.activeThread?.collection_id === c.id ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("");
}

async function changeThreadCollection(cid) {
  if (!state.activeThread) return;
  await api(`/api/threads/${state.activeThread.id}`, { method: "PATCH", body: JSON.stringify({ collection_id: cid || null }) });
  state.activeThread.collection_id = cid || null;
  await loadThreads();
}

// ── Chat streaming ─────────────────────────────────────────
async function* streamChat(text) {
  const res = await fetch(`/api/threads/${state.activeThread.id}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(part.slice(6));
        if (data.token) yield data.token;
        if (data.done) return;
      } catch (e) {}
    }
  }
}

async function sendChat() {
  if (state.streaming) return;
  const text = $("chat-input").value.trim();
  if (!text) return;

  if (state.mode === "ingest") {
    await ingestNote(text);
    $("chat-input").value = "";
    return;
  }

  state.streaming = true;
  $("send-btn").disabled = true;
  appendMessage("user", text);
  $("chat-input").value = "";
  appendMessage("assistant", "");

  let full = "";
  try {
    for await (const token of streamChat(text)) {
      full += token;
      updateLastMessage("assistant", full);
    }
    if (!full) updateLastMessage("assistant", "(no response)");
  } catch (e) {
    updateLastMessage("assistant", "⚠ " + e.message);
  } finally {
    state.streaming = false;
    $("send-btn").disabled = false;
  }
}

async function ingestNote(text) {
  try {
    await api(`/api/threads/${state.activeThread.id}/notes`, { method: "POST", body: JSON.stringify({ text }) });
    appendMessage("system", `✓ Note saved to collection.`);
    toast("Note ingested", "success");
  } catch (e) {
    appendMessage("system", "⚠ " + e.message);
  }
}

// ── Mode toggle ────────────────────────────────────────────
function setMode(mode) {
  state.mode = mode;
  const btn = $("mode-toggle");
  const input = $("chat-input");
  const hint = $("mode-hint");
  if (mode === "chat") {
    btn.textContent = "💬 Chat";
    btn.className = "mode-btn mode-chat";
    input.placeholder = "Ask a question...";
    hint.textContent = "Type and send. RAG is on when a collection is attached.";
  } else {
    btn.textContent = "📝 Ingest";
    btn.className = "mode-btn mode-ingest";
    input.placeholder = "Type a note to save to the collection...";
    hint.textContent = "Type and send. The content will be saved as a chunk in the thread's collection.";
  }
}

// ── Settings ───────────────────────────────────────────────
let _providers = [];

function _providerOptions(includeNone = false) {
  let html = includeNone ? `<option value="">(same as chat)</option>` : "";
  html += _providers.map(p =>
    `<option value="${p.id}">${escapeHtml(p.name)}${p.supports_embeddings ? "" : " (chat only)"}</option>`
  ).join("");
  return html;
}

function _updateProviderNote(slot) {
  const sel = $(`${slot}-provider-select`);
  const note = $(`${slot}-provider-note`);
  const input = $(`${slot}-key-input`);
  const p = _providers.find(x => x.id === sel.value);
  if (!p) { note.textContent = "Will use the chat provider's key."; input.placeholder = "(use chat key)"; return; }
  if (p.supports_embeddings) {
    note.textContent = `Default chat: ${p.default_chat} · Default embedding: ${p.default_embedding}`;
  } else {
    note.textContent = `Default chat: ${p.default_chat} · No embeddings — choose a different provider for RAG.`;
  }
  const placeholders = { openrouter: "sk-or-v1-...", opencode_zen: "sk-...", openai: "sk-..." };
  input.placeholder = placeholders[p.id] || "API key";
}

async function openSettings() {
  const s = await api("/api/settings");
  _providers = s.providers || [];
  const chatSel = $("chat-provider-select");
  chatSel.innerHTML = _providers.map(p =>
    `<option value="${p.id}">${escapeHtml(p.name)}</option>`
  ).join("");
  chatSel.value = s.chat.provider || _providers[0]?.id || "";
  chatSel.onchange = () => _updateProviderNote("chat");

  const embSel = $("emb-provider-select");
  embSel.innerHTML = _providerOptions(true);
  embSel.value = s.embedding.provider || "";
  embSel.onchange = () => _updateProviderNote("emb");

  _updateProviderNote("chat");
  _updateProviderNote("emb");

  $("chat-key-input").value = "";
  $("chat-model-input").value = s.chat.model || "";
  $("emb-key-input").value = "";
  $("emb-model-input").value = s.embedding.model || "";

  const status = $("key-status");
  status.style.color = "var(--text-muted)";
  const chatName = _providers.find(p => p.id === s.chat.provider)?.name || "(unset)";
  const embName = s.embedding.provider
    ? (_providers.find(p => p.id === s.embedding.provider)?.name || "(unset)")
    : "same as chat";
  const chatLine = s.chat.has_key ? `${chatName} — ${s.chat.api_key}` : `${chatName} — no key set`;
  const embLine = s.embedding.has_key
    ? `${embName} — ${s.embedding.api_key}`
    : (s.embedding.provider ? `${embName} — no key set` : `${embName} (will use chat key if needed)`);
  status.textContent = `Chat: ${chatLine} · Embeddings: ${embLine}`;

  $("settings-save").textContent = "Save";
  $("settings-save").disabled = false;
  $("settings-modal").hidden = false;
  $("chat-key-input").focus();
}

function closeSettings() {
  $("settings-modal").hidden = true;
}

async function saveSettings() {
  const status = $("key-status");
  const btn = $("settings-save");
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Saving…";
  try {
    const payload = {
      chat: {
        provider: $("chat-provider-select").value,
        api_key: $("chat-key-input").value.trim(),
        model: $("chat-model-input").value.trim(),
      },
      embedding: {
        provider: $("emb-provider-select").value,
        api_key: $("emb-key-input").value.trim(),
        model: $("emb-model-input").value.trim(),
      },
    };
    await api("/api/settings", { method: "POST", body: JSON.stringify(payload) });
    status.textContent = "✓ Saved";
    status.style.color = "var(--success)";
    btn.textContent = "Saved ✓";
    setTimeout(() => {
      closeSettings();
      btn.textContent = originalLabel;
      btn.disabled = false;
    }, 900);
  } catch (e) {
    status.textContent = "⚠ " + e.message;
    status.style.color = "var(--danger)";
    btn.textContent = originalLabel;
    btn.disabled = false;
  }
}

// ── Util ───────────────────────────────────────────────────
function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[c]);
}

// ── Wire up ────────────────────────────────────────────────
async function restoreActiveView() {
  let saved;
  try { saved = JSON.parse(localStorage.getItem("activeId") || "null"); } catch { saved = null; }
  if (!saved) return;
  if (saved.kind === "thread" && state.threads.some(t => t.id === saved.id)) {
    await selectThread(saved.id);
  } else if (saved.kind === "collection" && state.collections.some(c => c.id === saved.id)) {
    await selectCollection(saved.id);
  } else {
    localStorage.removeItem("activeId");
  }
}

async function init() {
  $("settings-btn").onclick = openSettings;
  $("settings-cancel").onclick = closeSettings;
  $("settings-save").onclick = saveSettings;
  $("new-collection").onclick = createCollection;
  $("new-collection-cancel").onclick = closeNewCollection;
  $("new-collection-create").onclick = submitNewCollection;
  $("new-thread").onclick = createThread;
  $("new-thread-cancel").onclick = closeNewThread;
  $("new-thread-create").onclick = submitNewThread;
  $("delete-collection").onclick = deleteCollection;
  $("delete-thread").onclick = deleteThread;
  $("file-input").onchange = (e) => uploadFiles(e.target.files);
  $("add-note").onclick = addNote;
  $("send-btn").onclick = sendChat;
  $("mode-toggle").onclick = () => setMode(state.mode === "chat" ? "ingest" : "chat");
  $("thread-collection").onchange = (e) => changeThreadCollection(e.target.value);
  $("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });
  $("note-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      addNote();
    }
  });
  $("chat-key-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveSettings();
  });
  $("emb-key-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveSettings();
  });
  $("new-collection-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submitNewCollection(); }
    if (e.key === "Escape") closeNewCollection();
  });
  $("new-thread-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submitNewThread(); }
    if (e.key === "Escape") closeNewThread();
  });
  document.querySelectorAll(".modal").forEach(m => {
    m.addEventListener("click", (e) => {
      if (e.target === m) m.hidden = true;
    });
  });

  loadCollections();
  loadThreads();
  setMode("chat");
  await restoreActiveView();
}

init();
