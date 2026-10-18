"""Extra features built on top of scans: Paperhands enrich, Rug Check, Cabal Detector,
Smart Money Radar, Leaderboard, optional LLM roast. Everything reads cached scan results first."""
import os, json, glob, time, statistics as st
from concurrent.futures import ThreadPoolExecutor
import core
from chains import evm

RESULTS = os.path.join(core.CACHE, "results")
SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
RAY_AUTH = {"5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", "GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL"}

def all_results():
    """Every cached/sample result once (newest wins), tagged with chain/asset/kind."""
    seen = {}
    for d in (SAMPLES, RESULTS):
        for f in glob.glob(os.path.join(d, "*.json")):
            k = os.path.basename(f)[:-5]
            try: r = json.load(open(f))
            except Exception: continue
            r.setdefault("chain", "sol"); r.setdefault("asset", "coin" if r.get("asset") != "nft" else "nft")
            r["_kind"] = "wallet" if (r.get("kind") == "wallet" or k.startswith("wallet_") or "-wallet_" in k) else "token"
            r["_mtime"] = os.path.getmtime(f); seen[k] = r
    return list(seen.values())

# ---------------- Paperhands ----------------
def enrich_paperhands(res):
    """For sold positions: value if never sold (tokens bought x price now) vs what it got. Adds hold_value / missed."""
    if res.get("asset") == "nft": return res
    ch = res.get("chain", "sol"); P = [p for p in res.get("positions", []) if p.get("n_sells") and p.get("tok_in")]
    if not P: return res
    try:
        if ch == "sol":
            pairs = core.ds_pairs([p["mint"] for p in P]); px = lambda pr: float(pr.get("priceNative") or 0) if pr and (pr.get("quoteToken") or {}).get("address") == core.WSOL else None
        else:
            pairs = evm.ds_pairs(ch, [p.get("token") or p["mint"] for p in P]); px = lambda pr: float(pr.get("priceUsd") or 0) if pr else None
    except Exception: return res
    for p in P:
        pr = pairs.get(p.get("token") or p["mint"]); now = px(pr)
        if now is None: continue
        got = (p.get("sol_out") or 0) + (p.get("value_left") or 0)
        p["price_now"] = now; p["hold_value"] = p["tok_in"] * now; p["missed"] = p["hold_value"] - got
    return res

# ---------------- Rug Check ----------------
def rug_sol(mint, scan=None):
    out = {"chain": "sol", "mint": mint, "checks": []}
    add = lambda name, status, detail: out["checks"].append({"name": name, "status": status, "detail": detail})
    info = core.rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}], ttl=600) or {}
    v = (((info.get("value") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
    ma, fa = v.get("mintAuthority"), v.get("freezeAuthority")
    add("Mint authority", "red" if ma else "green", "Can still mint new supply" if ma else "Revoked, supply is fixed")
    add("Freeze authority", "red" if fa else "green", "Can freeze holders' tokens" if fa else "Revoked, nobody can freeze your tokens")
    supply = float(v.get("supply") or 0) / 10 ** int(v.get("decimals") or 0) if v else 0
    pr = core.ds_pairs([mint]).get(mint)
    pool = (pr or {}).get("pairAddress"); dex = (pr or {}).get("dexId", "")
    try:
        L = (core.rpc("getTokenLargestAccounts", [mint], ttl=600) or {}).get("value", [])[:20]
        accs = core.rpc("getMultipleAccounts", [[a["address"] for a in L], {"encoding": "jsonParsed"}], ttl=600) or {}
        owners = [((((x or {}).get("data") or {}).get("parsed") or {}).get("info") or {}).get("owner") for x in accs.get("value", [])]
        rows = []
        for a, o in zip(L, owners):
            amt = float(a.get("uiAmount") or 0); poolish = o == pool or o in RAY_AUTH
            if not poolish and o:  # pump.fun curve / AMM pool PDAs are owned by programs
                ai = core.rpc("getAccountInfo", [o, {"encoding": "base64"}], ttl=86400) or {}
                own = (ai.get("value") or {}).get("owner")
                poolish = own not in (None, "11111111111111111111111111111111")
            rows.append({"owner": o, "pct": amt / supply * 100 if supply else 0, "pool": poolish})
        hold = [r for r in rows if not r["pool"]]; top10 = sum(r["pct"] for r in hold[:10]); top1 = hold[0]["pct"] if hold else 0
        out["top_holders"] = rows[:12]
        add("Top 10 holders", "red" if top10 > 50 else "yellow" if top10 > 30 else "green", f"{top10:.1f}% of supply (pools and curves excluded), biggest wallet {top1:.1f}%")
    except Exception as e:
        add("Top 10 holders", "gray", "Couldn't read holders right now")
    dev = (scan or {}).get("dev")
    if dev:
        bought = sum(w.get("tokens", 0) for w in (scan.get("excluded", []) + scan.get("wallets", [])) if w.get("wallet") == dev)
        try:
            r = core.rpc("getTokenAccountsByOwner", [dev, {"mint": mint}, {"encoding": "jsonParsed"}], ttl=300) or {}
            bal = sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0) for a in r.get("value", []))
            pct = bal / supply * 100 if supply else 0
            if bought and bal < 0.1 * bought: add("Dev wallet", "yellow", f"Dev ({core.short(dev)}) sold most of their buy. Holds {pct:.2f}% now.")
            elif pct > 5: add("Dev wallet", "red", f"Dev ({core.short(dev)}) still holds {pct:.1f}% of supply, could dump.")
            else: add("Dev wallet", "green", f"Dev ({core.short(dev)}) holds {pct:.2f}% of supply.")
        except Exception: add("Dev wallet", "gray", "Couldn't read the dev's balance")
    else: add("Dev wallet", "gray", "Dev not identified (run Scan a coin first)")
    if dex == "pumpfun": add("Liquidity", "yellow", "Still on the pump.fun bonding curve, no LP tokens yet")
    elif dex == "pumpswap": add("Liquidity", "green", "Migrated from pump.fun to PumpSwap. pump.fun burns migration LP")
    else: add("Liquidity", "gray", f"LP lock/burn unknown for {dex or 'this pool'} (no free source)")
    liq = ((pr or {}).get("liquidity") or {}).get("usd")
    if liq is not None: add("Pool size", "red" if liq < 10000 else "yellow" if liq < 50000 else "green", f"${liq:,.0f} liquidity on {dex}")
    return score(out)

def rug_evm(ch, token, scan=None):
    out = {"chain": ch, "mint": token, "checks": []}
    add = lambda name, status, detail: out["checks"].append({"name": name, "status": status, "detail": detail})
    try:
        r = evm.rpc(ch, "eth_call", [{"to": token, "data": "0x8da5cb5b"}, "latest"], ttl=600)
        if r is None or r == "0x": add("Owner", "gray", "No owner() function (can't tell if renounced)")
        else:
            o = "0x" + r[-40:]
            add("Owner", "green" if int(o, 16) in (0, 0xdead) else "yellow", "Ownership renounced" if int(o, 16) in (0, 0xdead) else f"Owned by {o[:6]}…{o[-4:]}, owner may hold special powers")
    except Exception: add("Owner", "gray", "Couldn't read owner()")
    dev = None
    if evm.has_api(ch):
        c = evm.api(ch, {"module": "contract", "action": "getcontractcreation", "contractaddresses": token}, ttl=86400)
        if c: dev = c[0].get("contractCreator", "").lower()
    if dev:
        try:
            meta = evm.token_meta(ch, token); bal = int(evm.rpc(ch, "eth_call", [{"to": token, "data": "0x70a08231" + "0" * 24 + dev[2:]}, "latest"], ttl=300) or "0x0", 16) / 10 ** meta["decimals"]
            sup = int(evm.rpc(ch, "eth_call", [{"to": token, "data": "0x18160ddd"}, "latest"], ttl=3600) or "0x0", 16) / 10 ** meta["decimals"]
            pct = bal / sup * 100 if sup else 0
            add("Dev wallet", "red" if pct > 5 else "green", f"Deployer {dev[:6]}…{dev[-4:]} holds {pct:.2f}% of supply")
        except Exception: add("Dev wallet", "gray", "Couldn't read the deployer's balance")
    else: add("Dev wallet", "gray", "Deployer lookup needs an explorer API on this chain")
    add("Top 10 holders", "gray", "Holder list isn't free on this chain without an indexer key")
    pr = evm.ds_pairs(ch, [token]).get(token.lower()) or evm.ds_pairs(ch, [token]).get(token)
    liq = ((pr or {}).get("liquidity") or {}).get("usd")
    dex = (pr or {}).get("dexId", ""); lab = ", ".join((pr or {}).get("labels") or [])
    add("Liquidity", "gray", f"LP lock/burn unknown ({dex} {lab}".strip() + "). v3/v4 pools use NFT positions, check a locker manually")
    if liq is not None: add("Pool size", "red" if liq < 10000 else "yellow" if liq < 50000 else "green", f"${liq:,.0f} liquidity on {dex}")
    return score(out)

def score(out):
    pts = {"green": 0, "yellow": 1, "red": 3}; known = [c for c in out["checks"] if c["status"] != "gray"]
    s = sum(pts[c["status"]] for c in known)
    reds = sum(c["status"] == "red" for c in known)
    out["light"] = "red" if reds >= 2 or s >= 5 else "yellow" if s >= 2 or reds else "green"
    out["label"] = {"red": "High risk", "yellow": "Be careful", "green": "Looks OK"}[out["light"]]
    out["known"] = len(known); out["note"] = "Automated checks on public data. A green light is not a guarantee. Not financial advice."
    return out

# ---------------- Cabal Detector ----------------
def funder_sol(w):
    """First SOL sender of a wallet, if its whole history fits in one page."""
    r = core.rpc("getSignaturesForAddress", [w, {"limit": 1000}], ttl=86400)
    if not r or len(r) >= 1000: return None
    t = core._safe_tx(r[-1]["signature"])
    if not t: return None
    keys = [k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]; m = t["meta"]
    deltas = [(m["postBalances"][i] - m["preBalances"][i], k) for i, k in enumerate(keys)]
    src = min(deltas)[1]
    return src if src != w else None

def cabal(res):
    ch = res.get("chain", "sol"); W = res.get("wallets", []) + res.get("excluded", [])
    groups = []
    by_block = {}
    for w in W: by_block.setdefault(w.get("slot") or w.get("block"), []).append(w["wallet"])
    for b, ws in by_block.items():
        if b and len(set(ws)) >= 3: groups.append({"type": "Same block", "why": f"{len(set(ws))} wallets bought in the same block", "wallets": sorted(set(ws))})
    me = res.get("mint"); idx = {}
    for r in all_results():
        if r["_kind"] != "token" or r.get("mint") == me: continue
        for w in r.get("wallets", []) + r.get("excluded", []): idx.setdefault(w["wallet"], set()).add((r.get("token") or {}).get("symbol") or r.get("mint"))
    co = {}
    addrs = [w["wallet"] for w in W]
    for i, a in enumerate(addrs):
        for b in addrs[i + 1:]:
            both = idx.get(a, set()) & idx.get(b, set())
            if both: co.setdefault(frozenset(both), set()).update((a, b))
    for toks, ws in co.items():
        groups.append({"type": "Co-buyers", "why": "Also early together in " + ", ".join("$" + t for t in sorted(toks)[:4]), "wallets": sorted(ws)})
    funded = {}
    if ch == "sol":
        with ThreadPoolExecutor(6) as ex:
            F = list(ex.map(lambda a: (a, (lambda: funder_sol(a))() if True else None), addrs[:30]))
        for a, f in F:
            if f: funded.setdefault(f, []).append(a)
        for f, ws in funded.items():
            if len(ws) >= 2: groups.append({"type": "Same funder", "why": f"Funded by the same wallet {core.short(f)}", "funder": f, "wallets": ws})
    groups.sort(key=lambda g: -len(g["wallets"]))
    flagged = {a for g in groups for a in g["wallets"]}
    return {"groups": groups, "checked": len(addrs), "flagged": len(flagged),
            "note": ("Same funder = first SOL sender, only for wallets whose full history is short (first 30 early wallets). " if ch == "sol" else "Funding links are not traced on this chain. ")
                    + "Co-buyers compares against other coins already scanned here. A group is a hint, not proof."}

# ---------------- Radar / Leaderboard ----------------
def top_wallets():
    best = {}
    for r in all_results():
        ch = r.get("chain", "sol")
        if r["_kind"] == "token":
            for w in r.get("wallets", []):
                if (w.get("score") or 0) >= 50 and (w.get("n_tokens") or 0) >= 3:
                    k = (ch, w["wallet"]); cur = best.get(k)
                    if not cur or w["score"] > cur["score"]:
                        best[k] = {"wallet": w["wallet"], "chain": ch, "asset": r.get("asset", "coin"), "score": w["score"], "win_rate": w.get("win_rate"), "best_x": w.get("best_x"),
                                   "n_tokens": w.get("n_tokens"), "n5": w.get("n5"), "from": "$" + ((r.get("token") or {}).get("symbol") or "?"), "positions": w.get("positions", []), "seen": 0}
                    best[k]["seen"] = best[k].get("seen", 0) + 1
        else:
            v = r.get("verdict") or ""
            if v.startswith(("Good for", "Copy")):
                k = (ch, r["wallet"]); sc = round(100 * ((r.get("win_rate") or 0) * 0.6 + min(r.get("n5") or 0, 4) / 10) + (10 if v.startswith(("Good for copy", "Copy")) else 0), 1)
                cur = best.get(k)
                if not cur or sc > cur["score"]:
                    best[k] = {"wallet": r["wallet"], "chain": ch, "asset": r.get("asset", "coin"), "score": sc, "win_rate": r.get("win_rate"), "best_x": r.get("best_x_now"), "n_tokens": r.get("n_tokens"),
                               "n5": r.get("n5"), "from": "wallet check: " + v.split(" (")[0], "positions": r.get("positions", []), "seen": (cur or {}).get("seen", 0) + 1}
    return sorted(best.values(), key=lambda x: -x["score"])

def leaderboard(limit=50):
    L = top_wallets()[:limit]
    return {"rows": [{k: v for k, v in x.items() if k != "positions"} for x in L], "note": "Built only from scans already run on this site (cached). Scores are estimates."}

RADAR_LIVE = os.path.join(core.CACHE, "radar_live.json")
def radar(refresh=False, since_days=7):
    T = top_wallets()[:25]; feed = []; cut = time.time() - since_days * 86400
    for w in T:
        for p in w["positions"]:
            if (p.get("first_buy") or 0) >= cut:
                feed.append({"wallet": w["wallet"], "chain": w["chain"], "score": w["score"], "mint": p.get("mint"), "symbol": p.get("symbol"), "ts": p["first_buy"],
                             "spent": p.get("sol_in"), "x_now": p.get("x_now"), "src": "cached scan"})
    live = {}
    if refresh: live = refresh_radar([w for w in T if w["chain"] == "sol"][:8])
    elif os.path.exists(RADAR_LIVE):
        try: live = json.load(open(RADAR_LIVE))
        except Exception: live = {}
    feed += live.get("items", [])
    uniq = {}
    for f in feed: uniq.setdefault((f["wallet"], f["mint"]), f)
    feed = sorted(uniq.values(), key=lambda f: -(f["ts"] or 0))[:80]
    return {"items": feed, "wallets": len(T), "refreshed": live.get("at"),
            "note": "Recent buys by the best wallets this site has already scanned. Refresh pulls the latest 25 txs of the top 8 Solana wallets, only when you press it."}

def refresh_radar(T):
    items = []
    def one(w):
        out = []
        try:
            sigs = core.rpc("getSignaturesForAddress", [w["wallet"], {"limit": 25}], ttl=120) or []
            for s in sigs:
                if s.get("err"): continue
                t = core._safe_tx(s["signature"])
                if not t: continue
                d, solv, payer = core.tx_deltas(t, w["wallet"])
                for m, amt in d.items():
                    if amt > 0 and solv < -0.01: out.append({"wallet": w["wallet"], "chain": "sol", "score": w["score"], "mint": m, "symbol": None, "ts": t.get("blockTime"), "spent": -solv, "x_now": None, "src": "live"})
        except Exception: pass
        return out
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(one, T): items += r
    pairs = core.ds_pairs([i["mint"] for i in items]) if items else {}
    for i in items:
        pr = pairs.get(i["mint"])
        if pr: i["symbol"] = pr["baseToken"]["symbol"]
    live = {"at": int(time.time()), "items": items}
    try: json.dump(live, open(RADAR_LIVE, "w"))
    except OSError: pass
    return live

# ---------------- optional LLM roast ----------------
def llm_roast(stats):
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key: return None
    prompt = ("Write a short, playful roast (3 sentences max, PG-13, no slurs, no insults about identity, nothing about real-world harm) of a crypto wallet "
              "based only on these stats. Be funny about trading habits. Stats: " + json.dumps(stats)[:1500])
    try:
        r = core._sess.post("https://api.x.ai/v1/chat/completions", headers={"Authorization": "Bearer " + key},
                            json={"model": os.environ.get("ROAST_MODEL", "grok-3-mini"), "messages": [{"role": "user", "content": prompt}], "max_tokens": 200}, timeout=40)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception: return None
