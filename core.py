"""Early buyer wallet tracker - data + analysis core.
Free, keyless sources only: Solana public RPC, DexScreener, GeckoTerminal.
Everything is cached to ./cache so repeated runs survive rate limits."""
import hashlib, json, os, re, threading, time, math
from concurrent.futures import ThreadPoolExecutor
import requests
APP = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
from solders.pubkey import Pubkey

# RPC choice: HELIUS_API_KEY (env only, never logged/stored) > SOLANA_RPC > free public RPC.
HELIUS_KEY = os.environ.get("HELIUS_API_KEY", "").strip()
if HELIUS_KEY:
    RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"; RPC_LABEL = "Helius RPC"
else:
    RPC = os.environ.get("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
    RPC_LABEL = "custom RPC" if os.environ.get("SOLANA_RPC") else "Solana public RPC"
WORKERS = int(os.environ.get("WORKERS", 8 if HELIUS_KEY else 3))

def redact(text):
    """Strip any API key from text before it reaches logs, job status or results."""
    text = str(text)
    if HELIUS_KEY: text = text.replace(HELIUS_KEY, "***")
    for k in ("ETHERSCAN_API_KEY", "ALCHEMY_API_KEY", "OPENSEA_API_KEY", "TELEGRAM_BOT_TOKEN", "XAI_API_KEY"):
        v = os.environ.get(k, "").strip()
        if len(v) >= 8: text = text.replace(v, "***")
    text = re.sub(r"(g\.alchemy\.com/v2/)[^/?\s'\"]+", r"\1***", text)
    text = re.sub(r"apikey=[^&\s'\"]+", "apikey=***", text)
    return re.sub(r"api-key=[^&\s'\"]+", "api-key=***", text)
# Cache dir is disposable (fine on ephemeral disks like Render free tier). Override with CACHE_DIR.
CACHE = os.environ.get("CACHE_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
try:
    os.makedirs(CACHE, exist_ok=True)
except OSError:
    CACHE = "/tmp/wagmi_tracker-cache"; os.makedirs(CACHE, exist_ok=True)
PUMP = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
WSOL = "So11111111111111111111111111111111111111112"
STABLES = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}

MAX_CURVE_TXS = int(os.environ.get("MAX_CURVE_TXS", 1200))
MIN_BUY_SOL = float(os.environ.get("MIN_BUY_SOL", 0.01))  # smaller buys = dust/bot, ignored
N_EARLY = int(os.environ.get("N_EARLY", 40))       # unique early buyers to collect
WALLET_TXS = int(os.environ.get("WALLET_TXS", 50)) # recent txs sampled per wallet
PEAK_BUDGET = int(os.environ.get("PEAK_BUDGET", 25))  # GeckoTerminal OHLCV calls per job

_sess = requests.Session()
_sess.headers["User-Agent"] = APP["APP_NAME"].lower().replace(" ", "-") + "/0.1"

class Limiter:
    def __init__(self, per_sec):
        self.gap = 1.0 / per_sec; self.lock = threading.Lock(); self.next = 0.0
    def wait(self):
        with self.lock:
            now = time.time(); t = max(now, self.next); self.next = t + self.gap
        if t > now: time.sleep(t - now)

RPC_LIM = Limiter(float(os.environ.get("RPC_RPS", 8 if HELIUS_KEY else 3.3)))
GT_LIM = Limiter(0.3)   # GeckoTerminal public: ~30/min, stay under
DS_LIM = Limiter(4)

def _ckey(*parts):
    return os.path.join(CACHE, hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest() + ".json")

def _cget(key, ttl):
    try:
        if ttl is None or time.time() - os.path.getmtime(key) < ttl:
            with open(key) as f: return json.load(f)
    except Exception: pass
    return None

def _cput(key, val):
    try:
        tmp = key + ".tmp%d" % threading.get_ident()
        with open(tmp, "w") as f: json.dump(val, f)
        os.replace(tmp, key)
    except OSError: pass  # cache is best-effort

def rpc(method, params, ttl=None):
    """ttl=None -> cache forever (immutable data)."""
    key = _ckey("rpc", method, params)
    hit = _cget(key, ttl)
    if hit is not None: return hit["r"]
    for i in range(10):
        RPC_LIM.wait()
        try:
            r = _sess.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=40)
            d = r.json()
            if "result" in d:
                _cput(key, {"r": d["result"]}); return d["result"]
        except Exception: pass
        time.sleep(1.0 + i * 1.5)
    raise RuntimeError(f"{RPC_LABEL} {method} failed after retries (rate limit or outage)")

def http_json(url, lim, ttl=600):
    key = _ckey("http", url); hit = _cget(key, ttl)
    if hit is not None: return hit["r"]
    for i in range(6):
        lim.wait()
        try:
            r = _sess.get(url, timeout=30)
            if r.status_code == 404: _cput(key, {"r": None}); return None
            if r.status_code == 200:
                d = r.json(); _cput(key, {"r": d}); return d
        except Exception: pass
        time.sleep(2 + i * 3)
    return None

# ---------------- market data ----------------
def ds_pairs(mints):
    """DexScreener batch (<=30 per call). Returns {mint: best SOL-quoted pair or best pair}."""
    out = {}
    mints = list(dict.fromkeys(mints))
    for i in range(0, len(mints), 30):
        chunk = mints[i:i + 30]
        d = http_json("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(chunk), DS_LIM, ttl=600) or []
        for p in d:
            m = p["baseToken"]["address"]
            if m not in chunk: continue
            score = (p.get("quoteToken", {}).get("address") == WSOL, (p.get("liquidity") or {}).get("usd") or 0)
            if m not in out or score > out[m][0]: out[m] = (score, p)
    return {m: v[1] for m, v in out.items()}

def gt_peak_native(pool, since_ts):
    """Highest price (in quote token, i.e. SOL for SOL pairs) after since_ts, from hourly OHLCV."""
    d = http_json(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/hour?aggregate=1&limit=1000&currency=token&token=base", GT_LIM, ttl=1800)
    try: rows = d["data"]["attributes"]["ohlcv_list"]
    except Exception: return None
    hs = [r[2] for r in rows if r[0] + 3600 > since_ts]
    return max(hs) if hs else None

# ---------------- tx parsing ----------------
def get_tx(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])

def tx_deltas(tx, owner):
    """Token deltas by mint for owner, plus SOL delta (lamports + wSOL)."""
    keys = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
    m = tx["meta"]; d = {}
    for sign, lst in ((-1, m.get("preTokenBalances") or []), (1, m.get("postTokenBalances") or [])):
        for b in lst:
            if b.get("owner") != owner: continue
            d[b["mint"]] = d.get(b["mint"], 0.0) + sign * float(b["uiTokenAmount"]["uiAmount"] or 0)
    sol = 0.0
    if owner in keys:
        i = keys.index(owner); sol = (m["postBalances"][i] - m["preBalances"][i]) / 1e9
    sol += d.pop(WSOL, 0.0)
    return {k: v for k, v in d.items() if abs(v) > 1e-12}, sol, keys[0]

def all_sigs(addr, max_pages, progress=None):
    """Page getSignaturesForAddress back to the very first tx. Returns (oldest-first list, complete?)."""
    sigs, before = [], None
    for p in range(max_pages):
        params = {"limit": 1000}
        if before: params["before"] = before
        r = rpc("getSignaturesForAddress", [addr, params], ttl=None if before else 900)
        sigs += r
        if progress: progress(f"Scanning history of {addr[:6]}…: {len(sigs):,} txs")
        if len(r) < 1000: return list(reversed(sigs)), True
        before = r[-1]["signature"]
    return list(reversed(sigs)), False

def parse_buy(tx, mint, slot, t, sig, t0):
    signer = tx["transaction"]["message"]["accountKeys"][0]["pubkey"] if "message" in tx["transaction"] else tx["transaction"]["accountKeys"][0]["pubkey"]
    if tx["meta"].get("err"): return signer, None
    d, sol, _ = tx_deltas_any(tx, signer)
    q = d.get(mint, 0)
    if q > 0 and sol < 0:
        return signer, {"wallet": signer, "slot": slot, "t": t, "secs": (t - t0) if t0 else 0, "tokens": q, "sol": -sol, "sig": sig}
    return signer, None

def _keys(tx):
    return tx["transaction"]["message"]["accountKeys"] if "message" in tx["transaction"] else tx["transaction"]["accountKeys"]

def tx_deltas_any(tx, owner):
    return tx_deltas({"transaction": {"message": {"accountKeys": _keys(tx)}}, "meta": tx["meta"]}, owner)

def early_buys(mint, pair, log):
    """Collect the first N_EARLY unique buyers. Order of attempts:
    1) pump.fun bonding curve history (complete),
    2) main pool history if it is short enough to page to the start,
    3) otherwise read whole blocks forward from pool creation (getBlock), which is
       heavy but needs no index."""
    buys, seen, sigset = [], set(), set()
    info = {"dev": None, "launch_slot": None, "launch_ts": None, "sources": [], "scanned_txs": 0}
    def add_from_sigs(sigs, label):
        idx = 0
        with ThreadPoolExecutor(WORKERS) as ex:
            while len(seen) < N_EARLY and idx < len(sigs) and idx < MAX_CURVE_TXS:
                chunk = sigs[idx:idx + 24]; idx += 24
                txs = list(ex.map(lambda s: get_tx(s["signature"]), chunk))
                for s, tx in zip(chunk, txs):
                    if not tx: continue
                    if info["launch_slot"] is None:
                        info["launch_slot"], info["launch_ts"] = s["slot"], s["blockTime"]
                        info["dev"] = _keys(tx)[0]["pubkey"]
                    signer, b = parse_buy(tx, mint, s["slot"], s["blockTime"], s["signature"], info["launch_ts"])
                    if b and b["sig"] not in sigset: buys.append(b); sigset.add(b["sig"]); (b["sol"] >= MIN_BUY_SOL) and seen.add(signer)
                log(f"{label}: read {min(idx, len(sigs))} early txs, {len(seen)} unique buyers")
        info["scanned_txs"] += min(idx, len(sigs)); info["sources"].append(label)
        return idx >= len(sigs)
    bc = str(Pubkey.find_program_address([b"bonding-curve", bytes(Pubkey.from_string(mint))], PUMP)[0])
    log("Checking pump.fun bonding curve…")
    curve, complete = all_sigs(bc, 60, log)
    start_slot = None
    pool_slot = slot_at_time(pair["pairCreatedAt"] // 1000) if pair and pair.get("pairCreatedAt") and pair["dexId"] != "pumpfun" else None
    if curve:
        if not complete: raise RuntimeError(f"Bonding curve has over {len(curve):,} txs, too many to read with the free RPC.")
        ok = [s for s in curve if not s.get("err") and (pool_slot is None or s["slot"] <= pool_slot + 3)]
        if not add_from_sigs(ok, "pump.fun bonding curve") and len(seen) < N_EARLY:
            info["note"] = f"Read the first {MAX_CURVE_TXS} bonding-curve txs only (cap), so later curve buyers are not included."
            return buys, info
    if len(seen) >= N_EARLY or not pair or pair["dexId"] == "pumpfun":
        return buys, info
    pool = pair["pairAddress"]
    log("Checking main pool history size…")
    psigs, complete = all_sigs(pool, 12, log)
    if complete:
        add_from_sigs([s for s in psigs if not s.get("err")], f"{pair['dexId']} pool")
        return buys, info
    start_slot = max(pool_slot or 0, info["launch_slot"] or 0) or slot_at_time(pair["pairCreatedAt"] // 1000)
    label = f"{pair['dexId']} pool (block scan)"; info["sources"].append(label)
    slot = max(start_slot - 6, info["launch_slot"] or 0); scanned = 0; MAXB = int(os.environ.get("MAX_BLOCKS", 60))
    while len(seen) < N_EARLY and scanned < MAXB:
        blk = get_block(slot); slot += 1
        if not blk: continue
        scanned += 1
        for tx in blk.get("transactions", []):
            if not any(b["mint"] == mint for b in (tx["meta"].get("postTokenBalances") or [])): continue
            if info["launch_slot"] is None:
                info["launch_slot"], info["launch_ts"] = slot - 1, blk["blockTime"]; info["dev"] = _keys(tx)[0]["pubkey"]
            signer, b = parse_buy(tx, mint, slot - 1, blk["blockTime"], tx["transaction"]["signatures"][0], info["launch_ts"])
            info["scanned_txs"] += 1
            if b and b["sig"] not in sigset: buys.append(b); sigset.add(b["sig"]); (b["sol"] >= MIN_BUY_SOL) and seen.add(signer)
        log(f"{label}: {scanned} blocks read, {len(seen)} unique buyers")
    return buys, info

def get_block(slot):
    key = _ckey("blk", slot)
    hit = _cget(key, None)
    if hit is not None: return hit["r"]
    for i in range(6):
        RPC_LIM.wait()
        try:
            d = _sess.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": "getBlock", "params": [slot, {"encoding": "jsonParsed", "transactionDetails": "accounts", "rewards": False, "maxSupportedTransactionVersion": 1}]}, timeout=60).json()
            if "result" in d:
                r = d["result"]
                if r:  # keep only txs touching SPL token balances to save disk
                    r = {"blockTime": r["blockTime"], "transactions": [t for t in r["transactions"] if t["meta"].get("postTokenBalances")]}
                _cput(key, {"r": r}); return r
            if d.get("error", {}).get("code") in (-32007, -32009): _cput(key, {"r": None}); return None  # skipped slot
        except Exception: pass
        time.sleep(1 + i * 2)
    return None

def _bt(slot):
    for k in range(8):  # skip empty slots
        try:
            bt = rpc("getBlockTime", [slot + k])
            if bt: return slot + k, bt
        except Exception: pass
    return None, None

def slot_at_time(ts):
    """Find a slot whose block time is within ~1s of ts (secant search on block times)."""
    cur = rpc("getSlot", [], ttl=5)
    s1, t1 = _bt(cur - 200); s0 = cur - int((time.time() - ts) / 0.4)
    for _ in range(12):
        s0, t0 = _bt(s0)
        if s0 is None: break
        if abs(t0 - ts) <= 1: return s0
        rate = (s1 - s0) / (t1 - t0) if t1 != t0 else 2.5
        s1, t1 = s0, t0
        s0 = s0 + int((ts - t0) * rate)
    return s0

def build_positions(wallet, sample, workers=1):
    """Rebuild simple per-token positions from a wallet's txs (newest-first list of sigs).
    Only clean single-token swaps against SOL/wSOL are counted."""
    txs = {}
    if workers > 1:
        with ThreadPoolExecutor(workers) as ex:
            for s, tx in zip(sample, ex.map(lambda s: _safe_tx(s["signature"]), sample)): txs[s["signature"]] = tx
    pos = {}
    for s in reversed(sample):  # oldest first
        tx = txs.get(s["signature"]) if workers > 1 else _safe_tx(s["signature"])
        if not tx: continue
        d, sol, signer = tx_deltas(tx, wallet)
        d = {k: v for k, v in d.items() if k not in STABLES}
        if len(d) != 1: continue
        m, q = next(iter(d.items()))
        p = pos.setdefault(m, {"mint": m, "sol_in": 0, "sol_out": 0, "tok_in": 0, "tok_out": 0, "first_buy": None,
                               "first_buy_slot": None, "last_sell": None, "n_buys": 0, "n_sells": 0, "self_signed": 0})
        if q > 0 and sol < 0:
            p["sol_in"] += -sol; p["tok_in"] += q; p["n_buys"] += 1
            if p["first_buy"] is None: p["first_buy"], p["first_buy_slot"] = s["blockTime"], s["slot"]
            if signer == wallet: p["self_signed"] += 1
        elif q < 0 and sol > 0 and p["tok_in"] > 0:
            p["sol_out"] += sol; p["tok_out"] += -q; p["n_sells"] += 1; p["last_sell"] = s["blockTime"]
    return [p for p in pos.values() if p["sol_in"] >= MIN_BUY_SOL]

def _safe_tx(sig):
    try: return get_tx(sig)
    except Exception: return None

# ---------------- analysis ----------------
def short(a): return a[:4] + "…" + a[-4:]

def analyze(mint, log=lambda s: None, partial=lambda d: None):
    res = {"mint": mint, "started": int(time.time()), "notes": [], "wallets": [], "excluded": []}
    log("Looking up token on DexScreener…")
    pmap = ds_pairs([mint]); pair = pmap.get(mint)
    if pair:
        res["token"] = {"symbol": pair["baseToken"]["symbol"], "name": pair["baseToken"]["name"], "priceNative": float(pair.get("priceNative") or 0),
                        "priceUsd": float(pair.get("priceUsd") or 0), "mcap": pair.get("marketCap") or pair.get("fdv"), "pool": pair["pairAddress"],
                        "dex": pair["dexId"], "quote": pair["quoteToken"]["symbol"], "image": (pair.get("info") or {}).get("imageUrl"), "url": pair.get("url")}
    else:
        res["token"] = {"symbol": "?", "name": "unknown"}; res["notes"].append("DexScreener has no pair for this mint, so current price is unknown.")
    buys, info = early_buys(mint, pair, log)
    res.update(info); dev = info["dev"]; slot0 = info["launch_slot"]; t0 = info["launch_ts"]
    source = " + ".join(res["sources"]); res["source"] = source; res["curve_txs"] = res["scanned_txs"]
    slot_buyers = {}
    for b in buys: slot_buyers.setdefault(b["slot"], set()).add(b["wallet"])
    first = {}
    res["dust_buys"] = sum(1 for b in buys if b["sol"] < MIN_BUY_SOL)
    for b in buys:
        if b["sol"] < MIN_BUY_SOL: continue
        f = first.setdefault(b["wallet"], dict(b, n_buys=0)); f["n_buys"] += 1
        if b is not f and f["n_buys"] > 1: f["sol"] += b["sol"]; f["tokens"] += b["tokens"]
    early = sorted(first.values(), key=lambda x: (x["slot"], x["t"]))[:N_EARLY]
    for i, w in enumerate(early): w["rank"] = i + 1; w["entry"] = w["sol"] / w["tokens"] if w["tokens"] else None
    # 3) flags
    def flags(w):
        f = []
        if w["wallet"] == dev: f.append("dev (created the token)")
        if w["slot"] == slot0: f.append("sniper: same block as launch")
        elif w["secs"] <= 2: f.append(f"sniper: bought {w['secs']}s after launch")
        if len(slot_buyers.get(w["slot"], ())) >= 3 and w["secs"] <= 15: f.append(f"bundle?: {len(slot_buyers[w['slot']])} buyers in one block")
        return f
    log("Checking wallet activity levels…")
    with ThreadPoolExecutor(WORKERS) as ex:
        acts = list(ex.map(lambda w: rpc("getSignaturesForAddress", [w["wallet"], {"limit": 1000}], ttl=3600), early))
    keep = []
    for w, act in zip(early, acts):
        w["flags"] = flags(w); w["recent_sigs"] = len(act)
        if len(act) >= 1000 and act[0]["blockTime"] and act[-1]["blockTime"]:
            span_h = max((act[0]["blockTime"] - act[-1]["blockTime"]) / 3600, 0.01); w["tx_per_day"] = round(1000 / span_h * 24)
            if span_h < 6: w["flags"].append(f"bot: ~{w['tx_per_day']:,} txs/day")
        elif act and act[-1]["blockTime"]:
            span_h = max((time.time() - act[-1]["blockTime"]) / 3600, 0.01); w["tx_per_day"] = round(len(act) / span_h * 24, 1)
        hard = [f for f in w["flags"] if not f.startswith("bundle?")]
        (res["excluded"] if hard else keep).append(w)
        w["_act"] = [a for a in act if not a.get("err")]
    for w in res["excluded"]: w.pop("_act", None)
    res["n_early"] = len(early); partial(res)
    # 4) track record per kept wallet
    log(f"Building track records for {len(keep)} wallets…")
    def history(w):
        sample = w.pop("_act")[:WALLET_TXS]
        w["positions"] = build_positions(w["wallet"], sample)
        w["sampled_txs"] = len(sample)
        if sample: w["sample_from"] = sample[-1]["blockTime"]
        return w
    done = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for w in ex.map(history, keep):
            done += 1; log(f"Track records: {done}/{len(keep)} wallets")
            res["wallets"].append(w)
            if done % 5 == 0: partial(res)
    # 5) prices + peaks
    log("Pricing their tokens (DexScreener)…")
    allm = {p["mint"] for w in keep for p in w["positions"]} | {mint}
    prices = ds_pairs(list(allm))
    budget = [PEAK_BUDGET]; peak_cache = {}
    # target token peak first, then most-traded tokens
    freq = {}
    for w in keep:
        for p in w["positions"]: freq[p["mint"]] = freq.get(p["mint"], 0) + 1
    def peak_for(m, since):
        pr = prices.get(m)
        if not pr or pr["quoteToken"]["address"] != WSOL: return None
        key = (m, since // 86400)
        if key in peak_cache: return peak_cache[key]
        if budget[0] <= 0: return None
        budget[0] -= 1; log(f"Peak prices (GeckoTerminal, slow): {PEAK_BUDGET - budget[0]}/{PEAK_BUDGET}")
        v = gt_peak_native(pr["pairAddress"], since); peak_cache[key] = v; return v
    for w in keep:
        for p in w["positions"]:
            pr = prices.get(p["mint"])
            p["symbol"] = pr["baseToken"]["symbol"] if pr else None
            now = float(pr["priceNative"]) if pr and pr["quoteToken"]["address"] == WSOL and pr.get("priceNative") else None
            p["priced"] = now is not None or not pr
            rem = max(p["tok_in"] - p["tok_out"], 0)
            p["value_now"] = p["sol_out"] + rem * (now or 0)
            p["x_now"] = p["value_now"] / p["sol_in"] if p["priced"] else None
            p["entry"] = p["sol_in"] / p["tok_in"] if p["tok_in"] else None
            p["no_pair"] = not pr
    order = sorted({(p["mint"], p["first_buy"]) for w in keep for p in w["positions"] if p["first_buy"]}, key=lambda x: -freq.get(x[0], 0))
    tgt_peak = peak_for(mint, t0) if pair else None
    res["token"]["peak_native"] = tgt_peak
    for m, since in order:
        pk = peak_for(m, since)
        if pk is None: continue
        for w in keep:
            for p in w["positions"]:
                if p["mint"] == m and p["first_buy"] == since and p["entry"]:
                    p["x_peak"] = max(pk / p["entry"], p["x_now"] or 0)
    # 6) score
    cur = res["token"].get("priceNative")
    for w in keep:
        P = [p for p in w["positions"] if p["x_now"] is not None and p["mint"] != mint]
        w["n_tokens"] = len(P); w["wins"] = sum(1 for p in P if p["x_now"] >= 1)
        w["win_rate"] = w["wins"] / len(P) if P else None
        w["best_x"] = max([p["x_now"] for p in P], default=None)
        pk = [p.get("x_peak") for p in P if p.get("x_peak")]
        w["peak_checked"] = len(pk); w["n5"] = sum(1 for x in pk if x >= 5); w["n10"] = sum(1 for x in pk if x >= 10)
        w["best_peak"] = max(pk, default=None)
        w["pnl_sol"] = sum(p["value_now"] - p["sol_in"] for p in P)
        w["x_this"] = cur / w["entry"] if cur and w["entry"] else None
        w["x_this_peak"] = tgt_peak / w["entry"] if tgt_peak and w["entry"] else None
        n = len(P); wr = (w["wins"] + 1) / (n + 2)  # shrink toward 50% for tiny samples
        w["score"] = round(100 * (0.55 * wr + 0.25 * min(w["n5"], 4) / 4 + 0.2 * min(n, 8) / 8) * (1 if n >= 2 else 0.5), 1)
    res["wallets"].sort(key=lambda w: -w["score"])
    if info.get("note"): res["notes"].append(info["note"])
    res["finished"] = int(time.time()); res["peak_calls"] = PEAK_BUDGET - budget[0]
    res["notes"] += [
        f"Early buyers come from the first {res['scanned_txs']:,} txs read on: {source}. Data via {RPC_LABEL}.",
        f"Track record = other tokens bought in each wallet's last {WALLET_TXS} txs (free RPC). This token is left out, and older trades are not counted.",
        "Multiples are in SOL: (SOL received from sells + unsold tokens at today's price) / SOL spent. Fees, tips and rent are included in cost, so small buys look slightly worse.",
        "Peak 5x/10x = token's highest hourly price after their first buy vs their entry (GeckoTerminal). It shows the chance existed, not that they sold there.",
        f"Buys under {MIN_BUY_SOL} SOL are ignored as dust ({res.get('dust_buys', 0)} early dust buys skipped).",
        "Tokens with no DexScreener pair are counted as worth 0 (usually rugged or dead).",
    ]
    return res
