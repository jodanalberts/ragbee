import json
import math
import urllib.request


# ── 0. Text chunking ─────────────────────────────────────────
def chunks(text, n=600, overlap=100):
    parts = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    if not parts:
        return []
    out, buf = [], ""
    for p in parts:
        add = p if not buf else buf + "\n\n" + p
        if len(add) <= n:
            buf = add
        else:
            if buf:
                out.append(buf)
            if len(p) <= n:
                buf = p
            else:
                start = 0
                while start < len(p):
                    out.append(p[start:start + n])
                    start += n - overlap
                buf = ""
    if buf:
        out.append(buf)
    return out


# ── 1. Providers: swap models / providers here ──────────────
PROVIDERS = {
    "openrouter": {
        "name": "OpenRouter",
        "chat_url": "https://openrouter.ai/api/v1/chat/completions",
        "embedding_url": "https://openrouter.ai/api/v1/embeddings",
        "default_chat": "google/gemini-3.1-flash-lite",
        "default_embedding": "text-embedding-3-small",
        "extra_headers": {"HTTP-Referer": "http://localhost", "X-Title": "ragbee"},
        "supports_embeddings": True,
    },
    "opencode_zen": {
        "name": "OpenCode Zen",
        "chat_url": "https://opencode.ai/zen/v1/chat/completions",
        "embedding_url": None,
        "default_chat": "gemini-3.1-flash",
        "default_embedding": None,
        "extra_headers": {},
        "supports_embeddings": False,
    },
    "openai": {
        "name": "OpenAI",
        "chat_url": "https://api.openai.com/v1/chat/completions",
        "embedding_url": "https://api.openai.com/v1/embeddings",
        "default_chat": "gpt-4o-mini",
        "default_embedding": "text-embedding-3-small",
        "extra_headers": {},
        "supports_embeddings": True,
    },
}

K = 5


def get_provider(provider, chat_model=None, embedding_model=None):
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(PROVIDERS)}")
    p = PROVIDERS[provider]
    return {
        "id": provider,
        "name": p["name"],
        "chat_url": p["chat_url"],
        "embedding_url": p["embedding_url"],
        "chat_model": chat_model or p["default_chat"],
        "embedding_model": embedding_model or p["default_embedding"],
        "extra_headers": dict(p["extra_headers"]),
        "supports_embeddings": p["supports_embeddings"],
    }


# ── 2. HTTP primitive (raw urllib, no SDK) ──────────────────
def _post(url, payload, api_key, prov, stream=False):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        **prov["extra_headers"],
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    if stream:
        return urllib.request.urlopen(req, timeout=120)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


# ── 3. Primitives ───────────────────────────────────────────
def embed(text, api_key, prov):
    if not prov["supports_embeddings"]:
        raise RuntimeError(f"{prov['name']} does not provide embeddings; attach a collection that uses a provider with embeddings, or remove the collection from this thread.")
    data = _post(prov["embedding_url"], {"model": prov["embedding_model"], "input": text}, api_key, prov)
    return data["data"][0]["embedding"]


def chat_stream(messages, api_key, prov):
    resp = _post(prov["chat_url"], {"model": prov["chat_model"], "messages": messages, "stream": True}, api_key, prov, stream=True)
    for raw in resp:
        line = raw.decode().strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
        chunk = json.loads(payload)
        delta = chunk["choices"][0].get("delta", {}).get("content", "")
        if delta:
            yield delta


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-12)


def retrieve_from(collection_id, qemb, store, k=K):
    items = store.list_chunks(collection_id)
    scored = [(cosine(qemb, c["embedding"]), c) for c in items if c.get("embedding")]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


def retrieve(store, collection_id, query, api_key, prov, k=K):
    if not prov["supports_embeddings"]:
        return []
    qemb = embed(query, api_key, prov)
    return retrieve_from(collection_id, qemb, store, k)


def build_prompt(state):
    system = (
        "You are RAGbee, a local personal knowledge agent. "
        "Answer using the provided context and conversation history. "
        "The context may come from the user's collection AND from a built-in 'About RAGbee' guide — use both when relevant. "
        "If a question is about RAGbee itself (how to use it, what it can do, troubleshooting), the About guide takes priority. "
        "If the answer is not in any context, say you don't know. "
        "Cite sources as [source]."
    )
    messages = [{"role": "system", "content": system}]
    if state["context"]:
        ctx = "\n\n".join(f"[{c['source']}] {c['text']}" for c in state["context"])
        messages.append({"role": "system", "content": f"Context:\n{ctx}"})
    messages.extend(state["history"])
    messages.append({"role": "user", "content": state["question"]})
    return messages


# ── 4. Tools the agent can call (extensible) ────────────────
def tool_retrieve(state, store, cfg):
    if not cfg["emb_prov"]["supports_embeddings"]:
        return f"Skipped: {cfg['emb_prov']['name']} has no embeddings endpoint. Chat continues without retrieval."
    qemb = embed(state["question"], cfg["emb_key"], cfg["emb_prov"])
    user_hits, about_hits = [], []
    if state.get("collection_id"):
        user_hits = retrieve_from(state["collection_id"], qemb, store)
    about_cid = store.get_about_collection_id()
    if about_cid and about_cid != state.get("collection_id"):
        about_hits = retrieve_from(about_cid, qemb, store)
    state["context"].extend(user_hits + about_hits)
    return f"Retrieved {len(user_hits)} user + {len(about_hits)} about chunks."


TOOLS = {"retrieve": tool_retrieve}
# Students: add tools here, e.g. tool_web_search, tool_rerank, ...


# ── 5. The agent loop ────────────────────────────────────────
def decide(state):
    if state["cfg"]["emb_prov"]["supports_embeddings"]:
        return ["retrieve"]
    return []


def run(store, thread_id, question, cfg):
    thread = store.get_thread(thread_id)
    state = {
        "question": question,
        "context": [],
        "history": store.list_messages(thread_id),
        "collection_id": thread["collection_id"] if thread else None,
        "cfg": cfg,
        "trace": [],
    }
    for action in decide(state):
        result = TOOLS[action](state, store, cfg)
        state["trace"].append((action, result))
    for token in chat_stream(build_prompt(state), cfg["chat_key"], cfg["chat_prov"]):
        yield token
