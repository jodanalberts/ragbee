# About RAGbee

RAGbee is a local personal knowledge base with a chat agent. You build collections of files and notes, then talk to the agent about them.

## Quick start

1. Click ⚙ Settings. Pick a chat provider and an embedding provider, paste your API key(s), Save.
2. Click **+ New** under Collections. Name it (e.g. "Physics notes").
3. Add content: click "Upload .md / .txt files" or type a note and click Add note.
4. Click **+ New** under Threads. Optionally give it a name and pick a collection.
5. Type a question and press Enter. The agent retrieves from the collection and answers.

## What it can do

- **Collections**: a library of files and notes. Each collection has its own chunk store and embedding index.
- **Files**: upload `.md` or `.txt` files. They're chunked (~600 chars) and embedded automatically.
- **Notes**: short freeform text added via the collection view or the chat input (Ingest mode).
- **Threads**: a conversation with the agent. Each thread has its own message history and an optional default collection for RAG.
- **Chat ↔ Ingest toggle**: in the chat input, click the mode button to switch between asking questions and saving notes to the active collection.
- **Providers**: chat and embedding providers are picked independently. Supported: OpenRouter, OpenCode Zen, OpenAI. OpenCode Zen has no embeddings, so it can only be used for chat (RAG is disabled when it's the embedding provider).

## Commands

- `add <file>` — ingest a file into the active collection
- `note <text>` — save a freeform note
- `ask <q>` — ask a question (RAG if a collection is attached, plain chat otherwise)
- `list` — show collections and chunk counts
- `clear` — wipe the store (with confirmation)

In the web UI the same actions live in the sidebar and main pane.

## How RAG works here

When you ask a question in a thread with a collection attached:
1. Your question is embedded with the embedding provider.
2. The collection's chunks are ranked by cosine similarity to your question.
3. The top 5 chunks are pasted into the LLM's context as `[source] chunk text`.
4. The LLM answers using only that context, with `[source]` citations.

If the thread has no collection, the agent just chats from its own knowledge and conversation history.

## Troubleshooting

- **"Set your API key in Settings"** — open Settings and save a key for at least the chat provider.
- **"Provider has no embeddings"** — the embedding provider you picked (e.g. OpenCode Zen) doesn't expose an embeddings endpoint. Switch the embedding provider to OpenRouter or OpenAI to use RAG. Chat still works.
- **Modal won't close** — should be fixed; the `[hidden]` attribute is forced with `!important` in the CSS.
- **Stale data after schema change** — `init_db()` auto-detects a missing-table situation and recreates the DB. Your data is lost in that case; re-ingest your files.
- **Lost active view on refresh** — the last selected thread/collection is restored from `localStorage` on page load.

## Extending RAGbee

- New provider: add an entry to `PROVIDERS` in `agent.py` (base URL, default model, whether it supports embeddings). The UI dropdown populates itself.
- New tool: write a `tool_x(state, store, cfg)` and add it to `TOOLS`. Update `decide()` to call it.
- Smarter retrieval: rewrite `decide()` to be LLM-driven, or add a `tool_rerank` that re-scores the top-K.
- Multi-step: turn `run()` into a `while True:` loop that asks the LLM what to do next.

All of this is documented in `ragbee/docs/walkthrough.md`.
