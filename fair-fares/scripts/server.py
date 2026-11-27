#!/usr/bin/env python3
"""Local server for the fair-fares form (Python standard library only).

  python3 server.py [--port 8765] [--no-open] [--page results]

Binds to 127.0.0.1 only. POSTs must carry the header X-Fair-Fares: 1 (blocks cross-site form posts).
Writes ~/.fair-fares/server.json with the port, so other scripts can find it.
Events for the agent (start, book, check_again) go to ~/.fair-fares/events.jsonl; read them with wait_event.py.
"""
import json, os, sys, gzip, mimetypes, socket, threading, time, webbrowser, datetime, re, subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ASSETS, DATA, STATE, read_json, write_json, current_run, config
import doc_check

FORM = ASSETS / "form"
EVENTS = STATE / "events.jsonl"
_lock = threading.Lock()


def emit(kind, payload):
    with _lock:
        n = 0
        if EVENTS.exists():
            with open(EVENTS, encoding="utf-8") as f:
                n = sum(1 for _ in f)
        ev = {"id": n + 1, "type": kind, "at": datetime.datetime.now().isoformat(timespec="seconds"), "data": payload}
        with open(EVENTS, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev


def dest_docs_with_model(country, children):
    base = doc_check.destination_documents(country, children)
    if base["covered_by_rules"]:
        return base
    cache = read_json(STATE / "destdocs_cache.json", {}) or {}
    ck = f"{country}:{int(children)}"
    if ck in cache:
        base["documents"] += cache[ck]
        base["model"] = "cached"
        return base
    cmd = doc_check.model_cmd()
    if not cmd:
        base["model"] = "unavailable"
        return base
    prompt = (f"List the travel documents a foreign visitor to country {country} may need besides a passport "
              f"(visas, e-visas, travel authorisations, arrival cards, residence permits that replace a visa"
              f"{', documents for children' if children else ''}). Answer ONLY a JSON array of objects "
              f'{{"id": short_snake_id, "label": short label}}. Max 8 items.')
    full = [a.replace("{prompt}", prompt) for a in cmd]
    if "{prompt}" not in " ".join(cmd):
        full.append(prompt)
    try:
        out = subprocess.run(full, capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL).stdout
        arr = json.loads(re.search(r"\[.*\]", out, re.S).group(0))
        extra = [{"id": str(d["id"])[:40], "label": str(d["label"])[:120], "source": "model"} for d in arr
                 if isinstance(d, dict) and d.get("id") and d.get("label")][:8]
        have = {d["id"] for d in base["documents"]}
        extra = [d for d in extra if d["id"] not in have]
        cache[ck] = extra
        write_json(STATE / "destdocs_cache.json", cache)
        base["documents"] += extra
        base["model"] = "ok"
    except Exception as e:
        base["model"] = f"error: {e.__class__.__name__}"
    return base


class H(BaseHTTPRequestHandler):
    server_version = "fair-fares/1.0"

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", gz=False):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        if gz and "gzip" in (self.headers.get("Accept-Encoding") or "") and len(body) > 2048:
            body = gzip.compress(body, 6)
            self.send_response(code)
            self.send_header("Content-Encoding", "gzip")
        else:
            self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 5_000_000:
            raise ValueError("too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path
        if p in ("/", "/index.html"):
            return self.file(FORM / "index.html")
        if p.startswith("/form/"):
            return self.file(FORM / p[6:])
        if p.startswith("/data/"):
            name = os.path.basename(p)
            if name.endswith(".json"):
                return self.file(DATA / name, gz=True)
        if p == "/api/settings":
            return self.send(200, read_json(STATE / "settings.json", {}) or {})
        if p == "/api/meta":
            return self.send(200, {"data": read_json(DATA / "meta.json", {}), "config": config(),
                                   "setup": read_json(STATE / "setup_cache.json", {}), "fx": read_json(STATE / "fx.json", {})})
        if p == "/api/destdocs":
            c = (q.get("country") or [""])[0].upper()[:2]
            kids = (q.get("children") or ["0"])[0] == "1"
            return self.send(200, dest_docs_with_model(c, kids))
        if p == "/api/results":
            run = current_run()
            res = read_json(run / "results.json", None) if run else None
            prog = read_json(run / "progress.json", None) if run else None
            return self.send(200, {"run": str(run) if run else None, "results": res, "progress": prog})
        if p == "/api/booking-status":
            run = current_run()
            return self.send(200, read_json(run / "booking_status.json", {}) if run else {})
        return self.send(404, {"error": "not found"})

    def do_POST(self):
        if self.headers.get("X-Fair-Fares") != "1":
            return self.send(403, {"error": "missing header"})
        p = urlparse(self.path).path
        try:
            b = self.body()
        except Exception:
            return self.send(400, {"error": "bad json"})
        if p == "/api/settings":  # autosave draft (pre-fill next time)
            b["saved_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            write_json(STATE / "settings.json", b)
            return self.send(200, {"ok": True})
        if p == "/api/start":
            b["saved_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            write_json(STATE / "settings.json", b)
            ev = emit("start", {"settings_file": str(STATE / "settings.json")})
            return self.send(200, {"ok": True, "event": ev["id"]})
        if p == "/api/doccheck":
            force = bool(b.pop("_force", False))
            return self.send(200, doc_check.run(b, force=force))
        if p == "/api/book":
            ev = emit("book", {"option_id": str(b.get("option_id"))[:60]})
            return self.send(200, {"ok": True, "event": ev["id"]})
        return self.send(404, {"error": "not found"})

    def file(self, path, gz=False):
        path = path.resolve()
        if not (str(path).startswith(str(FORM.resolve())) or str(path).startswith(str(DATA.resolve()))):
            return self.send(403, {"error": "forbidden"})
        if not path.is_file():
            return self.send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript") or ctype.endswith("json"):
            ctype += "; charset=utf-8"
        return self.send(200, path.read_bytes(), ctype, gz=gz or ctype.startswith("text/") or "javascript" in ctype)


def free_port(start):
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("no free port")


def alive(port):
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=1)
        return True
    except Exception:
        return False


def main():
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8765
    page = args[args.index("--page") + 1] if "--page" in args else ""
    info = read_json(STATE / "server.json", {}) or {}
    url_suffix = f"#{page}" if page else ""
    if info.get("port") and alive(info["port"]):  # reuse a running server
        url = f"http://127.0.0.1:{info['port']}/{url_suffix}"
        print(json.dumps({"reused": True, "url": url}))
        if "--no-open" not in args:
            webbrowser.open(url)
        return
    port = free_port(port)
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{port}/{url_suffix}"
    write_json(STATE / "server.json", {"port": port, "pid": os.getpid(), "url": url, "started": time.time()})
    print(json.dumps({"reused": False, "url": url}), flush=True)
    if "--no-open" not in args:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
