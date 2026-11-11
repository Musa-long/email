import os, sqlite3, threading

DB_PATH = os.environ.get("DB_PATH", "/var/data/creds.db")
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS creds(
  email TEXT NOT NULL,
  pass  TEXT NOT NULL,
  src   TEXT DEFAULT '',
  PRIMARY KEY(email, pass)
) WITHOUT ROWID;
"""

def conn():
    if not hasattr(_local, "c"):
        c = sqlite3.connect(DB_PATH, timeout=120, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA cache_size=-262144")
        c.execute("PRAGMA temp_store=MEMORY")
        c.execute("PRAGMA mmap_size=1073741824")
        _local.c = c
    return _local.c

def init():
    c = conn()
    c.executescript(SCHEMA)
    c.commit()

def insert_batch(rows, src=""):
    c = conn()
    before = c.total_changes
    c.executemany("INSERT OR IGNORE INTO creds(email, pass, src) VALUES (?,?,?)",
                  [(e, p, src) for e, p in rows])
    c.commit()
    return c.total_changes - before

def lookup_many(emails):
    out, c = {}, conn()
    for i in range(0, len(emails), 900):
        chunk = emails[i:i + 900]
        q = "SELECT email, pass FROM creds WHERE email IN (%s)" % ",".join("?" * len(chunk))
        for e, p in c.execute(q, chunk):
            out.setdefault(e, set()).add(p)
    return out

def stats():
    c = conn()
    rows = c.execute("SELECT COUNT(*) FROM creds").fetchone()[0]
    uniq = c.execute("SELECT COUNT(DISTINCT email) FROM creds").fetchone()[0]
    return {"rows": rows, "distinct_emails": uniq}
