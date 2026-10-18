"""Bitcoin Ordinals / Runes (limited, free data).
mempool.space for wallet txs and timing, ordinals.com HTML pages for rune / inscription details.
Rune mints are decoded from runestones (OP_RETURN OP_13) in the wallet's own txs. No free price feed is available,
so outcomes are not priced."""
import re, time, html, statistics as st
import core

MP = "https://mempool.space/api"; ORD = "https://ordinals.com"
LIM = core.Limiter(3)

def get(u, ttl=600, as_text=False):
    key = core._ckey("btc", u); hit = core._cget(key, ttl)
    if hit is not None: return hit["r"]
    for i in range(4):
        LIM.wait()
        try:
            r = core._sess.get(u, timeout=40)
            if r.status_code == 200:
                v = r.text if as_text else r.json(); core._cput(key, {"r": v}); return v
            if r.status_code == 404: return None
        except Exception: pass
        time.sleep(1 + 2 * i)
    return None

def ord_fields(path):
    t = get(ORD + path, ttl=3600, as_text=True)
    if not t: return {}
    pairs = re.findall(r"<dt>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", t, re.S)
    clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
    out = {clean(k): clean(v) for k, v in pairs}
    m = re.search(r"<h1>(.*?)</h1>", t, re.S)
    if m: out["_title"] = clean(m.group(1))
    return out

def varints(b):
    out, cur, sh = [], 0, 0
    for x in b:
        cur |= (x & 0x7f) << sh; sh += 7
        if not x & 0x80: out.append(cur); cur, sh = 0, 0
    return out

def runestone_mint(spk_hex):
    """Return (block, tx) of the rune minted by a runestone output, if any."""
    if not spk_hex.startswith("6a5d"): return None
    b = bytes.fromhex(spk_hex[4:]); data = b""; i = 0
    while i < len(b):  # concatenate data pushes
        op = b[i]; i += 1
        if 1 <= op <= 75: data += b[i:i + op]; i += op
        elif op == 76: n = b[i]; data += b[i + 1:i + 1 + n]; i += 1 + n
        elif op == 77: n = int.from_bytes(b[i:i + 2], "little"); data += b[i + 2:i + 2 + n]; i += 2 + n
        else: break
    v = varints(data); fields = {}; k = 0
    while k + 1 < len(v):
        tag, val = v[k], v[k + 1]
        if tag == 0: break
        fields.setdefault(tag, []).append(val); k += 2
    m = fields.get(20)
    if m and len(m) >= 2: return (m[0], m[1])
    if (fields.get(2) or [0])[0] & 1: return ("etch", 0)
    return None

def wallet_txs(addr, pages=4):
    out = []; last = None
    for _ in range(pages):
        r = get(f"{MP}/address/{addr}/txs" + (f"/chain/{last}" if last else ""), ttl=900) or []
        out += r
        if len(r) < 25: break
        last = r[-1]["txid"]
    return out

def check_wallet(addr, log=lambda s: None, partial=lambda d: None):
    res = {"kind": "wallet", "chain": "btc", "asset": "nft", "unit": "BTC", "wallet": addr, "notes": [], "started": int(time.time())}
    log("Reading Bitcoin transactions (mempool.space)…")
    T = wallet_txs(addr)
    if not T: raise RuntimeError("No transactions found for this Bitcoin address.")
    mints = {}; insc = []; etched = []
    for t in T:
        own = any((v.get("prevout") or {}).get("scriptpubkey_address") == addr for v in t["vin"])
        ts = (t.get("status") or {}).get("block_time") or int(time.time())
        fee = t.get("fee", 0) / 1e8
        for o in t["vout"]:
            rm = runestone_mint(o.get("scriptpubkey", ""))
            if rm and rm[0] == "etch" and own: etched.append({"ts": ts, "txid": t["txid"], "h": (t.get("status") or {}).get("block_height")}); continue
            if rm and own: mints.setdefault(f"{rm[0]}:{rm[1]}", []).append({"ts": ts, "fee": fee, "txid": t["txid"], "h": (t.get("status") or {}).get("block_height")})
        if any("0063036f7264" in "".join(v.get("witness") or []) for v in t["vin"]) and any(o.get("scriptpubkey_address") == addr for o in t["vout"]):
            insc.append({"ts": ts, "fee": fee, "txid": t["txid"], "self": own})
    log("Looking up runes (ordinals.com)…")
    P = []
    for i, (rid, xs) in enumerate(sorted(mints.items(), key=lambda kv: -kv[1][0]["ts"])):
        f = ord_fields(f"/rune/{rid}") if i < 15 else {}
        start = None
        try: start = int(f.get("start") or f.get("etching block") or 0)
        except Exception: pass
        first_h = min(x["h"] or 10**9 for x in xs)
        P.append({"mint": rid, "symbol": f.get("_title", "").replace("Rune ", "") or rid, "first_buy": min(x["ts"] for x in xs), "n_buys": len(xs), "n_sells": 0,
                  "sol_in": sum(x["fee"] for x in xs), "sol_out": 0.0, "value_left": 0.0, "x_now": None, "priced": False, "self_initiated": True, "self_signed": len(xs),
                  "holding": None, "soulbound": False, "realized_x": None, "hold_secs": None, "no_pair": False, "sniped": False,
                  "delay": (first_h - start) * 600 if start and first_h < 10**9 and first_h >= start else None, "delay_ref": "mint open (blocks x 10m)",
                  "kind": "rune", "mints_total": f.get("mints")})
    if insc:
        P.append({"mint": "inscriptions", "symbol": f"{len(insc)} inscription(s)", "first_buy": min(x["ts"] for x in insc), "n_buys": len(insc), "n_sells": 0,
                  "sol_in": sum(x["fee"] for x in insc), "sol_out": 0.0, "value_left": 0.0, "x_now": None, "priced": False, "self_initiated": all(x["self"] for x in insc),
                  "self_signed": sum(x["self"] for x in insc), "holding": None, "soulbound": False, "realized_x": None, "hold_secs": None, "no_pair": False, "sniped": False,
                  "delay": None, "delay_ref": "", "kind": "inscription"})
    for e in etched:
        P.append({"mint": e["txid"], "symbol": "rune etching", "first_buy": e["ts"], "n_buys": 1, "n_sells": 0, "sol_in": 0.0, "sol_out": 0.0, "value_left": 0.0,
                  "x_now": None, "priced": False, "self_initiated": True, "self_signed": 1, "holding": None, "soulbound": False, "realized_x": None, "hold_secs": None,
                  "no_pair": False, "sniped": False, "delay": None, "delay_ref": "", "kind": "etching"})
    res["etchings"] = len(etched)
    span = max((T[0].get("status", {}).get("block_time", time.time()) - T[-1].get("status", {}).get("block_time", time.time())) / 86400, 1)
    res["activity"] = {"tx_per_day": round(len(T) / span, 2), "failed_share": 0.0, "basis": "txs", "mints": sum(len(x) for x in mints.values()) + len(insc), "collections": len(P), "contract": False}
    res["sampled_txs"] = len(T); res["positions"] = P
    delays = [p["delay"] for p in P if p.get("delay") is not None]; med = st.median(delays) if delays else None
    n = len(P); reasons = ([f"Etched (created) {len(etched)} rune(s) itself. That's a creator, not a minter to copy."] if etched else []) + [f"{res['activity']['mints']} rune mint / inscription tx(s) across {n} item type(s) in the last {len(T)} txs."]
    if med is not None: reasons.append(f"Typical rune mint about {round(med/600)} blocks after minting opened.")
    reasons.append("No free price feed for Runes/Ordinals, so outcomes (win rate, multiples) can't be measured.")
    early = med is not None and med <= 6 * 600
    v = "Skip" if n < 2 else ("Copy-mint it" if early and n >= 3 else "Watch for alpha")
    res.update({"n_tokens": 0, "wins": 0, "win_rate": None, "best_x_now": None, "best_realized": None, "n5": 0, "n10": 0, "peak_checked": 0, "pnl_sol": 0.0,
                "spent_sol": sum(p["sol_in"] for p in P), "median_delay": med, "delay_checked": len(delays), "median_hold": None, "avg_hold": None, "sniper_share": 0.0,
                "self_share": 1.0 if P else None, "holding_now": 0, "verdict": v, "reasons": reasons, "confidence": "Low",
                "confidence_why": "Timing and activity only. No free BTC price data, so outcomes are unknown."})
    res["finished"] = int(time.time())
    res["notes"] += ["Rune mints are decoded from runestones in this address's own transactions. Inscriptions are detected from 'ord' envelopes in the inputs.",
                     "Cost = network fees paid (BTC). No free Runes/Ordinals price feed is available, so outcomes are not priced.",
                     "Only the last ~100 transactions are read (mempool.space).", "Numbers are estimates. Not financial advice."]
    return res

def scan(q, log=lambda s: None, partial=lambda d: None):
    """Rune name/id or inscription id. Free data cannot list every early minter, so this shows the asset's own facts."""
    q = q.strip(); res = {"kind": "token", "chain": "btc", "asset": "nft", "unit": "BTC", "mint": q, "notes": [], "wallets": [], "excluded": [], "started": int(time.time())}
    log("Looking it up on ordinals.com…")
    if re.match(r"^[0-9a-f]{64}i\d+$", q):
        f = ord_fields(f"/inscription/{q}"); kind = "inscription"
    else:
        f = ord_fields(f"/rune/{q.upper()}"); kind = "rune"
    if not f: raise RuntimeError("Not found on ordinals.com.")
    res["token"] = {"symbol": f.get("_title", q).replace("Rune ", "").replace("Inscription ", "#"), "name": f.get("_title", q), "facts": {k: v for k, v in f.items() if not k.startswith("_")}, "btc_kind": kind}
    if kind == "inscription" and f.get("address"):
        res["wallets"].append({"wallet": f["address"], "rank": 1, "secs": 0, "sol": float(f.get("fee", "0") or 0) / 1e8, "flags": [], "n_tokens": None, "positions": [], "score": 0, "note": "current owner"})
    res["n_early"] = len(res["wallets"]); res["finished"] = int(time.time())
    res["notes"] += ["Bitcoin has no free index of every rune minter or inscription buyer, so 'first buyers' can't be listed without a paid indexer.",
                     "Shown: the rune or inscription's own facts from ordinals.com (etching, mints, supply, owner). Use Check a wallet for a minter's history.",
                     "Not financial advice."]
    return res
