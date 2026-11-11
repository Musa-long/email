import asyncio, csv, os, time, uuid
from pathlib import Path
import db

DATA = Path(os.environ.get("DATA_DIR", "/var/data"))
JOBS = {}

class Job:
    def __init__(self, kind, total=0, only_hits=False):
        self.id = uuid.uuid4().hex[:12]
        self.kind, self.total, self.done, self.hits = kind, total, 0, 0
        self.only_hits, self.state = only_hits, "running"
        self.started, self.q = time.time(), asyncio.Queue()
        self.out = DATA / "results" / f"{self.id}.csv"
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.out, "w", newline="", encoding="utf-8")
        self.w = csv.writer(self.fh)
        self.w.writerow(["email", "password", "verdict"])
        JOBS[self.id] = self

    def row(self, email, pw, verdict):
        if self.only_hits and verdict != "hit":
            return
        self.w.writerow([email, pw, verdict])

    def emit(self, ev, **kw):
        self.q.put_nowait({"event": ev, **kw})

    def close(self, state):
        self.state = state
        self.fh.flush()
        self.fh.close()
        self.emit("done", state=state, done=self.done, total=self.total, hits=self.hits)

async def run_pairs(job, pairs):
    CH = 2000
    for i in range(0, len(pairs), CH):
        chunk = pairs[i:i + CH]
        found = await asyncio.to_thread(db.lookup_many, [e for e, _ in chunk])
        for e, p in chunk:
            hit = p in found.get(e, ())
            job.done += 1
            if hit:
                job.hits += 1
            job.row(e, p, "hit" if hit else "miss")
        job.emit("progress", done=job.done, total=job.total, hits=job.hits)
    job.close("finished")

async def run_emails(job, emails):
    CH = 500
    for i in range(0, len(emails), CH):
        chunk = emails[i:i + CH]
        found = await asyncio.to_thread(db.lookup_many, chunk)
        for e in chunk:
            job.done += 1
            for p in found.get(e, ()):
                job.hits += 1
                job.row(e, p, "hit")
            if e not in found:
                job.row(e, "", "no_known_password")
        job.emit("progress", done=job.done, total=job.total, hits=job.hits)
    job.close("finished")

async def run_ingest(job, pairs, src):
    CH = 20000
    for i in range(0, len(pairs), CH):
        added = await asyncio.to_thread(db.insert_batch, pairs[i:i + CH], src)
        job.done += added
        job.emit("progress", done=job.done, total=job.total, hits=added)
    job.close("finished")
