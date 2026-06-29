import json
import webbrowser
from pathlib import Path
from threading import Timer

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import agent
import store

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="RAGbee")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

store.init_db()
store.seed_about_collection()
store.seed_about_thread()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# ── Settings ────────────────────────────────────────────────
def _provider_meta():
    return [
        {"id": pid, "name": p["name"], "supports_embeddings": p["supports_embeddings"],
         "default_chat": p["default_chat"], "default_embedding": p["default_embedding"]}
        for pid, p in agent.PROVIDERS.items()
    ]


@app.get("/api/settings")
def get_settings():
    cfg = store.get_config()
    return {
        "chat": {**cfg["chat"], "api_key": store.mask_key(cfg["chat"]["api_key"]), "has_key": bool(cfg["chat"]["api_key"])},
        "embedding": {**cfg["embedding"], "api_key": store.mask_key(cfg["embedding"]["api_key"]), "has_key": bool(cfg["embedding"]["api_key"])},
        "providers": _provider_meta(),
    }


@app.post("/api/settings")
def save_settings(payload: dict):
    current = store.get_config()
    for slot in ("chat", "embedding"):
        if slot not in payload:
            continue
        sub = payload[slot]
        prov = (sub.get("provider") or "").strip() or None
        if prov and prov not in agent.PROVIDERS:
            raise HTTPException(400, f"Unknown {slot} provider: {prov}")
        api_key = (sub.get("api_key") or "").strip()
        model = (sub.get("model") or "").strip() or None
        if prov and not api_key:
            api_key = current[slot]["api_key"]
        current[slot] = {"provider": prov, "api_key": api_key, "model": model}
    store.set_config(current)
    return {"ok": True}


def _build_cfg():
    cfg = store.get_config()
    chat = cfg["chat"]
    emb = cfg["embedding"]
    if not chat["provider"] or not chat["api_key"]:
        raise HTTPException(400, "Set a chat provider and API key in Settings")
    chat_prov = agent.get_provider(chat["provider"], chat_model=chat["model"])
    if emb["provider"] and emb["api_key"]:
        emb_prov = agent.get_provider(emb["provider"], embedding_model=emb["model"])
        emb_key = emb["api_key"]
    else:
        emb_prov = agent.get_provider(chat["provider"], embedding_model=chat["model"])
        emb_key = chat["api_key"]
    return {
        "chat_prov": chat_prov,
        "chat_key": chat["api_key"],
        "emb_prov": emb_prov,
        "emb_key": emb_key,
    }


def _emb_cfg():
    cfg = store.get_config()
    emb = cfg["embedding"]
    chat = cfg["chat"]
    if emb["provider"] and emb["api_key"]:
        prov = agent.get_provider(emb["provider"], embedding_model=emb["model"])
        key = emb["api_key"]
    elif chat["provider"] and chat["api_key"]:
        prov = agent.get_provider(chat["provider"], embedding_model=chat["model"])
        key = chat["api_key"]
    else:
        raise HTTPException(400, "Set an embedding provider (or chat provider) and API key in Settings")
    return prov, key


# ── Collections ─────────────────────────────────────────────
@app.get("/api/collections")
def collections():
    return store.list_collections()


@app.post("/api/collections")
def make_collection(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    return {"id": store.create_collection(name)}


@app.delete("/api/collections/{cid}")
def remove_collection(cid: str):
    store.delete_collection(cid)
    return {"ok": True}


@app.get("/api/collections/{cid}/chunks")
def get_chunks(cid: str):
    return store.list_chunks(cid)


@app.post("/api/collections/{cid}/files")
async def upload_files(cid: str, files: list[UploadFile] = File(...)):
    prov, api_key = _emb_cfg()
    if not prov["supports_embeddings"]:
        raise HTTPException(400, f"{prov['name']} has no embeddings; pick an embedding provider that supports them, or set one in Settings.")
    store.seed_about_chunks(lambda t: agent.embed(t, api_key, prov))
    added = 0
    for f in files:
        text = (await f.read()).decode("utf-8", errors="ignore")
        for part in agent.chunks(text):
            store.add_chunk(cid, f.filename, part, agent.embed(part, api_key, prov))
            added += 1
    return {"added": added}


@app.post("/api/collections/{cid}/notes")
def add_note(cid: str, payload: dict):
    prov, api_key = _emb_cfg()
    if not prov["supports_embeddings"]:
        raise HTTPException(400, f"{prov['name']} has no embeddings; pick an embedding provider that supports them, or set one in Settings.")
    store.seed_about_chunks(lambda t: agent.embed(t, api_key, prov))
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    store.add_chunk(cid, "note", text, agent.embed(text, api_key, prov))
    return {"ok": True}


@app.delete("/api/collections/{cid}/chunks/{ckid}")
def remove_chunk(cid: str, ckid: str):
    store.delete_chunk(ckid)
    return {"ok": True}


# ── Threads ─────────────────────────────────────────────────
@app.get("/api/threads")
def threads():
    return store.list_threads()


@app.post("/api/threads")
def make_thread(payload: dict):
    title = (payload.get("title") or "New thread").strip()
    cid = payload.get("collection_id") or None
    return {"id": store.create_thread(title, cid)}


@app.patch("/api/threads/{tid}")
def patch_thread(tid: str, payload: dict):
    fields = {k: v for k, v in payload.items() if k in ("title", "collection_id")}
    store.update_thread(tid, **fields)
    return {"ok": True}


@app.delete("/api/threads/{tid}")
def remove_thread(tid: str):
    store.delete_thread(tid)
    return {"ok": True}


@app.get("/api/threads/{tid}/messages")
def messages(tid: str):
    return store.list_messages(tid)


@app.post("/api/threads/{tid}/chat")
def chat(tid: str, payload: dict):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    cfg = _build_cfg()
    store.seed_about_chunks(lambda t: agent.embed(t, cfg["emb_key"], cfg["emb_prov"]))
    store.add_message(tid, "user", text)

    def gen():
        full = ""
        for token in agent.run(store, tid, text, cfg):
            full += token
            yield f"data: {json.dumps({'token': token})}\n\n"
        store.add_message(tid, "assistant", full)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/threads/{tid}/notes")
def thread_note(tid: str, payload: dict):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    prov, api_key = _emb_cfg()
    if not prov["supports_embeddings"]:
        raise HTTPException(400, f"{prov['name']} has no embeddings; cannot ingest notes.")
    thread = store.get_thread(tid)
    if not thread or not thread.get("collection_id"):
        raise HTTPException(400, "thread has no collection — attach one in the chat header")
    store.add_chunk(thread["collection_id"], "note", text, agent.embed(text, api_key, prov))
    return {"ok": True}


def main():
    import uvicorn
    url = "http://localhost:8000"
    print(f"\U0001f41d RAGbee running at {url}")
    Timer(1, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
