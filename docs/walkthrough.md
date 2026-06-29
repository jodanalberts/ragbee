# RAGbee — a walkthrough of the agent loop

RAGbee is a local personal knowledge management tool. You build **collections**
of files and notes, create **threads** (conversations), and chat with the agent
about your content. The agent retrieves relevant chunks from a collection before
answering, so its responses are grounded in your own knowledge base.

This document walks through `agent.py` — the heart of the system — so students
can see exactly how a RAG agent works and where to extend it.

## The agent loop in one sentence

> Load conversation history → decide which tools to run → execute them → build
> a prompt with context and history → stream the LLM's answer token by token.

## File map

| File | Responsibility |
|---|---|
| `agent.py` | The agent loop. Pure logic, no web, no DB. **Read this first.** |
| `store.py` | SQLite CRUD: collections, chunks, threads, messages. The agent's "memory." |
| `app.py` | FastAPI routes + SSE streaming. The web layer. Skip on first read. |
| `static/` | Frontend (vanilla HTML/JS). |
| `docs/walkthrough.md` | This file. |

## `agent.py` — section by section

`agent.py` is organised into five sections, marked with `── N. Title ──`
banners. Read it top to bottom.

### Section 0 — Text chunking

`chunks(text, n=600, overlap=100)` splits long text into overlapping chunks
(~600 chars each, 100 char overlap). The overlap helps retrieval: a fact that
straddles a chunk boundary is still findable. This is plain string splitting,
no ML involved.

**Exercise 1.** Try different `n` and `overlap` values. Smaller chunks = more
precise retrieval but more embeddings to store. Larger chunks = more context
per hit but noisier similarity scores. What's the sweet spot for your notes?

### Section 1 — Config

```python
PROVIDERS = {
    "openrouter": { ... },
    "opencode_zen": { ... },
    "openai": { ... },
}

K = 5


def get_provider(provider, chat_model=None, embedding_model=None):
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
```

**This is where you swap models and providers.** Each entry in `PROVIDERS` is a
self-contained recipe: base URLs, default models, extra headers (e.g.
OpenRouter wants `HTTP-Referer`), and whether the provider exposes an
embeddings endpoint. `get_provider()` resolves a chosen provider plus optional
model overrides into a flat dict the rest of the agent consumes.

Chat and embedding providers are picked **independently** in Settings — you can
mix and match (e.g. OpenCode Zen for chat, OpenRouter for embeddings). The
agent receives a `cfg` dict bundling both:

```python
cfg = {
    "chat_prov": {...}, "chat_key": "...",
    "emb_prov":  {...}, "emb_key":  "...",
}
```

`chat_stream` uses `cfg["chat_prov"]`; `embed` and `retrieve` use
`cfg["emb_prov"]`. If no embedding provider is configured, the chat provider's
settings are used as a fallback.

**Exercise 2.** Add a fourth provider (Anthropic native, local Ollama, etc.).
Pick a base URL, default model, and whether it supports embeddings. Add it to
`PROVIDERS` and the UI dropdown populates itself — no other code changes.

### Section 2 — HTTP primitive

`_post(url, payload, api_key, stream=False)` is a tiny wrapper around
`urllib.request`. It adds the `Authorization` header (and a couple of
OpenRouter-recommended headers) and returns either parsed JSON or a raw
streaming response.

We use the stdlib instead of the `openai` SDK on purpose: students can see the
exact request being made. No magic, no abstraction.

### Section 3 — Primitives

Four small functions:

- `embed(text, api_key)` — text → vector (one API call)
- `chat_stream(messages, api_key)` — generator yielding tokens from the LLM
- `cosine(a, b)` — pure-Python cosine similarity between two vectors
- `retrieve(store, collection_id, query, api_key, k)` — embed the query, score
  every chunk in the collection by cosine similarity, return the top K
- `build_prompt(state)` — assemble the messages array: system prompt + (optional
  retrieved context) + conversation history + the new question

The `state` dict is the agent's working memory for one turn. It contains
`question`, `context` (retrieved chunks so far), `history` (prior messages),
`collection_id`, and `trace` (which tools ran and what they returned).

**Exercise 3.** Add a different retrieval scoring function (e.g. dot product
instead of cosine) and compare results. When does cosine vs dot product matter?
(Hint: only when vectors aren't normalised.)

**Exercise 4.** Modify `build_prompt` to include the `state["trace"]` as a
"reasoning trace" in the system prompt. Does the LLM answer differently when
it can see which tools ran?

### Section 4 — Tools

```python
def tool_retrieve(state, store, api_key):
    hits = retrieve(store, state["collection_id"], state["question"], api_key)
    state["context"].extend(hits)
    return f"Retrieved {len(hits)} chunks."

TOOLS = {"retrieve": tool_retrieve}
```

A tool is a function that takes `state` (and any extra args), mutates `state`
(side effects: adding to `context`, `trace`, etc.), and returns a string
description of what it did. The `TOOLS` dict maps action names to tool
functions.

**This is the main extension point.** Add a new tool:

```python
def tool_web_search(state, query, api_key):
    # ... call a search API ...
    state["context"].extend(results)
    return f"Found {len(results)} web results."

TOOLS["web_search"] = tool_web_search
```

**Exercise 5.** Add a `tool_rerank` that re-scores the retrieved chunks using
a cross-encoder or a second LLM call. Does it improve answer quality?

**Exercise 6.** Add a `tool_summarise` that condenses the retrieved context
before passing it to the LLM. Useful when retrieval returns many long chunks.

### Section 5 — The agent loop

```python
def decide(state):
    return ["retrieve"] if state["cfg"]["emb_prov"]["supports_embeddings"] else []


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
        result = TOOLS[action](state, store, api_key)
        state["trace"].append((action, result))
    for token in chat_stream(build_prompt(state), api_key):
        yield token
```

Two functions:

- `decide(state)` returns a list of action names. **Currently it returns
  `["retrieve"]` if the thread has a collection, else `[]`.** That's a one-pass
  RAG agent. It runs, it answers, it stops.
- `run(store, thread_id, question, api_key)` is the actual loop. It loads state,
  runs the decided tools, builds the prompt, and yields tokens.

**This is where you turn a one-shot RAG pipeline into a real agent.**

**Exercise 7 — the big one.** Make `decide()` LLM-driven: ask the model which
tool to run next, given the current state. Loop until the LLM returns `"done"`.
You've now built a multi-step agent.

A sketch:

```python
def decide(state):
    messages = [
        {"role": "system", "content": (
            "You are an agent. Pick the next action.\n"
            "Available: " + ", ".join(TOOLS.keys()) + ", or 'done'.\n"
            "Respond with just the action name."
        )},
        {"role": "user", "content": f"Question: {state['question']}\nTrace: {state['trace']}"},
    ]
    # ... call the LLM, return the chosen action ...
```

Then in `run()`, wrap the decide/execute in a `while True:` loop that breaks
when `decide` returns `"done"`.

**Exercise 8.** Add a maximum iteration count to prevent infinite loops
("agent got stuck" is a real failure mode).

**Exercise 9.** Add a reflection step: after the LLM answers, ask it "Are you
confident in this answer? If not, what additional context would help?" and
loop if needed.

## How `app.py` uses `agent.py`

The web layer is thin. The interesting part is the chat streaming endpoint:

```python
@app.post("/api/threads/{tid}/chat")
def chat(tid: str, payload: dict):
    text = payload.get("text", "").strip()
    store.add_message(tid, "user", text)               # 1. save user msg

    def gen():
        full = ""
        for token in agent.run(store, tid, text, api_key):  # 2. run agent
            full += token
            yield f"data: {json.dumps({'token': token})}\n\n"  # 3. SSE
        store.add_message(tid, "assistant", full)        # 4. save assistant
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
```

Four steps: persist the user message, stream tokens from the agent generator,
push each token to the browser via Server-Sent Events, and persist the full
assistant reply when the stream finishes. The `cfg` dict built by
`_build_cfg()` (resolving chat + embedding providers from settings) is passed
to `agent.run(store, tid, text, cfg)`.

The frontend (`static/app.js`) consumes the SSE stream with `fetch` +
`ReadableStream` and appends tokens to the last message bubble as they arrive.
No websockets, no polling — just HTTP streaming.

## What you've learned

If you've worked through this walkthrough, you now understand:

- The anatomy of a RAG pipeline (embed → retrieve → prompt → generate)
- How to make it a loop (`decide()` + `TOOLS` + state)
- How to stream LLM tokens over HTTP (SSE)
- How to swap models and providers (Section 1)
- Where to add new capabilities (the `TOOLS` dict)

That's the core of building agents. The rest is iteration.
