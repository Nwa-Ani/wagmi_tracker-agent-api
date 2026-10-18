"""EVM chains (Ethereum, Base, Robinhood Chain): memecoin + NFT scans and wallet checks.
Free sources: Etherscan v2 / Routescan (Ethereum), Blockscout (Base, when reachable), public JSON-RPC pools
(Base: thirdweb, Tenderly, publicnode, drpc; Robinhood Chain RPC), DexScreener (pairs/prices), GeckoTerminal (OHLCV),
OpenSea public stats (NFT floors, optional OPENSEA_API_KEY).
Optional keys: ETHERSCAN_API_KEY (Ethereum; Base only on a paid Etherscan plan), ALCHEMY_API_KEY (fast, full
Base/Ethereum wallet history via alchemy_getAssetTransfers on the free tier)."""
import os, time, json, threading, itertools, statistics as st
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import core, wallet_check

T_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
T_SINGLE = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
T_BATCH = "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb"
ZERO = "0x" + "0" * 40; ZT = "0x" + "0" * 64
ESKEY = os.environ.get("ETHERSCAN_API_KEY", "").strip()
OSKEY = os.environ.get("OPENSEA_API_KEY", "").strip()
ALKEY = os.environ.get("ALCHEMY_API_KEY", "").strip()

def _pool(env, *urls):
    v = os.environ.get(env, "").strip()
    return list(dict.fromkeys(([v] if v else []) + list(urls)))

CHAINS = {
    "eth": dict(name="Ethereum", ds="ethereum", gt="eth", os="ethereum", native="ETH", block_time=12, sniper_secs=13, chainid=1, alchemy="eth-mainnet",
                rpcs=_pool("ETH_RPC", "https://ethereum-rpc.publicnode.com"), span=None, addr_span=None,
                apis=([("Etherscan API", "https://api.etherscan.io/v2/api", {"chainid": 1, "apikey": ESKEY})] if ESKEY else [])
                     + [("Routescan API", "https://api.routescan.io/v2/network/mainnet/evm/1/etherscan/api", {})],
                explorer="https://etherscan.io", stables={"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xdac17f958d2ee523a2206206994597c13d831ec7", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "0x6b175474e89094c44da98b954eedeac495271d0f"}),
    # Base: Etherscan's free plan does not cover chain 8453 and Routescan doesn't index it, so the explorer API is
    # probed at runtime (paid Etherscan key, then keyless Blockscout); otherwise history comes from Alchemy (optional
    # key) or from a pool of public RPCs that serve eth_getLogs in 1,000-block windows.
    "base": dict(name="Base", ds="base", gt="base", os="base", native="ETH", block_time=2, sniper_secs=4, chainid=8453, alchemy="base-mainnet",
                 rpcs=_pool("BASE_RPC", "https://8453.rpc.thirdweb.com", "https://gateway.tenderly.co/public/base", "https://base.drpc.org", "https://base-rpc.publicnode.com"),
                 span=999, addr_span=999,
                 apis=([("Etherscan API", "https://api.etherscan.io/v2/api", {"chainid": 8453, "apikey": ESKEY})] if ESKEY else [])
                      + [("Blockscout API", "https://base.blockscout.com/api", {})],
                 explorer="https://basescan.org", stables={"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "0x4200000000000000000000000000000000000006", "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"}),
    "robinhood": dict(name="Robinhood Chain", ds="robinhood", gt="robinhood", os=None, native="ETH", block_time=0.1, sniper_secs=2, chainid=4663, alchemy=None,
                      rpcs=_pool("ROBINHOOD_RPC", "https://rpc.mainnet.chain.robinhood.com"), span=29999, addr_span=9_999_999, apis=[],
                      explorer="https://robinhoodchain.blockscout.com", stables=set()),
}
for _c in CHAINS.values(): _c["rpc"] = _c["rpcs"][0]
LIM = {k: core.Limiter(float(os.environ.get("EVM_RPS", 10)) * (2 if len(CHAINS[k]["rpcs"]) > 2 else 1)) for k in CHAINS}
API_LIM = core.Limiter(4)
pad = lambda a: "0x" + "0" * 24 + a.lower()[2:]
unpad = lambda t: "0x" + t[-40:]
_rr = {k: itertools.count() for k in CHAINS}
_LIMIT_WORDS = ("only", "not supported", "limited to", "too many", "exceed", "range", "too large", "maximum", "personal token", "specify an address")

from urllib.parse import urlparse
STATS = {}  # host -> {"ok": n, "limit": n, "err": n}; hostnames only, never full URLs (a custom RPC URL may hold a key)
def _stat(u, k):
    h = urlparse(u).hostname or "?"; d = STATS.setdefault(h, {"ok": 0, "limit": 0, "err": 0}); d[k] += 1
_ERRS = {}
_BAD = {}  # (chain, url, kind) -> time until which that provider is skipped for that kind of call

def _kind(method, params):
    if method != "eth_getLogs": return "call"
    return "logs_addr" if params and params[0].get("address") else "logs"

def rpc(ch, method, params, ttl=None):
    """JSON-RPC with a provider pool: round-robin for eth_getLogs, falling through to the next provider on
    limits / rate errors. Providers that refuse a kind of call are skipped for 10 minutes."""
    key = core._ckey("evm", ch, method, params); hit = core._cget(key, ttl)
    if hit is not None: return hit["r"]
    pool = CHAINS[ch]["rpcs"]; n = len(pool); kind = _kind(method, params); now = time.time()
    live = [u for u in pool if _BAD.get((ch, u, kind), 0) < now] or pool
    first = next(_rr[ch]) % len(live) if method == "eth_getLogs" else 0
    order = [live[(first + i) % len(live)] for i in range(len(live))]
    last = None; limited = set(); tries = 0
    while tries < max(8, 3 * len(order)):
        cand = [u for u in order if u not in limited]
        if not cand: break
        u = cand[tries % len(cand)]; tries += 1
        LIM[ch].wait()
        try:
            d = core._sess.post(u, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=45).json()
            if "result" in d:
                _stat(u, "ok"); _ERRS[urlparse(u).hostname] = 0; core._cput(key, {"r": d["result"]}); return d["result"]
            e = d.get("error") or {}; last = f"{e.get('message', '')} {e.get('data', '') if isinstance(e.get('data'), str) else ''}"
            if "revert" in last.lower() or "invalid opcode" in last.lower():
                core._cput(key, {"r": None}); return None
            _stat(u, "limit")
            if "historical state" in last or "missing trie" in last or "archive" in last.lower() or any(w in last.lower() for w in _LIMIT_WORDS):
                limited.add(u)
                if n > 1 and kind != "logs_addr": _BAD[(ch, u, kind)] = time.time() + 600
                continue
        except Exception as e:
            last = str(e); _stat(u, "err"); h = urlparse(u).hostname
            _ERRS[h] = _ERRS.get(h, 0) + 1
            if n > 1 and _ERRS[h] >= 5:  # provider keeps failing (blocked IP / HTML error pages): bench it for 10 min
                for kd in ("call", "logs", "logs_addr"): _BAD[(ch, u, kd)] = time.time() + 600
                _ERRS[h] = 0; limited.add(u)
        time.sleep(0.4 + 0.6 * (tries // max(1, len(cand))))
    if limited and len(limited) >= len(order):
        if "historical state" in str(last) or "missing trie" in str(last) or "archive" in str(last).lower(): raise LookupError(core.redact(last))
        raise ValueError(core.redact(last))
    raise RuntimeError(core.redact(f"{CHAINS[ch]['name']} RPC {method} failed: {last}"))

# ---------- Etherscan-compatible explorer APIs, probed once per hour ----------
_API_STATE = {}; _API_LOCK = threading.Lock()

def api_src(ch):
    """(label, base_url, extra_params) of the first explorer API that actually answers for this chain, or None."""
    C = CHAINS[ch]
    if not C["apis"]: return None
    st_ = _API_STATE.get(ch)
    if st_ and time.time() - st_[0] < 3600: return st_[1]
    with _API_LOCK:
        st_ = _API_STATE.get(ch)
        if st_ and time.time() - st_[0] < 3600: return st_[1]
        found = None; why = []
        for label, base, extra in C["apis"]:
            if len(C["apis"]) == 1 and ch == "eth": found = (label, base, extra); break
            try:
                r = core._sess.get(base, params={"module": "block", "action": "getblocknobytime", "timestamp": int(time.time()) - 3600, "closest": "before", **extra},
                                   headers={"accept": "application/json", "user-agent": "Mozilla/5.0 wagmi_tracker"}, timeout=20)
                d = r.json() if r.text.lstrip().startswith("{") else {}
                if str(d.get("status")) == "1" and d.get("result"): found = (label, base, extra); break
                why.append(f"{label}: {str(d.get('result') or d.get('message') or ('HTTP ' + str(r.status_code)))[:90]}")
            except Exception as e: why.append(f"{label}: {type(e).__name__}")
        _API_STATE[ch] = (time.time(), found, why)
        print(core.redact(f"[evm] {C['name']} explorer API: {found[0] if found else 'none'} ({'; '.join(why) or 'ok'})"), flush=True)
        return found

def api_reason(ch):
    s = _API_STATE.get(ch); return "; ".join(s[2]) if s else ""

def api(ch, params, ttl=None):
    """Explorer API call. Returns a list/dict/str result, [] for 'no records', or None when the API failed."""
    src = api_src(ch)
    if not src: return None
    _, base, extra = src
    key = core._ckey("evmapi", ch, base, params); hit = core._cget(key, ttl)
    if hit is not None: return hit["r"]
    for i in range(4):
        API_LIM.wait()
        try:
            d = core._sess.get(base, params={**params, **extra}, headers={"accept": "application/json"}, timeout=60).json()
            r = d.get("result")
            if isinstance(r, list) or (str(d.get("status")) == "1"):
                core._cput(key, {"r": r}); return r
            msg = str(d.get("message")) + " " + str(r)
            if "No records" in msg or "No transactions" in msg or "No logs" in msg or "No token" in msg:
                core._cput(key, {"r": []}); return []
            if "not supported" in msg or "Invalid API" in msg or "upgrade" in msg.lower():
                _API_STATE[ch] = (time.time(), None, [msg[:90]]); return None
        except Exception: pass
        time.sleep(1.5 + i * 2)
    return None

def has_api(ch): return api_src(ch) is not None

# ---------- Alchemy (optional free key): alchemy_getAssetTransfers ----------
_AL_STATE = {}

def alchemy_on(ch):
    """True when ALCHEMY_API_KEY is set and Alchemy actually answers for this chain (probed once per hour)."""
    if not (ALKEY and CHAINS[ch].get("alchemy")): return False
    st_ = _AL_STATE.get(ch)
    if st_ and time.time() - st_[0] < 3600: return st_[1]
    ok = False
    try:
        r = core._sess.post(f"https://{CHAINS[ch]['alchemy']}.g.alchemy.com/v2/{ALKEY}", json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}, timeout=20)
        ok = r.status_code == 200 and "result" in (r.json() if r.text.lstrip().startswith("{") else {})
    except Exception: ok = False
    _AL_STATE[ch] = (time.time(), ok)
    print(f"[evm] {CHAINS[ch]['name']} Alchemy: {'ok' if ok else 'key rejected or unreachable, using fallbacks'}", flush=True)
    return ok
AL_LIM = core.Limiter(float(os.environ.get("ALCHEMY_RPS", 8)))

def alchemy_transfers(ch, w, cats, days, direction=("from", "to"), from_zero=False, max_pages=3):
    """Transfers for wallet `w` in the last `days`. direction picks fromAddress/toAddress queries. None on failure."""
    C = CHAINS[ch]; url = f"https://{C['alchemy']}.g.alchemy.com/v2/{ALKEY}"
    try: fb = hex(max(0, latest(ch) - int(days * 86400 / C["block_time"])))
    except Exception: fb = "0x0"
    out = []; ok = False
    for d in direction:
        q = {"fromBlock": fb, "toBlock": "latest", "category": list(cats), "withMetadata": True, "excludeZeroValue": False, "maxCount": "0x3e8", "order": "desc"}
        if d == "from": q["fromAddress"] = w
        else:
            q["toAddress"] = w
            if from_zero: q["fromAddress"] = ZERO
        page = None
        for _ in range(max_pages):
            if page: q["pageKey"] = page
            key = core._ckey("alchemy", ch, q); hit = core._cget(key, 900)
            if hit is not None: res = hit["r"]
            else:
                res = None
                for i in range(4):
                    AL_LIM.wait()
                    try:
                        r = core._sess.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "alchemy_getAssetTransfers", "params": [q]}, timeout=45)
                        j = r.json()
                        if "result" in j: res = j["result"]; core._cput(key, {"r": res}); break
                        if r.status_code in (401, 403) or "key" in str(j.get("error", "")).lower():
                            _AL_STATE[ch] = (time.time(), False); print("[evm] Alchemy rejected the key (check ALCHEMY_API_KEY)", flush=True); return None
                    except Exception: pass
                    time.sleep(1 + i * 2)
            if res is None: break
            ok = True; out += res.get("transfers") or []; page = res.get("pageKey")
            if not page: break
    if not ok: return None
    return out

def _al_ts(x):
    try: return int(datetime.fromisoformat(x["metadata"]["blockTimestamp"].replace("Z", "+00:00")).timestamp())
    except Exception: return None

def _al_amt(x):
    rc = x.get("rawContract") or {}
    try:
        dec = int(rc.get("decimal") or "0x12", 16) if str(rc.get("decimal") or "").startswith("0x") else int(rc.get("decimal") or 18)
        return int(rc.get("value") or "0x0", 16) / 10 ** dec
    except Exception: return float(x.get("value") or 0)

def src_label(ch):
    if alchemy_on(ch): return "Alchemy transfers API"
    s = api_src(ch)
    return s[0] if s else f"public {CHAINS[ch]['name']} RPC logs"

def latest(ch): return int(rpc(ch, "eth_blockNumber", [], ttl=10), 16)

def block_ts(ch, n):
    b = rpc(ch, "eth_getBlockByNumber", [hex(n), False]); return int(b["timestamp"], 16) if b else None

def block_at_time(ch, ts):
    if has_api(ch):
        r = api(ch, {"module": "block", "action": "getblocknobytime", "timestamp": int(ts), "closest": "before"})
        try: return int(r if not isinstance(r, dict) else r.get("blockNumber"))
        except Exception: pass
    hi = latest(ch); hts = block_ts(ch, hi); lo = max(0, hi - int((hts - ts) / CHAINS[ch]["block_time"] * 1.3) - 1000)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        t = block_ts(ch, mid)
        if t is None or t > ts: hi = mid
        else: lo = mid
    return lo

def is_contract(ch, a):
    try: return rpc(ch, "eth_getCode", [a, "latest"], ttl=86400 * 7) not in ("0x", "0x0", None)
    except Exception: return False

def _norm(l, ts=None):
    return {"address": l["address"].lower(), "topics": [t.lower() for t in l["topics"] if t], "data": l.get("data", "0x"),
            "block": int(l["blockNumber"], 16) if isinstance(l["blockNumber"], str) and l["blockNumber"].startswith("0x") else int(l["blockNumber"]),
            "hash": l["transactionHash"].lower(), "ts": int(l["timeStamp"], 16) if isinstance(l.get("timeStamp"), str) and l["timeStamp"].startswith("0x") else (int(l["timeStamp"]) if l.get("timeStamp") else ts),
            "li": _hx(l.get("logIndex"))}

def _hx(v):
    v = str(v or "0")
    try: return int(v, 16) if v.startswith("0x") else int(v)
    except ValueError: return 0

def logs_forward(ch, address, topics, start, stop=None, want=1000, span=None, log=None):
    """Logs ascending from `start` until `want` collected or `stop` reached. Window size adapts to RPC limits."""
    C = CHAINS[ch]; out = []
    if address and has_api(ch):
        page = 1; seen = set(); failed = False
        while len(out) < want and page <= 10:
            p = {"module": "logs", "action": "getLogs", "address": address, "fromBlock": start, "toBlock": stop or "latest", "page": page, "offset": 1000}
            for i, t in enumerate(topics):
                if t is None: continue
                p[f"topic{i}"] = t
                if i: p[f"topic0_{i}_opr"] = "and"
            r = api(ch, p)
            if r is None: failed = True; break
            new = [x for x in r if (x.get("transactionHash"), x.get("logIndex")) not in seen]
            seen |= {(x.get("transactionHash"), x.get("logIndex")) for x in r}
            out += [_norm(x) for x in new]
            if len(r) < 1000 or not new: break
            page += 1
        if out or not failed: return out[:want] if want else out
        out = []  # explorer failed: fall back to RPC
    stop = stop or latest(ch); span = span or (C["addr_span"] if address else C["span"]); cur = start
    t0 = block_ts(ch, start); bt = C["block_time"]
    while cur <= stop and len(out) < want:
        end = min(cur + span, stop)
        f = {"fromBlock": hex(cur), "toBlock": hex(end), "topics": topics}
        if address: f["address"] = address
        try:
            r = rpc(ch, "eth_getLogs", [f], ttl=None if end < stop - 50 else 60)
        except ValueError:
            if span <= 50: raise
            span = max(span // 4, 50); continue
        for x in r or []: out.append(_norm(x, (t0 + int((int(x["blockNumber"], 16) - start) * bt)) if t0 else None))
        if log: log(f"Reading {C['name']} logs… block {end:,}")
        cur = end + 1
    out.sort(key=lambda x: (x["block"], x["li"]))
    return out

def logs_recent(ch, topics_list, days, log=None, workers=None):
    """Topic-filtered logs (no address) over the last `days`, windowed in parallel across the RPC pool.
    Returns (logs, windows_ok, windows_total) via .stats on the list."""
    C = CHAINS[ch]; top = latest(ch); n = int(days * 86400 / C["block_time"]); start = max(0, top - n)
    workers = workers or min(16, 6 * len(C["rpcs"]))
    ttop = block_ts(ch, top); windows = [(s, min(s + C["span"], top)) for s in range(start, top + 1, C["span"] + 1)]
    def one(args):
        (s, e), topics = args
        try: r = rpc(ch, "eth_getLogs", [{"fromBlock": hex(s), "toBlock": hex(e), "topics": topics}], ttl=None if e < top - 50 else 120)
        except Exception: return None
        return [_norm(x, int(ttop - (top - int(x["blockNumber"], 16)) * C["block_time"])) for x in r or []]
    jobs = [(w, t) for t in topics_list for w in windows]; out = LogList(); done = ok = 0
    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(one, jobs):
            done += 1
            if r is not None: out += r; ok += 1
            if log and done % 40 == 0: log(f"Reading {C['name']} history… {done}/{len(jobs)} windows")
    out.sort(key=lambda x: (x["block"], x["li"])); out.ok, out.total = ok, len(jobs); return out

class LogList(list):
    ok = total = 0

def token_meta(ch, token):
    key = core._ckey("meta", ch, token); hit = core._cget(key, None)
    if hit: return hit["r"]
    def call(sel):
        try: return rpc(ch, "eth_call", [{"to": token, "data": sel}, "latest"], ttl=86400 * 30)
        except Exception: return None
    dec = call("0x313ce567"); sym = call("0x95d89b41")
    def s(h):
        try:
            b = bytes.fromhex(h[2:]); 
            if len(b) >= 64: n = int.from_bytes(b[32:64], "big"); return b[64:64 + n].decode(errors="ignore")
            return b.rstrip(b"\0").decode(errors="ignore")
        except Exception: return None
    m = {"decimals": int(dec, 16) if dec and dec != "0x" else 18, "symbol": s(sym) if sym else None}
    core._cput(key, {"r": m}); return m

def tx(ch, h):
    try:
        r = rpc(ch, "eth_getTransactionByHash", [h])
        if r: return r
    except Exception: pass
    if has_api(ch):
        r = api(ch, {"module": "proxy", "action": "eth_getTransactionByHash", "txhash": h})
        if isinstance(r, dict): return r
    return None

def ohlcv(ch, pool, tf="hour", before=None, currency="usd"):
    u = f"https://api.geckoterminal.com/api/v2/networks/{CHAINS[ch]['gt']}/pools/{pool}/ohlcv/{tf}?aggregate=1&limit=1000&currency={currency}&token=base" + (f"&before_timestamp={int(before)}" if before else "")
    d = core.http_json(u, core.GT_LIM, ttl=1800)
    try: return sorted(d["data"]["attributes"]["ohlcv_list"])
    except Exception: return []

def price_at(rows, ts):
    best = None
    for r in rows:
        if r[0] <= ts: best = r
        else: break
    return best[4] if best else (rows[0][1] if rows and rows[0][0] - ts < 3600 else None)

def ds_pairs(ch, tokens):
    out = {}; tokens = list(dict.fromkeys(t.lower() for t in tokens))
    for i in range(0, len(tokens), 30):
        d = core.http_json(f"https://api.dexscreener.com/tokens/v1/{CHAINS[ch]['ds']}/" + ",".join(tokens[i:i + 30]), core.DS_LIM, ttl=600) or []
        for p in d:
            m = p["baseToken"]["address"].lower()
            sc = (p.get("liquidity") or {}).get("usd") or 0
            if m in tokens and (m not in out or sc > ((out[m].get("liquidity") or {}).get("usd") or 0)): out[m] = p
    return out

def _amount(l, dec): 
    try: return int(l["data"][:66], 16) / 10 ** dec
    except Exception: return 0.0

# ===================== memecoins =====================
def scan_token(ch, token, log=lambda s: None, partial=lambda d: None, n_early=40):
    C = CHAINS[ch]; token = token.lower()
    res = {"kind": "token", "chain": ch, "asset": "coin", "unit": "USD", "mint": token, "notes": [], "wallets": [], "excluded": [], "started": int(time.time())}
    log("Looking up the coin on DexScreener…")
    pair = ds_pairs(ch, [token]).get(token)
    if not pair: raise RuntimeError(f"No DEX pair found for this token on {C['name']}.")
    meta = token_meta(ch, token)
    res["token"] = {"symbol": pair["baseToken"]["symbol"], "name": pair["baseToken"]["name"], "priceUsd": float(pair.get("priceUsd") or 0),
                    "mcap": pair.get("marketCap") or pair.get("fdv"), "pool": pair["pairAddress"], "dex": pair["dexId"] + (" " + "/".join(pair.get("labels") or []) if pair.get("labels") else ""),
                    "image": (pair.get("info") or {}).get("imageUrl"), "url": pair.get("url")}
    t_pool = pair.get("pairCreatedAt", 0) // 1000
    log("Finding the pool's first block…")
    b0 = block_at_time(ch, t_pool - 30) if t_pool else 0
    log("Reading the first transfers…")
    L = logs_forward(ch, token, [T_TRANSFER], b0, want=1500, log=log)
    L = [l for l in L if len(l["topics"]) == 3]
    # liquidity sources = contracts that send this token to several different addresses
    senders = {}
    for l in L[:1500]:
        f = unpad(l["topics"][1])
        if f != ZERO and f != token: senders.setdefault(f, set()).add(unpad(l["topics"][2]))
    amm = {a for a, r in senders.items() if len(r) >= 3 and is_contract(ch, a)}
    if len(pair["pairAddress"]) == 42: amm.add(pair["pairAddress"].lower())
    buys = []
    for l in L:
        f, t = unpad(l["topics"][1]), unpad(l["topics"][2])
        if f in amm and t not in amm and t != ZERO: buys.append({"wallet": t, "block": l["block"], "t": l["ts"], "tokens": _amount(l, meta["decimals"]), "hash": l["hash"]})
    if not buys: raise RuntimeError("Could not find early swaps for this token with free data.")
    first_block = buys[0]["block"]; t_first = buys[0]["t"] or t_pool
    res["launch_ts"] = t_first; res["source"] = f"first {len(L):,} Transfer logs after pool creation ({src_label(ch) if has_api(ch) else 'public RPC'})"
    log("Pricing entries (GeckoTerminal)…")
    pool = pair["pairAddress"]
    mins = ohlcv(ch, pool, "minute", before=(t_first or t_pool) + 60 * 990)
    hours = ohlcv(ch, pool, "hour"); peak_after = lambda ts: max([r[2] for r in hours if r[0] + 3600 > ts], default=None)
    per_block = {}
    for b in buys: per_block.setdefault(b["block"], set()).add(b["wallet"])
    first = {}
    for b in buys:
        if b["wallet"] in first: continue
        first[b["wallet"]] = b
        if len(first) >= n_early: break
    early = sorted(first.values(), key=lambda x: x["block"])
    cur = res["token"]["priceUsd"]
    for i, w in enumerate(early):
        w["rank"] = i + 1; w["secs"] = int((w["t"] or 0) - (t_first or 0)); w["flags"] = []
        p = price_at(mins, w["t"]) if w["t"] else None
        w["entry"] = p; w["sol"] = (p or 0) * w["tokens"]   # 'sol' field = cost in USD for EVM (unit USD)
        w["x_this"] = cur / p if p and cur else None
        pk = peak_after(w["t"]) if w["t"] else None; w["x_this_peak"] = max(pk / p, w["x_this"] or 0) if pk and p else None
        if w["block"] == first_block: w["flags"].append("sniper: first swap block")
        elif w["secs"] <= C["sniper_secs"]: w["flags"].append(f"sniper: {w['secs']}s after first swap")
        if len(per_block[w["block"]]) >= 3 and w["secs"] <= 60: w["flags"].append(f"bundle?: {len(per_block[w['block']])} buyers in one block")
    log("Checking wallets (contracts / bots)…")
    with ThreadPoolExecutor(8) as ex: cflags = list(ex.map(lambda w: is_contract(ch, w["wallet"]), early))
    keep = []
    for w, c in zip(early, cflags):
        if c: w["flags"].append("contract (router, MEV or bot)")
        hard = [f for f in w["flags"] if not f.startswith("bundle?")]
        (res["excluded"] if hard else keep).append(w)
    res["n_early"] = len(early); partial(res)
    log(f"Track records for {len(keep)} wallets…")
    hist = {}
    def h(w):
        if ch == "robinhood" and keep.index(w) >= 12: return w["wallet"], ([], 0, {})
        if ch == "base" and not fast_hist(ch) and keep.index(w) >= 12: return w["wallet"], ([], 0, {})
        try: return w["wallet"], wallet_positions(ch, w["wallet"], days=hist_days(ch, "scan"), log=None)
        except Exception: return w["wallet"], ([], 0, {})
    with ThreadPoolExecutor(2 if ch == "base" and not fast_hist(ch) else 3) as ex:
        for i, (a, r) in enumerate(ex.map(h, keep)):
            hist[a] = r; log(f"Track records: {i+1}/{len(keep)} wallets")
    allpos = [p for a, (P, _, _) in hist.items() for p in P if p["token"] != token]
    price_positions(ch, allpos, budget=int(os.environ.get("EVM_PEAK_BUDGET", 25)), log=log)
    for w in keep:
        P, n, _ = hist[w["wallet"]]; P = [p for p in P if p["token"] != token]
        w["positions"] = P; w["sampled_txs"] = n
        Q = [p for p in P if p.get("x_now") is not None]
        w["n_tokens"] = len(Q); w["wins"] = sum(1 for p in Q if p["x_now"] >= 1); w["win_rate"] = w["wins"] / len(Q) if Q else None
        w["best_x"] = max([p["x_now"] for p in Q], default=None)
        pk = [p["x_peak"] for p in Q if p.get("x_peak")]; w["peak_checked"] = len(pk); w["n5"] = sum(x >= 5 for x in pk); w["n10"] = sum(x >= 10 for x in pk)
        wr = (w["wins"] + 1) / (len(Q) + 2)
        w["score"] = round(100 * (0.55 * wr + 0.25 * min(w["n5"], 4) / 4 + 0.2 * min(len(Q), 8) / 8) * (1 if len(Q) >= 2 else 0.5), 1)
        res["wallets"].append(w)
    res["wallets"].sort(key=lambda w: -w["score"]); res["finished"] = int(time.time())
    if keep and not any(w.get("sampled_txs") for w in keep):
        res["notes"].append(f"No recent history came back for these wallets. Either they're inactive lately or the free {C['name']} RPC refused history queries"
                            + (" (add a free ALCHEMY_API_KEY for reliable Base history)." if ch == "base" else " (set ETHERSCAN_API_KEY for reliable history)." if ch == "eth" else "."))
    res["notes"] += [f"Early buyers = first addresses that received {res['token']['symbol']} from the pool/router contracts ({res['source']}).",
                     "Entry price comes from GeckoTerminal 1-minute candles, so cost (USD) and multiples are estimates.",
                     f"Track record = other tokens moved in each wallet's last {'1 day (top 12 wallets only, RPC limits)' if ch == 'robinhood' else str(hist_days(ch, 'scan')) + ' day(s)'} ({src_label(ch)}{', top 12 wallets only because of public RPC limits' if ch == 'base' and not fast_hist(ch) else ''}), priced with hourly candles for the most common tokens only.",
                     "Contracts (routers, MEV bots, smart wallets) and first-block snipers are removed. Funding links between wallets are not traced.",
                     "Numbers are estimates. Not financial advice."]
    return res

def fast_hist(ch): return alchemy_on(ch) or has_api(ch)

def hist_days(ch, kind):
    """History window per source: explorer/Alchemy are cheap, public RPC logs cost one call per 1,000 blocks."""
    fast = fast_hist(ch)
    return {"check": 30 if fast else (2 if ch == "robinhood" else 3 if ch == "base" else 10),
            "scan": 1 if ch == "robinhood" else (7 if fast else 1 if ch == "base" else 5),
            "nftcheck": 2 if ch == "robinhood" else (90 if fast else 3 if ch == "base" else 14),
            "nftscan": 2 if ch == "robinhood" else (30 if fast else 1 if ch == "base" else 4)}[kind]

def wallet_positions(ch, w, days=7, log=None, max_items=1500):
    """Per-token ERC-20 positions (token amounts + times) from the wallet's recent transfers.
    Source chain: Alchemy (if key) -> explorer API (if it answers) -> public RPC logs."""
    C = CHAINS[ch]; w = w.lower(); items = []; got = False; since = time.time() - days * 86400
    if alchemy_on(ch):
        r = alchemy_transfers(ch, w, ["erc20"], days)
        if r is not None:
            got = True
            for x in r:
                tk = ((x.get("rawContract") or {}).get("address") or "").lower(); ts = _al_ts(x)
                if not tk or (ts and ts < since): continue
                items.append({"token": tk, "from": (x.get("from") or "").lower(), "to": (x.get("to") or "").lower(), "ts": ts, "block": int(x["blockNum"], 16),
                              "hash": x["hash"].lower(), "amt": _al_amt(x), "symbol": x.get("asset")})
    if not got and has_api(ch):
        r = api(ch, {"module": "account", "action": "tokentx", "address": w, "page": 1, "offset": 1000, "sort": "desc"}, ttl=1800)
        if r is not None:
            got = True
            for x in r:
                if int(x["timeStamp"]) < since: continue
                items.append({"token": x["contractAddress"].lower(), "from": x["from"].lower(), "to": x["to"].lower(), "ts": int(x["timeStamp"]), "block": int(x["blockNumber"]),
                              "hash": x["hash"].lower(), "amt": int(x["value"]) / 10 ** int(x.get("tokenDecimal") or 18), "symbol": x.get("tokenSymbol")})
    if not got:
        L = logs_recent(ch, [[T_TRANSFER, None, pad(w)], [T_TRANSFER, pad(w)]], days, log=log)
        _LAST_RPC_COVERAGE[(ch, w)] = (L.ok, L.total)
        metas = {}
        for l in L:
            if len(l["topics"]) != 3: continue
            tk = l["address"]
            if tk not in metas: metas[tk] = token_meta(ch, tk)
            items.append({"token": tk, "from": unpad(l["topics"][1]), "to": unpad(l["topics"][2]), "ts": l["ts"], "block": l["block"], "hash": l["hash"],
                          "amt": _amount(l, metas[tk]["decimals"]), "symbol": metas[tk]["symbol"]})
    items.sort(key=lambda x: (x["block"], x["ts"] or 0)); items = items[-max_items:]
    pos = {}; txs = set()
    for x in items:
        if x["token"] in C["stables"]: continue
        txs.add(x["hash"])
        p = pos.setdefault(x["token"], {"token": x["token"], "mint": x["token"], "symbol": x["symbol"], "buys": [], "sells": [], "tok_in": 0, "tok_out": 0})
        if x["to"] == w and x["from"] != ZERO: p["buys"].append((x["ts"], x["amt"], x["hash"])); p["tok_in"] += x["amt"]
        elif x["from"] == w and p["tok_in"] > 0: p["sells"].append((x["ts"], x["amt"], x["hash"])); p["tok_out"] += x["amt"]
    P = [p for p in pos.values() if p["buys"]]
    for p in P:
        p["first_buy"] = p["buys"][0][0]; p["last_sell"] = p["sells"][-1][0] if p["sells"] else None
        p["n_buys"] = len(p["buys"]); p["n_sells"] = len(p["sells"])
    return P, len(txs), {}

_LAST_RPC_COVERAGE = {}

def empty_note(ch, w, days, what="ERC-20 token transfers"):
    """Plain explanation when a wallet comes back empty, naming the source and why it may be empty."""
    C = CHAINS[ch]; ok, total = _LAST_RPC_COVERAGE.get((ch, w.lower()), (None, None))
    msg = f"No {what} found for this wallet on {C['name']} in the last {days} days ({src_label(ch)})."
    if ok is not None and total and ok < total:
        msg += f" Only {ok}/{total} RPC windows answered, so the public RPCs were rate limiting; try again in a few minutes."
    elif ok is not None:
        msg += " Either the wallet was quiet in that window or it trades on another chain."
    if ch == "base" and not alchemy_on(ch):
        msg += " For full Base history (30 days of trades, 90 days of mints), add a free ALCHEMY_API_KEY in Render (Etherscan's free plan doesn't cover Base)."
    return msg

def price_positions(ch, P, budget=20, log=None):
    """USD valuation from hourly candles: cost at buy time, proceeds at sell time, rest at today's price."""
    pairs = ds_pairs(ch, [p["token"] for p in P]); freq = {}
    for p in P: freq[p["token"]] = freq.get(p["token"], 0) + 1
    order = sorted(freq, key=lambda t: -freq[t]); rows = {}
    for t in order:
        if budget <= 0: break
        pr = pairs.get(t)
        if not pr: continue
        budget -= 1
        if log: log(f"Price history (GeckoTerminal, slow): {len(rows)+1} tokens")
        rows[t] = ohlcv(ch, pr["pairAddress"], "hour")
    for p in P:
        pr = pairs.get(p["token"]); R = rows.get(p["token"])
        p["symbol"] = (pr["baseToken"]["symbol"] if pr else None) or p.get("symbol"); p["no_pair"] = not pr
        p["pair_created"] = (pr.get("pairCreatedAt") or 0) // 1000 if pr else None
        if not R:
            p["x_now"] = None; p["priced"] = False
            p["sol_in"] = p["sol_out"] = p["value_left"] = 0.0; continue
        now = float(pr.get("priceUsd") or 0)
        cost = sum(a * (price_at(R, t) or 0) for t, a, _ in p["buys"]); got = sum(a * (price_at(R, t) or 0) for t, a, _ in p["sells"])
        left = max(p["tok_in"] - p["tok_out"], 0); p["value_left"] = left * now
        p["sol_in"], p["sol_out"] = cost, got; p["priced"] = cost > 0
        p["x_now"] = (got + p["value_left"]) / cost if cost > 0 else None
        p["realized_x"] = got / cost if cost > 0 and p["sells"] else None
        p["entry"] = cost / p["tok_in"] if p["tok_in"] else None
        pk = max([r[2] for r in R if r[0] + 3600 > p["first_buy"]], default=None)
        p["x_peak"] = max(pk / p["entry"], p["x_now"] or 0) if pk and p["entry"] else None
        p["holding"] = left > 0.02 * p["tok_in"] and p["value_left"] > 1
    for p in P:
        p.setdefault("realized_x", None); p.setdefault("holding", max(p["tok_in"] - p["tok_out"], 0) > 0.02 * p["tok_in"])
        p["hold_secs"] = (p["last_sell"] - p["first_buy"]) if p.get("last_sell") and p.get("first_buy") else None

def check_wallet(ch, w, log=lambda s: None, partial=lambda d: None):
    C = CHAINS[ch]; w = w.lower()
    res = {"kind": "wallet", "chain": ch, "asset": "coin", "unit": "USD", "wallet": w, "notes": [], "started": int(time.time())}
    log("Reading wallet transfers…")
    contract = is_contract(ch, w)
    days = hist_days(ch, "check")
    log(f"Reading wallet transfers ({src_label(ch)}, {days} days)…")
    P, ntx, _ = wallet_positions(ch, w, days=days, log=log)
    nonce = None
    try: nonce = int(rpc(ch, "eth_getTransactionCount", [w, "latest"], ttl=600), 16)
    except Exception: pass
    span_d = max(((max(p["buys"][-1][0] for p in P) - min(p["first_buy"] for p in P)) / 86400) if P else days, 0.5)
    res["activity"] = {"tx_per_day": round(ntx / span_d, 1), "failed_share": 0.0, "basis": "token transfers", "nonce": nonce, "contract": contract}
    res["sampled_txs"] = ntx
    P.sort(key=lambda p: -(p["first_buy"] or 0)); P = P[:40]
    log("Pricing trades (GeckoTerminal, slow)…")
    price_positions(ch, P, budget=int(os.environ.get("EVM_CHECK_BUDGET", 20)), log=log)
    log("Checking who sent the buys…")
    def own(p):
        h = p["buys"][0][2]; t = tx(ch, h); return t and t.get("from", "").lower() == w
    with ThreadPoolExecutor(6) as ex: owns = list(ex.map(own, P[:30]))
    for p, o in zip(P, owns + [None] * (len(P) - len(owns))):
        p["self_signed"] = p["n_buys"] if o else 0; p["self_initiated"] = bool(o) if o is not None else True
        p["delay"] = (p["first_buy"] - p["pair_created"]) if p.get("pair_created") and p["first_buy"] and p["first_buy"] >= p["pair_created"] else None
        p["delay_ref"] = "pool"; p["sniped"] = p["delay"] is not None and p["delay"] <= C["sniper_secs"]
        p["sol_in"] = p.get("sol_in", 0.0); p["sol_out"] = p.get("sol_out", 0.0); p["value_left"] = p.get("value_left", 0.0)
        for k in ("buys", "sells"): p.pop(k, None)
    res["positions"] = P
    if not P: res["notes"].append(empty_note(ch, w, days))
    res.update(wallet_check.summarize(res, P))
    if contract:
        res["verdict"] = "Skip" if res["verdict"].startswith("Good for copy") else res["verdict"]
        res["reasons"].append("This address is a contract (smart wallet or bot), so a copy bot can't follow it cleanly.")
    res["finished"] = int(time.time())
    res["notes"] += [f"Based on ERC-20 transfers in the last {days} days ({src_label(ch)}).",
                     "Values are in USD from GeckoTerminal hourly candles (cost at buy time, proceeds at sell time, the rest at today's price). Gas is not included.",
                     "Only the most-traded tokens get price history (free rate limits). Unpriced tokens are left out of the win rate.",
                     "Entry timing is measured from pool creation on DexScreener.", "Numbers are estimates. Not financial advice."]
    return res

# ===================== NFTs =====================
def first_mint_block(ch, contract):
    C = CHAINS[ch]
    if has_api(ch):
        r = api(ch, {"module": "logs", "action": "getLogs", "address": contract, "topic0": T_TRANSFER, "topic1": ZT, "topic0_1_opr": "and", "fromBlock": 0, "toBlock": "latest", "page": 1, "offset": 1})
        if r: return int(r[0]["blockNumber"], 16) if str(r[0]["blockNumber"]).startswith("0x") else int(r[0]["blockNumber"])
    top = latest(ch)
    try:  # creation block via archive getCode binary search (works on Base drpc)
        lo, hi = 0, top
        if rpc(ch, "eth_getCode", [contract, hex(hi)]) in ("0x", None): return None
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if rpc(ch, "eth_getCode", [contract, hex(mid)]) in ("0x", None): lo = mid
            else: hi = mid
        return hi
    except LookupError: pass
    span = C["addr_span"]; s = 0
    while s <= top:  # address-filtered wide windows (Robinhood RPC allows 10M blocks)
        r = rpc(ch, "eth_getLogs", [{"fromBlock": hex(s), "toBlock": hex(min(s + span, top)), "address": contract, "topics": [T_TRANSFER, ZT]}])
        if r: return int(r[0]["blockNumber"], 16)
        s += span + 1
    return None

def os_floor(ch, contract):
    C = CHAINS[ch]
    if not C["os"]: return None, "no OpenSea data for this chain"
    h = {"accept": "application/json", **({"x-api-key": OSKEY} if OSKEY else {})}
    def g(u):
        key = core._ckey("os", u); hit = core._cget(key, 3600)
        if hit is not None: return hit["r"]
        try:
            r = core._sess.get(u, headers=h, timeout=30); d = r.json() if r.status_code == 200 else None
        except Exception: d = None
        core._cput(key, {"r": d}); return d
    c = g(f"https://api.opensea.io/api/v2/chain/{C['os']}/contract/{contract}")
    if not c or not c.get("collection"): return None, "OpenSea lookup unavailable" + ("" if OSKEY else " (set OPENSEA_API_KEY)")
    s = g(f"https://api.opensea.io/api/v2/collections/{c['collection']}/stats")
    try: return {"floor": float(s["total"]["floor_price"]), "symbol": s["total"].get("floor_price_symbol", "ETH"), "slug": c["collection"], "name": c.get("name")}, None
    except Exception: return None, "no floor on OpenSea"

def soulbound(ch, contract, token_id, transfers_seen):
    try:
        r = rpc(ch, "eth_call", [{"to": contract, "data": "0xb45a3c0e" + format(token_id, "064x")}, "latest"], ttl=86400)
        if r and r != "0x" and int(r, 16) == 1: return True
    except Exception: pass
    return None if transfers_seen else None

def scan_collection(ch, contract, log=lambda s: None, partial=lambda d: None, n_early=50):
    C = CHAINS[ch]; contract = contract.lower()
    res = {"kind": "token", "chain": ch, "asset": "nft", "unit": C["native"], "mint": contract, "notes": [], "wallets": [], "excluded": [], "started": int(time.time())}
    log("Finding the collection's first mint…")
    b0 = first_mint_block(ch, contract)
    if b0 is None: raise RuntimeError(f"No NFT mints found for this contract on {C['name']}.")
    log("Reading the first mints…")
    L = logs_forward(ch, contract, [T_TRANSFER, ZT], b0, want=600, log=log)
    L = [l for l in L if len(l["topics"]) == 4]
    if not L:
        L = [dict(l, topics=[T_SINGLE, l["topics"][1], ZT, l["topics"][3]]) for l in logs_forward(ch, contract, [T_SINGLE, None, ZT], b0, want=600, log=log)]
    if not L: raise RuntimeError("This contract has no ERC-721/1155 mints in range.")
    meta = token_meta(ch, contract)
    fl, why = os_floor(ch, contract)
    res["token"] = {"symbol": meta.get("symbol") or "NFT", "name": (fl or {}).get("name") or meta.get("symbol") or contract, "floor": (fl or {}).get("floor"), "floor_note": why}
    t0 = L[0]["ts"] or block_ts(ch, L[0]["block"]); res["launch_ts"] = t0
    by = {}
    for l in L:
        m = unpad(l["topics"][3] if l["topics"][0] == T_SINGLE else l["topics"][2]); by.setdefault(m, []).append(l)
    per_block = {}
    for l in L: per_block.setdefault(l["block"], set()).add(unpad(l["topics"][2]))
    minters = list(by.items())[:n_early]
    log("Checking mint transactions…")
    def info(item):
        m, ls = item; t = tx(ch, ls[0]["hash"]) or {}
        return m, ls, t
    with ThreadPoolExecutor(8) as ex: rows = list(ex.map(info, minters))
    with ThreadPoolExecutor(8) as ex: cflags = list(ex.map(lambda r: is_contract(ch, r[0]), rows))
    keep = []; sb = soulbound(ch, contract, int(L[0]["topics"][3], 16) if L[0]["topics"][0] == T_TRANSFER else 0, False)
    res["token"]["soulbound"] = bool(sb)
    for i, ((m, ls, t), c) in enumerate(zip(rows, cflags)):
        qty = len([l for l in L if l["hash"] == ls[0]["hash"]]) or 1
        val = int(t.get("value", "0x0"), 16) / 1e18 if t else 0
        w = {"wallet": m, "rank": i + 1, "secs": int((ls[0]["ts"] or t0) - t0), "t": ls[0]["ts"], "block": ls[0]["block"], "minted": len(ls),
             "sol": val, "mint_price": val / qty if qty else None, "flags": [], "self": bool(t) and t.get("from", "").lower() == m}
        if c: w["flags"].append("contract wallet / bot")
        if t and not w["self"]: w["flags"].append("airdrop or minted by another wallet")
        if len(per_block.get(w["block"], ())) >= 5 and w["secs"] <= 120: w["flags"].append(f"farm?: {len(per_block[w['block']])} wallets minted in one block")
        hard = [f for f in w["flags"] if not f.startswith("farm?")]
        (res["excluded"] if hard else keep).append(w)
    res["n_early"] = len(rows); partial(res)
    log(f"Mint history for {min(len(keep), 20)} minters…")
    def hist(w):
        try: return nft_mints(ch, w["wallet"], days=hist_days(ch, "nftscan"))
        except Exception: return []
    with ThreadPoolExecutor(3) as ex:
        H = list(ex.map(hist, keep[:20]))
    for i, (w, hs) in enumerate(zip(keep, H + [None] * (len(keep) - len(H)))):
        w["positions"] = []
        if hs is None: w["n_tokens"] = None; continue
        cols = {}
        for x in hs: cols.setdefault(x["collection"], []).append(x)
        w["n_tokens"] = len(cols); w["mints_total"] = len(hs); w["sampled_txs"] = len({x["hash"] for x in hs})
        w["positions"] = [{"mint": c, "symbol": (xs[0].get("symbol")), "first_buy": xs[0]["ts"], "sol_in": 0, "sol_out": 0, "x_now": None, "n": len(xs)} for c, xs in cols.items()]
        w["win_rate"] = None; w["best_x"] = None; w["n5"] = w["n10"] = w["peak_checked"] = 0
        fl_x = (res["token"]["floor"] / w["mint_price"]) if res["token"]["floor"] and w.get("mint_price") else None
        w["x_this"] = fl_x
        w["score"] = round(min(w["n_tokens"], 10) * 6 + (20 if w["secs"] <= 600 else 10 if w["secs"] <= 3600 else 0) + (10 if w["self"] else 0), 1)
    for w in keep: res["wallets"].append(w)
    res["wallets"].sort(key=lambda w: -(w.get("score") or 0)); res["finished"] = int(time.time())
    res["notes"] += [f"Early minters = first recipients of mints (transfers from the zero address) on {C['name']}.",
                     "Mint price = ETH value sent in the mint tx divided by items minted in it (ERC-20 or allowlist-paid mints show 0).",
                     f"Floor: {'OpenSea ' + str(res['token']['floor']) + ' ' + C['native'] if res['token']['floor'] else (why or 'not available')}." ,
                     f"Mint history = other collections each minter minted in the last {hist_days(ch, 'nftscan')} day(s) ({src_label(ch)}). Funding links between wallets are not traced.",
                     "Soulbound (non-transferable) collections can't be flipped. Copy-minting only works if the mint is open to everyone." if res["token"]["soulbound"] else "Numbers are estimates. Not financial advice."]
    return res

def _al_nft(x):
    tid = x.get("erc721TokenId") or ((x.get("erc1155Metadata") or [{}])[0].get("tokenId") if x.get("erc1155Metadata") else None) or (x.get("tokenId"))
    try: return int(tid, 16) if tid else None
    except Exception: return None

def nft_mints(ch, w, days=7, log=None):
    C = CHAINS[ch]; w = w.lower(); out = []; since = time.time() - days * 86400
    if alchemy_on(ch):
        r = alchemy_transfers(ch, w, ["erc721", "erc1155"], days, direction=("to",), from_zero=True)
        if r is not None:
            for x in r:
                ts = _al_ts(x)
                if (x.get("from") or "").lower() != ZERO or (ts and ts < since): continue
                out.append({"collection": ((x.get("rawContract") or {}).get("address") or "").lower(), "symbol": x.get("asset"), "ts": ts, "hash": x["hash"].lower(), "block": int(x["blockNum"], 16), "id": _al_nft(x)})
            return out
    if has_api(ch):
        ok = False
        for act in ("tokennfttx", "token1155tx"):
            r = api(ch, {"module": "account", "action": act, "address": w, "page": 1, "offset": 1000, "sort": "desc"}, ttl=1800)
            if r is None: continue
            ok = True
            for x in r:
                if x["from"].lower() == ZERO and x["to"].lower() == w and int(x["timeStamp"]) > since:
                    out.append({"collection": x["contractAddress"].lower(), "symbol": x.get("tokenSymbol") or x.get("tokenName"), "ts": int(x["timeStamp"]), "hash": x["hash"].lower(), "block": int(x["blockNumber"]), "id": x.get("tokenID")})
        if ok: return out
    L = logs_recent(ch, [[T_TRANSFER, ZT, pad(w)], [T_SINGLE, None, ZT, pad(w)]], days, log=log)
    _LAST_RPC_COVERAGE[(ch, w)] = (L.ok, L.total)
    for l in L:
        if l["topics"][0] == T_TRANSFER and len(l["topics"]) != 4: continue
        out.append({"collection": l["address"], "symbol": None, "ts": l["ts"], "hash": l["hash"], "block": l["block"], "id": int(l["topics"][3], 16) if l["topics"][0] == T_TRANSFER else None})
    return out

def nft_outgoing(ch, w, days):
    C = CHAINS[ch]; w = w.lower(); out = []; since = time.time() - days * 86400
    if alchemy_on(ch):
        r = alchemy_transfers(ch, w, ["erc721", "erc1155"], days, direction=("from",))
        if r is not None:
            for x in r:
                ts = _al_ts(x)
                if ts and ts < since: continue
                out.append({"collection": ((x.get("rawContract") or {}).get("address") or "").lower(), "ts": ts, "hash": x["hash"].lower(), "to": (x.get("to") or "").lower()})
            return out
    if has_api(ch):
        ok = False
        for act in ("tokennfttx", "token1155tx"):
            r = api(ch, {"module": "account", "action": act, "address": w, "page": 1, "offset": 1000, "sort": "desc"}, ttl=1800)
            if r is None: continue
            ok = True
            for x in r:
                if x["from"].lower() == w: out.append({"collection": x["contractAddress"].lower(), "ts": int(x["timeStamp"]), "hash": x["hash"].lower(), "to": x["to"].lower()})
        if ok: return out
    for l in logs_recent(ch, [[T_TRANSFER, pad(w)]], days):
        if len(l["topics"]) == 4: out.append({"collection": l["address"], "ts": l["ts"], "hash": l["hash"], "to": unpad(l["topics"][2])})
    return out

def check_nft_wallet(ch, w, log=lambda s: None, partial=lambda d: None):
    C = CHAINS[ch]; w = w.lower()
    days = hist_days(ch, "nftcheck")
    res = {"kind": "wallet", "chain": ch, "asset": "nft", "unit": C["native"], "wallet": w, "notes": [], "started": int(time.time())}
    log("Reading NFT mints…")
    M = nft_mints(ch, w, days=days, log=log); O = nft_outgoing(ch, w, days)
    contract = is_contract(ch, w)
    cols = {}
    LP_NFTS = {"0xc36442b4a4522e871399cd717abdd847ab11fe88", "0x03a520b32c04bf3beef7beb72e919cf822ed34f1", "0xbd216513d74c8cf14cf4747e6aaa6420ff64ee9e", "0x7c5f5a4bbd8fd63184577525326123b519429bdc", "0x46a15b0b27311cedf172ab29e4f4766fbe7f4364"}
    M = [x for x in M if x["collection"] not in LP_NFTS]
    for x in M: cols.setdefault(x["collection"], []).append(x)
    hashes = list(dict.fromkeys(x["hash"] for x in M))[:60]
    log(f"Checking {len(hashes)} mint transactions…")
    with ThreadPoolExecutor(8) as ex: T = dict(zip(hashes, ex.map(lambda h: tx(ch, h), hashes)))
    P = []
    for i, (c, xs) in enumerate(sorted(cols.items(), key=lambda kv: -kv[1][0]["ts"])[:25]):
        log(f"Collections: {i+1}/{min(len(cols), 25)}")
        meta = token_meta(ch, c)
        t0 = None
        if i < 12:
            try:
                fb = first_mint_block(ch, c); t0 = block_ts(ch, fb) if fb is not None else None
            except Exception: t0 = None
        txs = [T.get(x["hash"]) for x in xs if T.get(x["hash"])]
        own = sum(1 for t in txs if t.get("from", "").lower() == w)
        cost = sum(int(t.get("value", "0x0"), 16) / 1e18 for t in {t["hash"]: t for t in txs}.values() if t.get("from", "").lower() == w)
        outs = [o for o in O if o["collection"] == c]
        fl, why = os_floor(ch, c) if i < 12 else (None, "not checked")
        sb = soulbound(ch, c, xs[0]["id"] or 0, bool(outs)) if xs[0].get("id") is not None else None
        per = cost / len(xs) if xs else 0
        held = max(len(xs) - len(outs), 0)
        p = {"mint": c, "symbol": meta.get("symbol") or xs[0].get("symbol"), "first_buy": xs[0]["ts"], "n_buys": len(xs), "n_sells": len(outs),
             "sol_in": cost, "sol_out": 0.0, "value_left": (fl["floor"] * held) if fl else 0.0, "self_signed": own, "self_initiated": own > 0 and own >= len(txs) * 0.8,
             "floor": fl["floor"] if fl else None, "floor_note": why, "soulbound": bool(sb), "holding": held > 0, "transferred": bool(outs),
             "delay": (xs[0]["ts"] - t0) if t0 and xs[0]["ts"] and xs[0]["ts"] >= t0 else None, "delay_ref": "first mint", "hold_secs": None, "realized_x": None, "no_pair": False}
        p["sniped"] = False
        # outcome: floor now vs mint cost per item (free mints count as wins if they have a floor)
        if fl and per > 0: p["x_now"] = fl["floor"] / per; p["priced"] = True
        elif fl and per == 0: p["x_now"] = 99.0 if fl["floor"] > 0 else 0.0; p["priced"] = True; p["free_mint"] = True
        else: p["x_now"] = None; p["priced"] = False
        P.append(p)
    span_d = max(((max(x["ts"] for x in M) - min(x["ts"] for x in M)) / 86400) if M else days, 1)
    res["activity"] = {"tx_per_day": round(len(hashes) / span_d, 2), "failed_share": 0.0, "basis": "mint txs", "contract": contract, "mints": len(M), "collections": len(cols), "outgoing": len(O)}
    res["sampled_txs"] = len(hashes); res["positions"] = P
    res.update(nft_verdict(res, P, contract, days))
    if not M: res["notes"].append(empty_note(ch, w, days, "NFT mints"))
    res["finished"] = int(time.time())
    res["notes"] += [f"NFT mints = ERC-721/1155 transfers from the zero address to this wallet in the last {days} days ({src_label(ch)}).",
                     "Self-initiated = the wallet sent the mint transaction itself (not an airdrop or a mint by another wallet).",
                     "Outcome = OpenSea floor now vs mint cost per item. Free mints with a floor count as wins. Sale prices are not decoded, so flips show as sent out.",
                     "Soulbound / non-transferable items can't be flipped. They show the mint only.", "Numbers are estimates. Not financial advice."]
    return res

def nft_verdict(res, P, contract, days):
    n = len(P); own = sum(1 for p in P if p["self_initiated"]); self_share = own / n if n else None
    priced = [p for p in P if p.get("x_now") is not None and not p["soulbound"]]
    wins = sum(1 for p in priced if p["x_now"] >= 1); wr = wins / len(priced) if priced else None
    delays = [p["delay"] for p in P if p.get("delay") is not None]; med = st.median(delays) if delays else None
    mints_per_day = (res["activity"]["mints"] / days) if days else 0
    reasons = []
    s = {"n_tokens": len(priced), "wins": wins, "win_rate": wr, "best_x_now": max([p["x_now"] for p in priced], default=None), "best_realized": None,
         "n5": sum(1 for p in priced if p["x_now"] >= 5), "n10": sum(1 for p in priced if p["x_now"] >= 10), "peak_checked": len(priced),
         "pnl_sol": sum(p["value_left"] - p["sol_in"] for p in priced), "spent_sol": sum(p["sol_in"] for p in P), "median_delay": med, "delay_checked": len(delays),
         "share_first_hour": sum(1 for d in delays if d <= 3600) / len(delays) if delays else None, "median_hold": None, "avg_hold": None,
         "sniper_share": 0.0, "self_share": self_share, "holding_now": sum(1 for p in P if p["holding"]), "collections": n}
    early = med is not None and med <= 6 * 3600
    if n < 2: v = "Skip"; reasons.append(f"Only {n} collection(s) minted in the last {days} days, not enough to judge.")
    elif contract: v = "Watch for alpha" if (wr or 0) >= 0.5 else "Skip"; reasons.append("This is a contract wallet, so a copy-mint bot can't follow it.")
    elif (self_share or 0) >= 0.8 and n >= 3 and (early or med is None) and (wr is None or wr >= 0.5):
        v = "Copy-mint it"
        if wr is None: reasons.append("Outcomes unknown (no floor data), so confidence is lower.")
    elif n >= 2 and ((wr or 0) >= 0.5 or early): v = "Watch for alpha"
    else: v = "Skip"
    reasons.insert(0, f"Minted {res['activity']['mints']} NFT(s) across {n} collection(s) in {days} days, {own} self-initiated.")
    if wr is not None: reasons.append(f"{wins}/{len(priced)} priced collections have a floor at or above its mint cost.")
    if med is not None: reasons.append(f"Typical mint {wallet_check.fmt_dur(med)} after the collection's first mint.")
    sbn = sum(1 for p in P if p["soulbound"])
    if sbn: reasons.append(f"{sbn} collection(s) are soulbound (can't be flipped). Copy-minting works only if the mint is open.")
    if self_share is not None and self_share < 0.8: reasons.append(f"Only {self_share*100:.0f}% of mints were sent by this wallet itself (airdrops or delegated mints).")
    conf = "High" if len(priced) >= 8 and n >= 8 else "Medium" if n >= 4 else "Low"
    if wr is None and conf == "High": conf = "Medium"
    s.update(verdict=v, reasons=reasons, confidence=conf, confidence_why=f"{n} collections, {len(priced)} with floor data, timing known for {len(delays)}.")
    return s
