import asyncio, base64, json, os, secrets
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, Response
import db, ingest, jobs

DATA = Path(os.environ.get("DATA_DIR", "/var/data"))
DATA.mkdir(parents=True, exist_ok=True)

BASIC_USER = os.environ.get("BASIC_USER", "")
BASIC_PASS = os.environ.get("BASIC_PASS", "")

app = FastAPI(title="CredsCheck")

@app.middleware("http")
async def auth(request: Request, call_next):
    if not BASIC_USER or request.url.path == "/healthz":
        return await call_next(request)
    h = request.headers.get("authorization", "")
    if h.startswith("Basic "):
        try:
            u, p = base64.b64decode(h[6:]).decode().split(":", 1)
            if secrets.compare_digest(u, BASIC_USER) and secrets.compare_digest(p, BASIC_PASS):
                return await call_next(request)
        except Exception:
            pass
    return Response("Auth required", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="credscheck"'})

@app.on_event("startup")
def _start():
    db.init()

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "static" / "index.html").read_text()

@app.get("/api/stats")
def stats():
    return db.stats()

def _read_payload(text, upload):
    if upload is not None:
        return upload.file.read().decode("utf-8", "ignore").splitlines()
    return (text or "").splitlines()

@app.post("/api/check/pairs")
async def check_pairs(text: str = Form(""), file: UploadFile = File(None),
                      only_hits: bool = Form(False)):
    pairs, _ = ingest.parse_lines(_read_payload(text, file))
    if not pairs:
        raise HTTPException(400, "no valid email:password pairs found")
    job = jobs.Job("pairs", len(pairs), only_hits)
    asyncio.create_task(jobs.run_pairs(job, pairs))
    return {"job": job.id, "total": len(pairs)}

@app.post("/api/check/emails")
async def check_emails(text: str = Form(""), file: UploadFile = File(None)):
    lines = _read_payload(text, file)
    emails, seen = [], set()
    for l in lines:
        e = l.strip().lower()
        if "@" in e and e not in seen:
            seen.add(e); emails.append(e)
    if not emails:
        raise HTTPException(400, "no valid emails found")
    job = jobs.Job("emails", len(emails))
    asyncio.create_task(jobs.run_emails(job, emails))
    return {"job": job.id, "total": len(emails)}

@app.post("/api/ingest")
async def do_ingest(text: str = Form(""), file: UploadFile = File(None),
                    src: str = Form("manual")):
    pairs, _ = ingest.parse_lines(_read_payload(text, file), src)
    if not pairs:
        raise HTTPException(400, "no valid pairs found")
    job = jobs.Job("ingest", len(pairs))
    asyncio.create_task(jobs.run_ingest(job, pairs, src))
    return {"job": job.id, "total": len(pairs)}

@app.get("/api/job/{jid}/stream")
async def stream(jid: str):
    job = jobs.JOBS.get(jid)
    if not job:
        raise HTTPException(404)
    async def gen():
        yield f"event: hello\ndata: {json.dumps({'total': job.total})}\n\n"
        while True:
            try:
                ev = await asyncio.wait_for(job.q.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": ping\n\n"; continue
            yield f"event: {ev['event']}\ndata: {json.dumps(ev)}\n\n"
            if ev["event"] == "done":
                break
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/job/{jid}/result.csv")
def result(jid: str):
    job = jobs.JOBS.get(jid)
    if not job:
        raise HTTPException(404)
    return FileResponse(job.out, filename=f"results-{jid}.csv", media_type="text/csv")
