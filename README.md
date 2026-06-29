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
