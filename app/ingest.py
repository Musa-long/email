import re

SEPS = ";|\t"

def split_combo(line):
    raw = line.strip().lstrip("\ufeff").rstrip()
    if not raw or raw.startswith("#"):
        return None
    if "://" in raw:
        raw = raw.split("://", 1)[1]

    sep = ":" if ":" in raw else next((s for s in SEPS if s in raw), None)
    if not sep:
        return None

    fields = raw.split(sep)
    idx = next((i for i, f in enumerate(fields) if "@" in f), None)
    if idx is None or idx + 1 >= len(fields):
        return None

    email = fields[idx].strip().lower()
    pw = sep.join(fields[idx + 1:]).strip()
    if "@" not in email or "." not in email.split("@")[-1] or not pw:
        return None
    if len(email) > 320 or len(pw) > 200:
        return None
    return email, pw

def parse_lines(lines, src=""):
    seen, batch = set(), []
    for line in lines:
        pair = split_combo(line)
        if not pair or pair in seen:
            continue
        seen.add(pair)
        batch.append(pair)
    return batch, len(seen)
