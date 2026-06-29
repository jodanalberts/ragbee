# RAGbee

A local RAG knowledge base with a chat agent. You build collections of files
and notes, then talk to the agent about them. Everything runs on your
machine; your data and your API keys stay with you.

This is also a teaching project. `agent.py` is small and walks through the
whole RAG loop — embed, retrieve, prompt, generate, stream — with the
`TOOLS` and `decide()` scaffold left obviously extensible. See
[`docs/walkthrough.md`](docs/walkthrough.md) for a guided tour with exercises.

## Quick start

```
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000. Set an API key in Settings, create a collection,
add a file or note, create a thread, start chatting.

## Providers

Chat and embedding providers are picked independently. Supported:

- **OpenRouter** — chat and embeddings
- **OpenCode Zen** — chat only (no embeddings endpoint, so RAG is disabled
  when it's the embedding provider)
- **OpenAI** — chat and embeddings

## Using it

- **Left sidebar** lists your Collections (knowledge) and Threads
  (conversations).
- **Collection view** shows the chunks; add files (`.md`/`.txt`) or notes.
- **Thread view** is the chat. The mode toggle switches between 💬 Chat
  (ask questions) and 📝 Ingest (save a note straight into the active
  collection). The collection dropdown in the header changes which library
  the thread draws from.
- An **"About RAGbee"** collection is seeded at startup so the agent can
  answer questions about itself.

## Code layout

- `agent.py` — the agent loop, no web or DB code
- `store.py` — SQLite CRUD
- `app.py` — FastAPI + SSE streaming
- `static/` — vanilla JS frontend
- `docs/walkthrough.md` — student guide with 9 exercises

Python 3.10+. An API key for one of the supported providers.

## Ideas to extend it

A few things you can build yourself once you're comfortable with the code.
Roughly quick → involved.

**Quick wins**
- Add a provider. `agent.PROVIDERS` is a dict of recipes; adding Ollama,
  Anthropic, or a local model is ~5 lines and the UI dropdown picks it up.
- Tweak the chunker. `agent.chunks(text, n, overlap)` controls how files
  get split. Different sizes give very different retrieval behaviour —
  try it and see.
- Customize the system prompt in `agent.build_prompt` to give the agent a
  personality, or add a "refuse to answer" rule for specific topics.
- Change the default models. Each provider entry has `default_chat` and
  `default_embedding` — point them at whatever you actually use.

**Medium**
- A web search tool. Write `tool_web_search(state, store, cfg)`, register
  it in `TOOLS`, update `decide()` to pick it when a question needs
  current information.
- Re-ranking. After the initial cosine search, score the top-K again with
  a cross-encoder or a second LLM call. Often a real quality bump.
- Hybrid search. Combine BM25 (keyword) scores with cosine (semantic)
  scores. Useful when exact terms matter — names, code identifiers, error
  messages.
- Auto-title threads. When a thread is created, send the first message
  to the LLM and ask for a 3–5 word title. Store it on the thread.
- PDF / DOCX support. `app.upload_files` currently reads bytes as UTF-8.
  Add `pypdf` or `python-docx` and decode in the endpoint.

**More involved**
- Make the agent loop LLM-driven. Replace the hardcoded `decide()` with a
  call to the LLM that picks the next action, then loop until it says
  "done". Turns the one-shot pipeline into a real multi-step agent.
- A reflection step. After the LLM answers, ask "are you confident?".
  If not, retrieve more and try again.
- Swap the storage backend. `store.py` is plain functions over SQLite;
  swap the implementation for Postgres, DuckDB, or a JSON file store.
- Build a new tool. Anything with a `(state, store, cfg) -> result`
  signature is a tool: calendar lookup, code execution, email draft,
  file search across the filesystem. Register it and the agent can use it.
