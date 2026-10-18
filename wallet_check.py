"""Wallet Check: back-check one Solana wallet's recent memecoin trades and give a verdict.
Reuses core.py (RPC/HTTP caching, rate limits, position rebuilding, prices, peaks)."""
import os, time, statistics as st
from solders.pubkey import Pubkey
import core

CHECK_TXS = int(os.environ.get("CHECK_TXS", 120))      # recent txs read for the wallet
MAX_TOKENS = int(os.environ.get("CHECK_MAX_TOKENS", 30))  # tokens looked up for launch time
PEAK_BUDGET = int(os.environ.get("CHECK_PEAK_BUDGET", 15))
PUMPSWAP = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
TOKEN_PROGRAMS = ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"]

def holdings(wallet):
    """Current token balances {mint: uiAmount} (one cheap call per token program)."""
    out = {}
    for prog in TOKEN_PROGRAMS:
        try:
            r = core.rpc("getTokenAccountsByOwner", [wallet, {"programId": prog}, {"encoding": "jsonParsed"}], ttl=600)
        except Exception: return None
        for a in (r or {}).get("value", []):
            info = a["account"]["data"]["parsed"]["info"]
            out[info["mint"]] = out.get(info["mint"], 0) + float(info["tokenAmount"]["uiAmount"] or 0)
    return out

def launch_info(mint, pair):
    """Token launch (pump.fun curve start) and/or pool creation time. Cheap: <=3 history pages."""
    li = {"launch_ts": None, "launch_slot": None, "pool_ts": None, "pump": False}
    if pair and pair.get("pairCreatedAt"): li["pool_ts"] = pair["pairCreatedAt"] // 1000
    if mint.endswith("pump") or (pair and pair.get("dexId") in ("pumpfun", "pumpswap")):
        bc = str(Pubkey.find_program_address([b"bonding-curve", bytes(Pubkey.from_string(mint))], core.PUMP)[0])
        try:
            sigs, complete = core.all_sigs(bc, 3)
            if sigs and complete:
                li.update(launch_ts=sigs[0]["blockTime"], launch_slot=sigs[0]["slot"], pump=True)
        except Exception: pass
    if pair and pair.get("dexId") == "pumpfun" and li["launch_ts"] is None: li["launch_ts"] = li["pool_ts"]
    return li

ATA_PROG = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")

def find_missing_sells(wallet, pos, hold, log, limit=25):
    """Sells may fall outside the sample (e.g. pump volume accounts only see some txs). For tokens with
    no sell seen and no balance left, read that token account's own history to find where they went."""
    W = Pubkey.from_string(wallet); todo = [p for p in pos if p["n_sells"] == 0 and (hold is None or hold.get(p["mint"], 0) < 0.02 * p["tok_in"])][:limit]
    for i, p in enumerate(todo):
        log(f"Looking for sells outside the sample: {i+1}/{len(todo)} tokens")
        M = Pubkey.from_string(p["mint"])
        progs = TOKEN_PROGRAMS[::-1] if p["mint"].endswith("pump") else TOKEN_PROGRAMS
        sigs = []
        for prog in progs:
            ata = str(Pubkey.find_program_address([bytes(W), bytes(Pubkey.from_string(prog)), bytes(M)], ATA_PROG)[0])
            try: sigs = core.rpc("getSignaturesForAddress", [ata, {"limit": 40}], ttl=1800) or []
            except Exception: sigs = []
            if sigs: break
        later = [x for x in reversed(sigs) if not x.get("err") and x["blockTime"] and x["blockTime"] >= (p["first_buy"] or 0)]
        seen_out = 0
        for x in later[:8]:
            tx = core._safe_tx(x["signature"])
            if not tx: continue
            d, sol, _ = core.tx_deltas(tx, wallet); q = d.get(p["mint"], 0)
            if q < 0 and sol > 0:
                p["sol_out"] += sol; p["tok_out"] += -q; p["n_sells"] += 1; p["last_sell"] = x["blockTime"]; seen_out += -q
            elif q < 0: p["transferred"] = True; seen_out += -q
            if seen_out >= 0.98 * p["tok_in"]: break
        p["sells_from_ata"] = True

def fmt_dur(s):
    if s is None: return "n/a"
    s = abs(s)
    return f"{s:.0f}s" if s < 90 else f"{s/60:.0f}m" if s < 5400 else f"{s/3600:.1f}h" if s < 172800 else f"{s/86400:.0f}d"

def check(wallet, log=lambda s: None, partial=lambda d: None):
    res = {"kind": "wallet", "wallet": wallet, "started": int(time.time()), "notes": []}
    log("Reading wallet activity…")
    act = core.rpc("getSignaturesForAddress", [wallet, {"limit": 1000}], ttl=1800) or []
    if not act: raise RuntimeError("No transactions found for this wallet.")
    ok = [a for a in act if not a.get("err")]
    span_h = max((act[0]["blockTime"] - act[-1]["blockTime"]) / 3600, 0.01) if len(act) > 1 else None
    res["activity"] = {"recent_sigs": len(act), "failed_share": round(1 - len(ok) / len(act), 3),
                       "tx_per_day": round(len(act) / span_h * 24, 1) if span_h else None,
                       "span_hours": round(span_h, 1) if span_h else None, "last_tx": act[0]["blockTime"]}
    # Famous wallets get flooded with airdrop/poisoning spam signed by others. pump.fun and PumpSwap
    # keep a per-user "volume accumulator" account that only the user's own trades touch, so read that first.
    W = bytes(Pubkey.from_string(wallet)); acc = {}
    for prog in (core.PUMP, PUMPSWAP):
        pda = str(Pubkey.find_program_address([b"user_volume_accumulator", W], prog)[0])
        for x in core.rpc("getSignaturesForAddress", [pda, {"limit": 1000}], ttl=1800) or []: acc[x["signature"]] = x
    acc = sorted(acc.values(), key=lambda x: -x["blockTime"])
    acc_ok = [x for x in acc if not x.get("err")]
    # If the wallet's own raw history is mostly self-signed (not spammed), use it: it has buys AND sells.
    probe = ok[:15]; own = 0
    for x in probe:
        tx = core._safe_tx(x["signature"])
        if tx and core._keys(tx)[0]["pubkey"] == wallet: own += 1
    res["activity"]["self_signed_share_raw"] = round(own / len(probe), 2) if probe else None
    if len(acc_ok) >= 15 and (not probe or own / len(probe) < 0.6):
        res["source"] = "pump.fun + PumpSwap trades (via the wallet's pump volume accounts, so spam is filtered out)"
        sample = acc_ok[:CHECK_TXS]
        span = max((acc[0]["blockTime"] - acc[-1]["blockTime"]) / 3600, 0.01)
        res["activity"]["raw_tx_per_day"] = res["activity"]["tx_per_day"]
        res["activity"].update(tx_per_day=round(len(acc) / span * 24, 1), failed_share=round(1 - len(acc_ok) / len(acc), 3), basis="own pump trades")
    else:
        res["source"] = "all recent wallet txs (no pump.fun volume account history found)"
        sample = ok[:CHECK_TXS]; res["activity"]["basis"] = "all txs"
    log(f"Rebuilding trades from the last {len(sample)} txs…")
    pos = core.build_positions(wallet, sample, workers=core.WORKERS)
    res["sampled_txs"] = len(sample); res["sample_from"] = sample[-1]["blockTime"] if sample else None
    log("Current holdings and prices…")
    hold = holdings(wallet)
    find_missing_sells(wallet, pos, hold, log)
    prices = core.ds_pairs([p["mint"] for p in pos])
    pos.sort(key=lambda p: -(p["first_buy"] or 0))
    budget = [PEAK_BUDGET]
    for i, p in enumerate(pos):
        pr = prices.get(p["mint"])
        p["symbol"] = pr["baseToken"]["symbol"] if pr else None
        p["no_pair"] = not pr
        sol_pair = bool(pr and pr["quoteToken"]["address"] == core.WSOL and pr.get("priceNative"))
        now = float(pr["priceNative"]) if sol_pair else None
        p["priced"] = sol_pair or not pr
        left = max(p["tok_in"] - p["tok_out"], 0)
        if hold is not None: left = min(left, hold.get(p["mint"], 0))  # trust on-chain balance (catches transfers out)
        p["tok_left"] = left; p["holding"] = left > 0.02 * p["tok_in"]
        p["value_left"] = left * (now or 0)
        p["realized_x"] = p["sol_out"] / p["sol_in"] if p["n_sells"] else None
        p["x_now"] = (p["sol_out"] + p["value_left"]) / p["sol_in"] if p["priced"] else None
        p["entry"] = p["sol_in"] / p["tok_in"]
        p["hold_secs"] = (p["last_sell"] - p["first_buy"]) if p["last_sell"] and p["first_buy"] else None
        p["self_initiated"] = p["self_signed"] == p["n_buys"]
        if i < MAX_TOKENS:
            log(f"Launch times: {i+1}/{min(len(pos), MAX_TOKENS)} tokens")
            li = launch_info(p["mint"], pr); p.update(li)
            ref = None
            if li["launch_ts"] and (not li["pool_ts"] or p["first_buy"] <= li["pool_ts"] + 5 or not li["pump"]):
                ref, p["delay_ref"] = li["launch_ts"], "launch"
            elif li["pool_ts"]:
                ref, p["delay_ref"] = li["pool_ts"], "pool" if li["pump"] else "pool"
            p["delay"] = p["first_buy"] - ref if ref and p["first_buy"] else None
            if p["delay"] is not None and p["delay"] < 0:  # bought on the curve before the pool existed; launch time unknown
                p["pre_pool"] = True; p["delay"] = None
            p["sniped"] = bool((li["launch_slot"] and p["first_buy_slot"] == li["launch_slot"]) or (p["delay"] is not None and p["delay"] <= 2 and p.get("delay_ref") == "launch"))
        if sol_pair and budget[0] > 0 and p["first_buy"]:
            budget[0] -= 1; log(f"Peak prices (GeckoTerminal, slow): {PEAK_BUDGET - budget[0]}/{PEAK_BUDGET}")
            pk = core.gt_peak_native(pr["pairAddress"], p["first_buy"])
            if pk: p["x_peak"] = max(pk / p["entry"], p["x_now"] or 0)
        if i % 5 == 4: res["positions"] = pos; partial(res)
    res["positions"] = pos
    res.update(summarize(res, pos))
    res["finished"] = int(time.time())
    res["notes"] += [
        f"Trades read from: {res['source']}. Data via {core.RPC_LABEL}.",
        f"Based on this wallet's last {len(sample)} successful txs (about {fmt_dur(time.time() - res['sample_from']) if res['sample_from'] else 'n/a'} of history). Older trades are not counted.",
        "Sells that fall outside the sample are looked up on each token account. Tokens moved out by transfer (not sold) count as 0.",
        "Only simple token-for-SOL swaps are counted. USDC routes and multi-token txs are skipped.",
        "x now = (SOL from sells + tokens still held at today's DexScreener price) / SOL spent, fees included. Held amount is checked against the live balance.",
        "Entry timing is measured from the pump.fun launch (first bonding-curve tx) when it could be read cheaply, otherwise from pool creation on DexScreener.",
        "Peak x shows how high the price went after they bought (GeckoTerminal, hourly). It does not mean they sold there.",
        "Tokens with no DexScreener pair are counted as worth 0. The verdict is a rule-based estimate, not advice.",
    ]
    return res

def money(x, unit, signed=False):
    if unit == "USD": return (("+" if x >= 0 else "-") if signed else "") + f"${abs(x):,.2f}"
    return (f"{x:+.2f}" if signed else f"{x:.2f}") + f" {unit}"

def summarize(res, pos):
    unit = res.get("unit", "SOL")
    P = [p for p in pos if p["x_now"] is not None]
    n = len(P); wins = sum(1 for p in P if p["x_now"] >= 1)
    delays = [p["delay"] for p in pos if p.get("delay") is not None]
    holds = [p["hold_secs"] for p in pos if p.get("hold_secs") is not None]
    peaks = [p["x_peak"] for p in pos if p.get("x_peak")]
    sniped = sum(1 for p in pos if p.get("sniped"))
    self_ok = sum(1 for p in pos if p["self_initiated"])
    a = res["activity"]
    s = {
        "n_tokens": n, "wins": wins, "win_rate": wins / n if n else None,
        "best_x_now": max([p["x_now"] for p in P], default=None),
        "best_realized": max([p["realized_x"] for p in pos if p["realized_x"]], default=None),
        "n5": sum(1 for x in peaks if x >= 5), "n10": sum(1 for x in peaks if x >= 10), "peak_checked": len(peaks),
        "pnl_sol": sum(p["sol_out"] + p["value_left"] - p["sol_in"] for p in P),
        "spent_sol": sum(p["sol_in"] for p in P),
        "median_delay": st.median(delays) if delays else None, "delay_checked": len(delays),
        "share_first_hour": sum(1 for d in delays if d <= 3600) / len(delays) if delays else None,
        "median_hold": st.median(holds) if holds else None, "avg_hold": sum(holds) / len(holds) if holds else None,
        "sniper_share": sniped / len(delays) if delays else None,
        "self_share": self_ok / len(pos) if pos else None,
        "holding_now": sum(1 for p in pos if p["holding"]),
        "avg_buy_sol": st.median([p["sol_in"] for p in pos]) if pos else None,
    }
    # ---- verdict rules ----
    tpd = a["tx_per_day"] or 0
    bot = tpd > 1500 or (a["failed_share"] > 0.5 and tpd > 300) or (s["sniper_share"] or 0) >= 0.5
    fast = (s["median_hold"] is not None and s["median_hold"] < 120) or tpd > 400 or (s["sniper_share"] or 0) >= 0.25
    wr = s["win_rate"] or 0
    early = s["share_first_hour"] is not None and s["share_first_hour"] >= 0.5
    good_picks = n >= 3 and (wr >= 0.45 or s["n5"] >= 1 or (s["best_x_now"] or 0) >= 3 or (s["best_realized"] or 0) >= 3)
    pos_pnl = s["pnl_sol"] > 0
    reasons = []
    if n < 3:
        verdict = "Skip"; reasons.append(f"Only {n} priced token trade(s) in the sample, not enough to judge.")
    elif bot:
        verdict = "Good for alpha (watch its buys/sells)" if good_picks and pos_pnl else "Skip"
        if tpd > 1500: reasons.append(f"Bot-like activity: ~{tpd:,.0f} txs/day.")
        if a["failed_share"] > 0.5 and tpd > 300: reasons.append(f"{a['failed_share']*100:.0f}% failed txs (typical of sniper/spam bots).")
        if (s["sniper_share"] or 0) >= 0.5: reasons.append(f"Snipes launches: {s['sniper_share']*100:.0f}% of buys in the launch block or first 2s.")
    elif wr >= 0.45 and pos_pnl and early and not fast and (s["self_share"] or 0) >= 0.8:
        verdict = "Good for copy-minting/copy-trading"
    elif good_picks and (pos_pnl or s["n5"] >= 1):
        verdict = "Good for alpha (watch its buys/sells)"
        if fast: reasons.append("Too fast or too active for a copy bot to follow cleanly.")
        if not early: reasons.append("Usually buys after the first hour, so it is less of an early-entry signal.")
        if wr < 0.45: reasons.append(f"Win rate {wr*100:.0f}% is mixed, but it has found big movers.")
    else:
        verdict = "Skip"
    # positive / descriptive reasons
    if n >= 3: reasons.insert(0, f"Win rate ~{wr*100:.0f}% on {n} tokens, net {money(s['pnl_sol'], unit, True)} on {money(s['spent_sol'], unit)} spent.")
    if s["median_delay"] is not None: reasons.append(f"Typical entry {fmt_dur(s['median_delay'])} after launch/pool ({(s['share_first_hour'] or 0)*100:.0f}% within 1h).")
    if s["median_hold"] is not None: reasons.append(f"Median hold {fmt_dur(s['median_hold'])}.")
    if s["n5"]: reasons.append(f"{s['n5']} token(s) reached 5x+ after its entry ({s['peak_checked']} checked).")
    if s["self_share"] is not None and s["self_share"] < 0.8: reasons.append(f"Only {s['self_share']*100:.0f}% of buys signed by this wallet itself (others relayed), which makes copying harder.")
    if not bot and tpd: reasons.append(f"Activity ~{tpd:,.0f} {'pump trades' if a.get('basis') == 'own pump trades' else 'txs'}/day, {a['failed_share']*100:.0f}% failed.")
    if verdict == "Skip" and n >= 3 and not bot: reasons.append("Picks and returns are not strong enough to follow.")
    # confidence
    conf = "High" if n >= 12 else "Medium" if n >= 6 else "Low"
    if s["delay_checked"] < 3 and conf == "High": conf = "Medium"
    s.update(verdict=verdict, reasons=reasons, confidence=conf,
             confidence_why=f"{n} priced tokens from {res['sampled_txs']} txs; timing known for {s['delay_checked']}, peaks for {s['peak_checked']}.")
    return s
