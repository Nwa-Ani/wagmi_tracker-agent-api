"""Tiny HTTP server: static UI + job API.  python3 server.py  -> http://localhost:8787"""
import json, os, re, threading, time, traceback, uuid
from urllib.parse import parse_qs, urlparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import core, wallet_check, extras, alerts
from chains import evm, sol_nft, btc

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(core.CACHE, "results"); os.makedirs(RESULTS, exist_ok=True)
SAMPLES = os.path.join(ROOT, "samples")  # committed example results so a fresh deploy can show demos instantly
JOBS = {}; BY_KEY = {}; LOCK = threading.Lock()
SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"); EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
BTC_ADDR = re.compile(r"^(bc1[0-9a-z]{20,90}|[13][1-9A-HJ-NP-Za-km-z]{25,34})$"); BTC_INSC = re.compile(r"^[0-9a-f]{64}i\d+$"); RUNE = re.compile(r"^[A-Za-z•.]{1,40}$|^\d+:\d+$")
CHAINS = ["sol", "eth", "base", "robinhood", "btc"]
CORE_PROGRAM = "CoREENxT6tW1HoK8ypY1SxRMZTcVPm7R94rH4PZNhX7d"

def rkey(chain, asset, kind, addr):
    if chain == "sol" and asset == "coin": return addr if kind == "token" else "wallet_" + addr  # legacy names
    return f"{chain}-{asset}-{'wallet_' if kind == 'wallet' else ''}{re.sub(r'[^0-9A-Za-z:._-]', '_', addr)}"

def result_path(key):
    for d in (RESULTS, SAMPLES):
        f = os.path.join(d, key + ".json")
        if os.path.exists(f): return f
    return None

def validate(chain, asset, kind, a):
    if chain == "sol": return bool(SOL_RE.match(a))
    if chain in evm.CHAINS: return bool(EVM_RE.match(a))
    if chain == "btc": return bool(BTC_ADDR.match(a)) if kind == "wallet" else bool(BTC_INSC.match(a) or RUNE.match(a))
    return False

def runner(chain, asset, kind, a):
    if chain == "sol":
        if asset == "coin": return core.analyze if kind == "token" else wallet_check.check
        return sol_nft.scan_collection if kind == "token" else sol_nft.check_wallet
    if chain == "btc": return btc.scan if kind == "token" else btc.check_wallet
    f = {("coin", "token"): evm.scan_token, ("coin", "wallet"): evm.check_wallet, ("nft", "token"): evm.scan_collection, ("nft", "wallet"): evm.check_nft_wallet}[(asset, kind)]
    return lambda x, log, partial: f(chain, x, log, partial)

def tag(r, chain, asset):
    r.setdefault("chain", chain); r.setdefault("asset", asset)
    r.setdefault("unit", "SOL" if chain == "sol" else "BTC" if chain == "btc" else "USD")
    return r

def run_job(jid, chain, asset, kind, a):
    j = JOBS[jid]
    def log(s): j["status"] = core.redact(s)
    def partial(r): j["result"] = json.loads(json.dumps(tag(r, chain, asset), default=str))
    try:
        r = runner(chain, asset, kind, a)(a, log, partial); tag(r, chain, asset)
        if kind == "wallet":
            log("Paperhands math (prices now)…")
            try: extras.enrich_paperhands(r)
            except Exception: pass
        r = json.loads(json.dumps(r, default=str))
        j["result"] = r; j["state"] = "done"; j["status"] = "Done"
        try:
            with open(os.path.join(RESULTS, rkey(chain, asset, kind, a) + ".json"), "w") as f: json.dump(r, f)
        except OSError: pass
    except Exception as e:
        print(core.redact(traceback.format_exc()), flush=True); j["state"] = "error"; j["status"] = core.redact(e)

def detect(a, chain_hint):
    a = a.strip()
    if BTC_ADDR.match(a): return {"chain": "btc", "kind": "wallet", "asset": "nft"}
    if BTC_INSC.match(a): return {"chain": "btc", "kind": "token", "asset": "nft"}
    if EVM_RE.match(a):
        ch = chain_hint if chain_hint in evm.CHAINS else "eth"
        try:
            if not evm.is_contract(ch, a): return {"chain": ch, "kind": "wallet"}
            for iface in ("80ac58cd", "d9b67a26"):
                r = evm.rpc(ch, "eth_call", [{"to": a, "data": "0x01ffc9a7" + iface + "0" * 56}, "latest"], ttl=86400)
                if r and r != "0x" and int(r, 16) == 1: return {"chain": ch, "kind": "token", "asset": "nft"}
            r = evm.rpc(ch, "eth_call", [{"to": a, "data": "0x313ce567"}, "latest"], ttl=86400)
            return {"chain": ch, "kind": "token", "asset": "coin"} if r and r != "0x" else {"chain": ch, "kind": "wallet"}
        except Exception: return {"chain": ch, "kind": None}
    if SOL_RE.match(a):
        try:
            info = core.rpc("getAccountInfo", [a, {"encoding": "jsonParsed"}], ttl=86400) or {}
            v = info.get("value") or {}
            if v.get("owner") == CORE_PROGRAM: return {"chain": "sol", "kind": "token", "asset": "nft"}
            parsed = (v.get("data") or {}).get("parsed") if isinstance(v.get("data"), dict) else None
            if parsed and parsed.get("type") == "mint":
                dec = (parsed.get("info") or {}).get("decimals")
                return {"chain": "sol", "kind": "token", "asset": "nft" if dec == 0 else "coin"}
            return {"chain": "sol", "kind": "wallet"}
        except Exception: return {"chain": "sol", "kind": "token" if a.endswith("pump") else "wallet"}
    if chain_hint == "btc" and RUNE.match(a): return {"chain": "btc", "kind": "token", "asset": "nft"}
    return {"error": "That doesn't look like a Solana, EVM (0x…) or Bitcoin address."}

CACHE_MEM = {}
def memo(key, ttl, fn):
    hit = CACHE_MEM.get(key)
    if hit and time.time() - hit[0] < ttl: return hit[1]
    v = fn(); CACHE_MEM[key] = (time.time(), v); return v

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=os.path.join(ROOT, "static"), **k)
    def _json(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def end_headers(self):
        if self.path.endswith((".js", ".css", ".html", "/")): self.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def do_GET(self):
        u = urlparse(self.path); p = u.path; q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if p == "/config.js":
                b = ("window.APP_CONFIG=" + json.dumps({**core.APP, "ROAST_LLM": bool(os.environ.get("XAI_API_KEY"))}) + ";").encode()
                self.send_response(200); self.send_header("Content-Type", "application/javascript"); self.send_header("Content-Length", str(len(b))); self.end_headers(); return self.wfile.write(b)
            if p == "/api/detect":
                d = detect(q.get("addr", ""), q.get("chain", "")); return self._json(d, 400 if d.get("error") else 200)
            if p.startswith("/api/job/"):
                j = JOBS.get(p.rsplit("/", 1)[1]); return self._json(j or {"state": "missing"}, 200 if j else 404)
            if p.startswith("/api/result/"):
                f = result_path(os.path.basename(p))
                if f: return self._json({"state": "done", "status": "Cached result", "result": json.load(open(f))})
                return self._json({"state": "missing"}, 404)
            if p == "/api/health":
                return self._json({"ok": True, "base_source": evm.src_label("base"), "rpc_stats": evm.STATS, "jobs_running": sum(1 for j in JOBS.values() if j.get("state") == "running")})
            if p == "/api/leaderboard": return self._json(memo("lb", 60, extras.leaderboard))
            if p == "/api/radar": return self._json(extras.radar(False))
            if p == "/api/alerts": return self._json(alerts.info())
            if p in ("/api/rug", "/api/cabal"):
                ch, a = q.get("chain", "sol"), q.get("addr", "")
                f = result_path(rkey(ch, "coin", "token", a)); scan = json.load(open(f)) if f else None
                if p == "/api/rug":
                    if not validate(ch, "coin", "token", a) or ch == "btc": return self._json({"error": "Rug Check works on Solana and EVM coins."}, 400)
                    return self._json(memo("rug" + ch + a, 600, lambda: extras.rug_sol(a, scan) if ch == "sol" else extras.rug_evm(ch, a.lower(), scan)))
                if not scan: return self._json({"error": "Scan the coin first."}, 404)
                return self._json(memo("cabal" + ch + a, 1800, lambda: extras.cabal(scan)))
        except Exception as e:
            print(core.redact(traceback.format_exc()), flush=True); return self._json({"error": core.redact(e)}, 500)
        return super().do_GET()
    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 65536)) or b"{}")
            if not isinstance(body, dict): raise ValueError
        except Exception:
            return self._json({"error": "Send a JSON object."}, 400)
        try: return self._post(body)
        except Exception as e:
            print(core.redact(traceback.format_exc()), flush=True); return self._json({"error": core.redact(e)}, 500)
    def _post(self, body):
        if self.path.startswith("/api/radar"): return self._json(extras.radar(True))
        if self.path.startswith("/api/roast"):
            return self._json({"text": extras.llm_roast(body.get("stats", {}))})
        if self.path.startswith("/api/analyze") or self.path.startswith("/api/wallet"):
            kind = "wallet" if self.path.startswith("/api/wallet") else "token"
            a = (body.get("mint") or body.get("wallet") or body.get("addr") or "").strip()
            chain = body.get("chain") or "sol"; asset = body.get("asset") or "coin"
            if chain == "btc": asset = "nft"
            if chain in evm.CHAINS: a = a.lower()
            if chain not in CHAINS or asset not in ("coin", "nft") or not validate(chain, asset, kind, a):
                return self._json({"error": "That address doesn't match the chain you picked."}, 400)
            key = rkey(chain, asset, kind, a); fresh = body.get("fresh")
            with LOCK:
                jid = BY_KEY.get(key)
                if jid and JOBS[jid]["state"] == "running": return self._json({"job": jid, "key": key})
                f = result_path(key)
                if not fresh and f and (f.startswith(SAMPLES) or time.time() - os.path.getmtime(f) < 6 * 3600):
                    jid = uuid.uuid4().hex[:10]; JOBS[jid] = {"state": "done", "status": "Cached result (under 6h old)", "result": json.load(open(f))}
                    return self._json({"job": jid, "key": key})
                jid = uuid.uuid4().hex[:10]; JOBS[jid] = {"state": "running", "status": "Starting…", "mint": a, "kind": kind, "chain": chain, "asset": asset, "result": None}; BY_KEY[key] = jid
            threading.Thread(target=run_job, args=(jid, chain, asset, kind, a), daemon=True).start()
            return self._json({"job": jid, "key": key})
        self._json({"error": "not found"}, 404)
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8787)); host = os.environ.get("HOST", "0.0.0.0")
    print(f"Data source: {core.RPC_LABEL}"); print(f"Telegram alerts: {'on' if alerts.start() else 'off (set TELEGRAM_BOT_TOKEN)'}")
    print(f"{core.APP['APP_NAME']} on http://localhost:{port}")
    ThreadingHTTPServer((host, port), H).serve_forever()
