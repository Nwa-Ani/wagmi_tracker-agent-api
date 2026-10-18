"""Solana NFTs: mint history + collection early minters.
Uses Helius enhanced transactions (needs HELIUS_API_KEY) and Magic Eden's public collection stats for floors."""
import os, time, statistics as st
import core, wallet_check
from chains import evm

KEY = core.HELIUS_KEY
HAPI = "https://api.helius.xyz/v0"
ME = "https://api-mainnet.magiceden.dev/v2"
HLIM = core.Limiter(8); MLIM = core.Limiter(1.5)

def need_key():
    if not KEY: raise RuntimeError("Solana NFT mode needs a Helius API key (set HELIUS_API_KEY). Memecoin mode works without it.")

def htx(addr, typ=None, pages=3):
    need_key(); out = []; before = None
    for _ in range(pages):
        p = {"api-key": KEY, "limit": 100}
        if typ: p["type"] = typ
        if before: p["before"] = before
        key = core._ckey("helius-tx", addr, typ, before); hit = core._cget(key, 1800)
        if hit is not None: r = hit["r"]
        else:
            r = None
            for i in range(4):
                HLIM.wait()
                try:
                    x = core._sess.get(f"{HAPI}/addresses/{addr}/transactions", params=p, timeout=40)
                    if x.status_code == 200: r = x.json(); break
                except Exception: pass
                time.sleep(1 + i)
            r = r or []; core._cput(key, {"r": r})
        out += r
        if len(r) < 100: break
        before = r[-1]["signature"]
    return out

def parse(sigs):
    need_key(); out = []
    for i in range(0, len(sigs), 100):
        chunk = sigs[i:i + 100]; key = core._ckey("helius-parse", chunk); hit = core._cget(key, None)
        if hit is not None: out += hit["r"]; continue
        HLIM.wait()
        try:
            r = core._sess.post(f"{HAPI}/transactions", params={"api-key": KEY}, json={"transactions": chunk}, timeout=60).json()
        except Exception: r = []
        if isinstance(r, list): core._cput(key, {"r": r}); out += r
    return out

def me_collection(mint):
    d = core.http_json(f"{ME}/tokens/{mint}", MLIM, ttl=86400)
    sym = (d or {}).get("collection")
    if not sym: return None, None
    s = core.http_json(f"{ME}/collections/{sym}/stats", MLIM, ttl=1800) or {}
    return sym, (s.get("floorPrice") / 1e9 if s.get("floorPrice") else None)

def das(method, params, ttl=1800):
    need_key(); return core.rpc(method, params, ttl=ttl)

def asset_origin(aid):
    """First tx of an asset: (minter=fee payer, ts, SOL the fee payer spent)."""
    r = core.rpc("getSignaturesForAddress", [aid, {"limit": 1000}], ttl=None)
    if not r: return None
    first = r[-1]
    t = core._safe_tx(first["signature"])
    if not t: return {"minter": None, "ts": first.get("blockTime"), "paid": 0.0, "sig": first["signature"]}
    keys = [k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]; m = t["meta"]
    paid = max((m["preBalances"][0] - m["postBalances"][0]) / 1e9, 0.0)
    return {"minter": keys[0], "ts": t.get("blockTime"), "paid": paid, "sig": first["signature"], "complete": len(r) < 1000}

def coll_of(a):
    g = [x["group_value"] for x in a.get("grouping", []) if x["group_key"] == "collection"]
    return g[0] if g else None

def me_floor_by_mint(mint):
    sym, fl = me_collection(mint); return sym, fl

def check_wallet(w, log=lambda s: None, partial=lambda d: None):
    res = {"kind": "wallet", "chain": "sol", "asset": "nft", "unit": "SOL", "wallet": w, "notes": [], "started": int(time.time())}
    log("Reading NFTs held (Helius DAS)…")
    A = []
    for page in (1, 2):
        r = das("getAssetsByOwner", {"ownerAddress": w, "page": page, "limit": 1000, "sortBy": {"sortBy": "recent_action", "sortDirection": "desc"}}) or {}
        A += [a for a in r.get("items", []) if a.get("interface") in ("V1_NFT", "ProgrammableNFT", "MplCoreAsset", "V2_NFT", "LEGACY_NFT") or (a.get("compression") or {}).get("compressed")]
        if len(r.get("items", [])) < 1000: break
    groups = {}
    for a in A:
        c = coll_of(a)
        if c: groups.setdefault(c, []).append(a)
    log(f"Checking how {min(len(groups), 25)} collections were acquired…")
    sales = htx(w, "NFT_SALE", pages=1); sold = {}
    for t in sales:
        ev = (t.get("events") or {}).get("nft") or {}
        if ev.get("seller") == w:
            for n in ev.get("nfts") or []: sold[n.get("mint")] = ev.get("amount", 0) / 1e9
    P = []
    from concurrent.futures import ThreadPoolExecutor
    items = list(groups.items())[:40]
    def one(kv):
        c, xs = kv; a = xs[0]; o = asset_origin(a["id"]) or {}
        first_coll = (das("getAssetsByGroup", {"groupKey": "collection", "groupValue": c, "page": 1, "limit": 1, "sortBy": {"sortBy": "created", "sortDirection": "asc"}}, ttl=None) or {}).get("items", [])
        t0 = (asset_origin(first_coll[0]["id"]) or {}).get("ts") if first_coll else None
        sym, fl = me_collection(a["id"])
        return c, xs, o, t0, sym, fl
    with ThreadPoolExecutor(6) as ex: rows = list(ex.map(one, items))
    for c, xs, o, t0, sym, fl in rows:
        minted = o.get("minter") == w
        name = sym or ((xs[0].get("content") or {}).get("metadata") or {}).get("symbol") or ((xs[0].get("content") or {}).get("metadata") or {}).get("name", "").split("#")[0].strip() or core.short(c)
        per = o.get("paid", 0.0) if minted else None; held = len(xs)
        p = {"mint": c, "symbol": name, "first_buy": o.get("ts"), "n_buys": held, "n_sells": 0, "minted": minted, "sol_in": (per or 0) * held if minted else 0.0,
             "sol_out": 0.0, "value_left": (fl or 0) * held, "self_signed": held if minted else 0, "self_initiated": minted, "floor": fl, "holding": True,
             "soulbound": False, "delay": (o["ts"] - t0) if minted and o.get("ts") and t0 and o["ts"] >= t0 else None, "delay_ref": "first mint",
             "hold_secs": None, "sniped": False, "no_pair": False, "realized_x": None, "how": "minted" if minted else "bought / received"}
        if minted and fl is not None:
            p["x_now"] = (fl / per) if per and per > 0.002 else (99.0 if fl > 0 else 0.0); p["priced"] = True
            if not per or per <= 0.002: p["free_mint"] = True
        else: p["x_now"] = None; p["priced"] = False
        P.append(p)
    P.sort(key=lambda p: -(p["first_buy"] or 0))
    mintedP = [p for p in P if p["minted"]]
    ts = [p["first_buy"] for p in mintedP if p["first_buy"]]
    days = max(((max(ts) - min(ts)) / 86400) if len(ts) > 1 else 30, 1)
    res["activity"] = {"tx_per_day": round(len(mintedP) / days, 2), "failed_share": 0.0, "basis": "mints", "mints": len(mintedP), "collections": len(groups), "contract": False, "sold_recent": len(sold)}
    res["sampled_txs"] = len(A)
    # verdict on self-minted collections only; bought ones are listed for context
    res["positions"] = P
    v = evm.nft_verdict(res, mintedP, False, round(days))
    v["reasons"].append(f"{len(P) - len(mintedP)} other held collection(s) were bought or received, not minted.")
    if sold: v["reasons"].append(f"{len(sold)} NFT sale(s) in recent Helius history (sold items are not in the floor math).")
    res.update(v); res["finished"] = int(time.time())
    res["notes"] += ["Solana NFTs come from Helius DAS (NFTs the wallet holds now, 40 most recently active collections). Sold or burned NFTs are not covered.",
                     "Minted = this wallet paid the fee on the asset's first transaction. Mint cost = SOL the fee payer spent in that tx (includes rent).",
                     "Floors come from Magic Eden collection stats. Free mints with a floor count as wins.", "Numbers are estimates. Not financial advice."]
    return res

def scan_collection(coll, log=lambda s: None, partial=lambda d: None, n_early=40):
    """coll = collection address (Metaplex collection / Core collection). Earliest assets by creation."""
    res = {"kind": "token", "chain": "sol", "asset": "nft", "unit": "SOL", "mint": coll, "notes": [], "wallets": [], "excluded": [], "started": int(time.time())}
    log("Reading the collection's first items (Helius DAS)…")
    r = das("getAssetsByGroup", {"groupKey": "collection", "groupValue": coll, "page": 1, "limit": n_early, "sortBy": {"sortBy": "created", "sortDirection": "asc"}}, ttl=None) or {}
    A = r.get("items", [])
    if not A:
        a = das("getAsset", {"id": coll}, ttl=3600)
        c = coll_of(a or {}) if a else None
        if c and c != coll: return scan_collection(c, log, partial, n_early)
        raise RuntimeError("No items found for this Solana collection address (paste the collection address or any NFT from it).")
    log(f"Finding who minted the first {len(A)} items…")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex: O = list(ex.map(lambda a: asset_origin(a["id"]) or {}, A))
    sym, fl = me_collection(A[0]["id"])
    meta = (A[0].get("content") or {}).get("metadata") or {}
    res["token"] = {"symbol": sym or meta.get("symbol") or "NFT", "name": (meta.get("name", "").split("#")[0].strip() or sym or coll), "floor": fl, "floor_note": None if fl else "no Magic Eden floor"}
    ts = [o.get("ts") for o in O if o.get("ts")]; t0 = min(ts) if ts else None; res["launch_ts"] = t0
    seen = {}; per_slot = {}
    for a, o in zip(A, O):
        m = o.get("minter")
        if not m: continue
        per_slot.setdefault(o.get("ts"), set()).add(m)
        if m in seen: seen[m]["minted"] += 1; continue
        seen[m] = {"wallet": m, "t": o.get("ts"), "secs": (o["ts"] - t0) if o.get("ts") and t0 else None, "minted": 1, "sol": o.get("paid", 0.0), "mint_price": o.get("paid", 0.0), "flags": [], "self": True,
                   "holds": (a.get("ownership") or {}).get("owner") == m}
    keep = []
    for i, w in enumerate(seen.values()):
        w["rank"] = i + 1
        if len(per_slot.get(w["t"], ())) >= 5 and (w["secs"] or 0) <= 120: w["flags"].append(f"farm?: {len(per_slot[w['t']])} wallets minted in the same second")
        if w["minted"] >= 10: w["flags"].append("bulk minter (10+ of the first items)")
        hard = [f for f in w["flags"] if f.startswith("bulk")]
        (res["excluded"] if hard else keep).append(w)
    res["n_early"] = len(seen); partial(res)
    log(f"NFT holdings for {min(len(keep), 15)} minters…")
    def h(w):
        try:
            r = das("getAssetsByOwner", {"ownerAddress": w["wallet"], "page": 1, "limit": 1000}) or {}
            return len({coll_of(a) for a in r.get("items", []) if coll_of(a)})
        except Exception: return None
    with ThreadPoolExecutor(4) as ex: H = list(ex.map(h, keep[:15]))
    for w, n in zip(keep, H + [None] * (len(keep) - len(H))):
        w["n_tokens"] = n; w["positions"] = []; w["win_rate"] = None; w["best_x"] = None; w["n5"] = w["n10"] = w["peak_checked"] = 0
        w["x_this"] = (fl / w["mint_price"]) if fl and w["mint_price"] and w["mint_price"] > 0.002 else None
        w["score"] = round(min(n or 0, 30) * 1.5 + (20 if (w["secs"] or 0) <= 600 else 10 if (w["secs"] or 0) <= 3600 else 0) + (10 if w["holds"] else 0), 1)
        res["wallets"].append(w)
    res["wallets"].sort(key=lambda w: -w["score"]); res["finished"] = int(time.time())
    res["notes"] += ["Early minters = fee payers of the first transactions of the collection's oldest items (Helius DAS + RPC).",
                     "Mint cost = SOL the fee payer spent in that tx (includes rent and fees).", f"Floor: {str(fl) + ' SOL (Magic Eden)' if fl else 'not available'}.",
                     "Collections held = distinct collections in each minter's wallet now (top 15 minters).", "Numbers are estimates. Not financial advice."]
    return res
