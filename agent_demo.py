#!/usr/bin/env python3
"""wagmi_tracker x402 demo agent: an AI agent that pays per call on Solana DEVNET (no accounts, no subscription).

  python3 agent_demo.py --server http://localhost:8787 --chain sol --address <wallet>
  python3 agent_demo.py ... --fail wrong-amount|wrong-mint|replay|expired|tampered-quote|garbage|wrong-recipient|no-funds

Uses a burner devnet keypair (.secrets/agent_payer.json or AGENT_KEYPAIR=path). The secret key is never printed."""
import argparse, base64, json, os, sys, time
import requests
from solders.keypair import Keypair
import x402_svm as s

G, Y, R, B, D, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[2m", "\033[0m"
def step(n, t): print(f"\n{B}{G}[{n}]{X} {B}{t}{X}")
def kv(k, v): print(f"    {D}{k:<14}{X} {v}")

def devnet_rpc(method, params):
    url = os.environ.get("DEVNET_RPC", "https://api.devnet.solana.com")
    return requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=20).json()["result"]

def load_kp():
    p = os.environ.get("AGENT_KEYPAIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secrets", "agent_payer.json")
    return Keypair.from_bytes(bytes(json.load(open(p))))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("WAGMI_SERVER", "http://localhost:8787"))
    ap.add_argument("--endpoint", default="wallet-check", choices=["wallet-check", "coin-scan"])
    ap.add_argument("--chain", default="sol"); ap.add_argument("--address", required=True)
    ap.add_argument("--fresh", default="1"); ap.add_argument("--fail", default="", choices=["", "wrong-amount", "wrong-mint", "replay", "expired", "tampered-quote", "garbage", "wrong-recipient", "no-funds"])
    a = ap.parse_args()
    kp = Keypair() if a.fail == "no-funds" else load_kp(); url = f"{a.server}/api/x402/{a.endpoint}?chain={a.chain}&address={a.address}" + ("&fresh=0" if a.fresh == "0" else "")
    print(f"{B}wagmi_tracker x402 agent{X}  {D}(Solana devnet, test money only){X}"); kv("agent wallet", kp.pubkey())

    step(1, f"GET {url}  (no payment)")
    r = requests.get(url, timeout=60)
    kv("status", f"{Y}{r.status_code} Payment Required{X}" if r.status_code == 402 else r.status_code)
    if r.status_code != 402: print(r.text[:500]); return 1
    pr = s.unb64json(r.headers["PAYMENT-REQUIRED"]); req = pr["accepts"][0]
    kv("scheme", f"{req['scheme']} on {req['network']}"); kv("price", f"{int(req['amount']) / 1e6:g} (atomic {req['amount']}) of mint {req['asset']}")
    kv("payTo", req["payTo"]); kv("fee sponsor", req["extra"]["feePayer"]); kv("quote memo", req["extra"]["memo"])
    kv("expires in", f"{req['maxTimeoutSeconds']}s")

    step(2, "Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)")
    bh = devnet_rpc("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"]
    kw = {}
    if a.fail == "wrong-amount": kw["amount"] = int(req["amount"]) // 2; print(f"    {R}demo failure: paying only half the price{X}")
    if a.fail == "wrong-mint": kw["mint"] = s.USDC_DEVNET if req["asset"] != s.USDC_DEVNET else "So11111111111111111111111111111111111111112"; print(f"    {R}demo failure: paying with the wrong token{X}")
    if a.fail == "wrong-recipient": kw["pay_to"] = str(Keypair().pubkey()); print(f"    {R}demo failure: paying someone else instead of payTo{X}")
    if a.fail == "no-funds": print(f"    {R}demo failure: a brand-new empty wallet tries to pay{X}")
    if a.fail == "tampered-quote":
        bad = json.loads(json.dumps(pr)); m = req["extra"]["memo"].split(":"); m[2] = str(int(time.time()) + 86400)
        bad["accepts"][0]["extra"]["memo"] = ":".join(m); pr = bad; print(f"    {R}demo failure: agent edits the quote to extend its expiry{X}")
    if a.fail == "expired":
        wait = int(req["maxTimeoutSeconds"]) + 2; print(f"    {R}demo failure: waiting {wait}s so the quote expires (run the server with X402_TIMEOUT=10 to keep this short){X}"); time.sleep(wait)
    _, hdr = s.payment_header(kp, pr, bh, **kw)
    if a.fail == "garbage": hdr = base64.b64encode(b"{not json").decode(); print(f"    {R}demo failure: malformed payment header{X}")
    kv("blockhash", bh); kv("header", f"PAYMENT-SIGNATURE: {hdr[:48]}… ({len(hdr)} chars)")

    step(3, "Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain")
    t0 = time.time(); r2 = requests.get(url, headers={"PAYMENT-SIGNATURE": hdr}, timeout=180); body = r2.json()
    ok = r2.status_code in (200, 202)
    kv("status", f"{G if ok else R}{r2.status_code}{X}  ({time.time() - t0:.1f}s)")
    if not ok:
        kv("reason", f"{R}{body.get('reason')}{X}"); kv("message", body.get("error")); print(f"    {G}✓ nothing was delivered without a valid payment{X}"); return 0 if a.fail else 1
    rec = s.unb64json(r2.headers["PAYMENT-RESPONSE"])
    kv("tx signature", rec["transaction"]); kv("explorer", f"{G}{s.explorer(rec['transaction'])}{X}"); kv("payer", rec["payer"])

    step(4, "Deliver the resource")
    poll = body.get("poll")
    if poll: kv("poll (free)", poll)
    while poll and body.get("state") != "done":
        print(f"    {D}…{body.get('status')}{X}"); time.sleep(4); body = requests.get(a.server + poll, timeout=30).json()
        if body.get("state") == "error": kv("scan error", body.get("status")); break
    res = body.get("result") or {}
    if res.get("kind") == "wallet" or "verdict" in res:
        kv("verdict", f"{G}{B}{res.get('verdict')}{X}  (confidence {res.get('confidence')})")
        kv("win rate", f"{(res.get('win_rate') or 0) * 100:.0f}% over {res.get('n_tokens')} tokens, PnL {res.get('pnl_sol') or 0:+.2f} SOL")
        for r_ in (res.get("reasons") or [])[:3]: print(f"    {D}• {r_}{X}")
    elif res:
        tok = res.get("token") or {}
        kv("coin", f"{tok.get('name') or res.get('mint')} ({tok.get('symbol', '')})"); kv("early buyers", f"{len(res.get('wallets') or [])} real wallets, {len(res.get('excluded') or [])} snipers/bots filtered")
    kv("full JSON", f"{len(json.dumps(res))} bytes delivered")

    if a.fail == "replay":
        step(5, "Replay the SAME payment header (should be refused)")
        r3 = requests.get(url, headers={"PAYMENT-SIGNATURE": hdr}, timeout=60); b3 = r3.json()
        kv("status", f"{R}{r3.status_code}{X}"); kv("reason", b3.get("reason")); kv("message", b3.get("error"))
    print(f"\n{G}{B}done{X}"); return 0

if __name__ == "__main__": sys.exit(main())
