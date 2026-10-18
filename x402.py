"""x402 pay-per-call Agent API for wagmi_tracker (x402 v2, scheme 'exact', Solana DEVNET only).

The website stays free and never asks anyone to connect a wallet. This module only serves
/api/x402/* to agents/clients that pay with their own key:
  1. unpaid request            -> 402 + PAYMENT-REQUIRED (devnet USDC, payTo, feePayer, signed quote memo)
  2. client signs a transfer   -> retries with PAYMENT-SIGNATURE (or X-PAYMENT) header
  3. server pre-checks the tx locally (amount, mint, recipient, memo/quote, expiry, replay, signature)
  4. settlement on Solana devnet: PayAI facilitator /verify + /settle (default, sponsors the fee) or
     X402_FACILITATOR=local (this server is the fee payer and submits the tx itself)
  5. server independently confirms the transfer on-chain via RPC, then delivers + PAYMENT-RESPONSE.
Nothing is delivered unless steps 3-5 all pass."""
import base64, hashlib, hmac, json, os, re, secrets, struct, threading, time
import requests
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.message import to_bytes_versioned
from solders.transaction import VersionedTransaction
from x402_svm import (DEVNET, USDC_DEVNET, TOKEN_PROGRAM, TOKEN_2022, COMPUTE_BUDGET, MEMO_PROGRAM, ata, b64json, unb64json, explorer)

ROOT = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.join(ROOT, ".secrets")
PAYAI = "https://facilitator.payai.network"

def _secret_file(name):
    p = os.path.join(SECRETS, name)
    return p if os.path.exists(p) else None

def _load_kp(env, fname):
    raw = os.environ.get(env, "").strip()
    try:
        if raw: return Keypair.from_bytes(bytes(json.loads(raw))) if raw.startswith("[") else Keypair.from_base58_string(raw)
        f = _secret_file(fname)
        if f: return Keypair.from_bytes(bytes(json.load(open(f))))
    except Exception: pass
    return None

def _hmac_key():
    if os.environ.get("X402_SECRET"): return os.environ["X402_SECRET"].encode()
    f = os.path.join(SECRETS, "x402_hmac")
    try:
        if not os.path.exists(f):
            os.makedirs(SECRETS, mode=0o700, exist_ok=True)
            with open(f, "w") as fh: fh.write(secrets.token_hex(32))
            os.chmod(f, 0o600)
        return open(f).read().strip().encode()
    except OSError:
        return secrets.token_bytes(32)  # ephemeral: quotes die with the process, which is safe

class Cfg:
    def __init__(self, env=None):
        e = os.environ if env is None else env
        self.mode = (e.get("X402_FACILITATOR") or "payai").strip().lower()   # "payai" | "local" | any facilitator URL
        self.facilitator = PAYAI if self.mode == "payai" else (self.mode.rstrip("/") if self.mode.startswith("http") else None)
        self.server_kp = _load_kp("X402_FEEPAYER_SECRET", "server_payto.json") if self.mode == "local" else None
        pay_to = e.get("X402_PAY_TO", "").strip()
        if not pay_to:
            kp = self.server_kp or _load_kp("X402_FEEPAYER_SECRET", "server_payto.json")
            pay_to = str(kp.pubkey()) if kp else ""
        self.pay_to = pay_to
        self.asset = (e.get("X402_ASSET") or USDC_DEVNET).strip()
        self.asset_name = e.get("X402_ASSET_NAME") or ("USDC (devnet)" if self.asset == USDC_DEVNET else "TEST token (devnet stand-in for USDC)")
        self.decimals = int(e.get("X402_DECIMALS") or 6)
        self.price = int(e.get("X402_PRICE") or 10_000)            # atomic units: 10_000 = 0.01 with 6 decimals
        self.timeout = int(e.get("X402_TIMEOUT") or 120)           # quote lifetime (seconds)
        self.wait = float(e.get("X402_WAIT") or 20)                # how long a paid call waits for the scan before 202
        hk = os.environ.get("HELIUS_API_KEY", "").strip()
        self.rpc = e.get("DEVNET_RPC") or (f"https://devnet.helius-rpc.com/?api-key={hk}" if hk else "https://api.devnet.solana.com")
        self.enabled = bool(self.pay_to) and (self.facilitator or self.server_kp) is not None
CFG = Cfg()

# ---------------------------------------------------------------- devnet RPC (key never logged)
def _scrub(s):
    s = str(s); hk = os.environ.get("HELIUS_API_KEY", "").strip()
    return s.replace(hk, "***") if hk else s

def rpc(method, params, cfg=None):
    cfg = cfg or CFG
    try:
        r = requests.post(cfg.rpc, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=20).json()
    except Exception as ex:
        raise RuntimeError(_scrub(ex)) from None
    if "error" in r: raise RuntimeError(_scrub(r["error"]))
    return r.get("result")

# ---------------------------------------------------------------- fee payer (sponsor)
_FP = {"t": 0, "v": None}
def fee_payer(cfg=None):
    cfg = cfg or CFG
    if cfg.server_kp: return str(cfg.server_kp.pubkey())
    if time.time() - _FP["t"] < 600 and _FP["v"]: return _FP["v"]
    kinds = requests.get(cfg.facilitator + "/supported", timeout=15).json().get("kinds", [])
    k = next(k for k in kinds if k.get("network") == DEVNET and k.get("x402Version") == 2 and k.get("scheme") == "exact")
    _FP.update(t=time.time(), v=k["extra"]["feePayer"]); return _FP["v"]

# ---------------------------------------------------------------- quotes: stateless, HMAC-signed, bound to one request
def resource_id(endpoint, chain, address, fresh):
    return hashlib.sha256(f"{endpoint}|{chain}|{address}|{int(bool(fresh))}".encode()).hexdigest()[:12]

def _mac(cfg, rid, exp, nonce):
    m = f"{rid}|{exp}|{nonce}|{cfg.price}|{cfg.asset}|{cfg.pay_to}|{cfg.decimals}"
    return hmac.new(_hmac_key(), m.encode(), hashlib.sha256).hexdigest()[:16]

def make_memo(cfg, rid, now=None):
    exp = int((now or time.time()) + cfg.timeout); nonce = secrets.token_hex(8)
    return f"wagmi402:{rid}:{exp}:{nonce}:{_mac(cfg, rid, exp, nonce)}"

def check_memo(cfg, memo, rid, now=None):
    """-> None if fine, else (reason, message)."""
    try:
        tag, mrid, exp, nonce, mac = str(memo).split(":")
        exp = int(exp); assert tag == "wagmi402"
    except Exception:
        return ("invalid_quote", "The payment memo is not a quote issued by this server. Request the resource without payment to get a fresh quote.")
    if not hmac.compare_digest(mac, _mac(cfg, mrid, exp, nonce)):
        return ("invalid_quote", "The quote signature doesn't match (tampered memo, or price/asset/recipient changed). Get a fresh quote.")
    if mrid != rid:
        return ("quote_resource_mismatch", "This payment was quoted for a different request (endpoint, chain, address or fresh flag). Pay for the exact request.")
    if (now or time.time()) > exp:
        return ("payment_expired", f"The quote expired at {time.strftime('%H:%M:%S', time.gmtime(exp))} UTC. Request again for a fresh 402 and pay within {cfg.timeout}s.")
    return None

def requirements(cfg, rid, memo=None):
    return {"scheme": "exact", "network": DEVNET, "amount": str(cfg.price), "asset": cfg.asset, "payTo": cfg.pay_to,
            "maxTimeoutSeconds": cfg.timeout, "extra": {"feePayer": fee_payer(cfg), "memo": memo or make_memo(cfg, rid)}}

# ---------------------------------------------------------------- replay ledger (persisted, per quote memo + per tx message)
class Ledger:
    def __init__(self, path):
        self.path = path; self.lock = threading.Lock()
        try: self.d = json.load(open(path))
        except Exception: self.d = {"used": {}, "paid": []}
    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f: json.dump(self.d, f)
            os.replace(tmp, self.path)
        except OSError: pass
    def reserve(self, keys):
        """Atomically claim the quote + tx. Returns the existing record if any key was already used."""
        with self.lock:
            for k in keys:
                if k in self.d["used"]: return self.d["used"][k]
            rec = {"state": "reserved", "t": time.time()}
            for k in keys: self.d["used"][k] = rec
            self.save(); return None
    def update(self, keys, **kw):
        with self.lock:
            for k in keys: self.d["used"].setdefault(k, {}).update(kw)
            self.save()
    def release(self, keys):
        with self.lock:
            for k in keys: self.d["used"].pop(k, None)
            self.save()
    def add_paid(self, row):
        with self.lock:
            self.d["paid"] = ([row] + self.d["paid"])[:200]; self.save()

# ---------------------------------------------------------------- local verification of the payment payload
class PayErr(Exception):
    def __init__(self, reason, message, status=402, extra=None):
        super().__init__(message); self.reason, self.message, self.status, self.extra = reason, message, status, extra or {}

def _u8(b, i): return b[i] if len(b) > i else None

def verify_payload(cfg, header, rid, now=None):
    """Checks everything that can be checked without the chain. Raises PayErr. Returns a ctx dict."""
    try:
        p = unb64json(header)
    except Exception:
        raise PayErr("invalid_payload", "PAYMENT-SIGNATURE must be base64-encoded JSON (an x402 PaymentPayload).", 400)
    if p.get("x402Version") != 2:
        raise PayErr("invalid_x402_version", "Only x402Version 2 is supported.", 400)
    acc = p.get("accepted"); tx_b64 = (p.get("payload") or {}).get("transaction") if isinstance(p.get("payload"), dict) else None
    if not isinstance(acc, dict) or not isinstance(tx_b64, str):
        raise PayErr("invalid_payload", "Payload needs 'accepted' (the offer you chose) and 'payload.transaction' (base64 Solana tx).", 400)
    if acc.get("scheme") != "exact": raise PayErr("unsupported_scheme", "Only the 'exact' scheme is accepted.")
    if acc.get("network") != DEVNET: raise PayErr("invalid_network", f"Only Solana devnet ({DEVNET}) is accepted. No mainnet, no real money.")
    memo = (acc.get("extra") or {}).get("memo")
    bad = check_memo(cfg, memo, rid, now)
    if bad: raise PayErr(*bad)
    want = requirements(cfg, rid, memo)
    for f, label in (("asset", "wrong_asset"), ("payTo", "wrong_recipient"), ("amount", "wrong_amount")):
        if str(acc.get(f)) != str(want[f]):
            raise PayErr(label, f"accepted.{f} is {acc.get(f)!r} but this server asks for {want[f]!r}.")
    if (acc.get("extra") or {}).get("feePayer") != want["extra"]["feePayer"]:
        raise PayErr("fee_payer_mismatch", "accepted.extra.feePayer doesn't match the sponsor this server uses.")
    try:
        tx = VersionedTransaction.from_bytes(base64.b64decode(tx_b64, validate=True)); msg = tx.message
        keys = [str(k) for k in msg.account_keys]
    except Exception:
        raise PayErr("invalid_transaction", "payload.transaction isn't a valid serialized Solana transaction.", 400)
    if getattr(msg, "address_table_lookups", None):
        raise PayErr("invalid_transaction", "Address lookup tables aren't accepted on this endpoint.")
    fp = want["extra"]["feePayer"]
    if keys[0] != fp: raise PayErr("fee_payer_mismatch", "The transaction's fee payer must be accepted.extra.feePayer.")
    if msg.header.num_required_signatures != 2:
        raise PayErr("invalid_transaction", "The transaction must need exactly two signatures: the sponsor (fee payer) and you.")
    dest_ok = {str(ata(cfg.pay_to, cfg.asset, TOKEN_PROGRAM)), str(ata(cfg.pay_to, cfg.asset, TOKEN_2022))}
    transfers, memos, cu = [], [], {}
    for ix in msg.instructions:
        prog = keys[ix.program_id_index]; acct = [keys[i] for i in ix.accounts]; data = bytes(ix.data)
        if fp in acct: raise PayErr("fee_payer_not_isolated", "The sponsor/fee payer may not appear in any instruction.")
        if prog == str(COMPUTE_BUDGET):
            if _u8(data, 0) == 2 and len(data) == 5: cu["limit"] = struct.unpack("<I", data[1:])[0]
            elif _u8(data, 0) == 3 and len(data) == 9: cu["price"] = struct.unpack("<Q", data[1:])[0]
            else: raise PayErr("invalid_transaction", "Only SetComputeUnitLimit/SetComputeUnitPrice compute-budget instructions are allowed.")
        elif prog in (str(TOKEN_PROGRAM), str(TOKEN_2022)):
            if _u8(data, 0) != 12 or len(data) != 10 or len(acct) < 4:
                raise PayErr("invalid_transaction", "Only one SPL TransferChecked instruction is allowed.")
            amount, dec = struct.unpack("<QB", data[1:])
            transfers.append({"src": acct[0], "mint": acct[1], "dst": acct[2], "owner": acct[3], "amount": amount, "decimals": dec, "program": prog})
        elif prog == str(MEMO_PROGRAM):
            memos.append(data)
        else:
            raise PayErr("invalid_transaction", f"Unexpected program {prog} in the payment transaction.")
    if cu.get("limit", 0) > 400_000 or cu.get("price", 0) > 50_000:
        raise PayErr("invalid_transaction", "Compute budget too high (max 400k CU, 50k micro-lamports/CU).")
    if len(transfers) != 1:
        raise PayErr("invalid_transaction", f"Expected exactly one TransferChecked, found {len(transfers)}.")
    t = transfers[0]
    if t["mint"] != cfg.asset: raise PayErr("wrong_asset", f"You paid with mint {t['mint']}, but this endpoint takes {cfg.asset_name} ({cfg.asset}).")
    if t["dst"] not in dest_ok: raise PayErr("wrong_recipient", f"The transfer goes to {t['dst']}, not to the token account of payTo {cfg.pay_to}.")
    if t["decimals"] != cfg.decimals: raise PayErr("wrong_amount", f"TransferChecked decimals must be {cfg.decimals}.")
    if t["amount"] < cfg.price:
        raise PayErr("wrong_amount", f"You paid {t['amount']} atomic units, the price is {cfg.price} ({cfg.price / 10 ** cfg.decimals:g} {cfg.asset_name}).")
    if t["owner"] == fp: raise PayErr("fee_payer_not_isolated", "The sponsor can't be the transfer authority.")
    if len(memos) != 1 or memos[0] != str(memo).encode():
        raise PayErr("memo_mismatch", "The transaction needs exactly one Memo instruction equal to accepted.extra.memo.")
    mbytes = to_bytes_versioned(msg); i = keys.index(t["owner"])
    if i >= msg.header.num_required_signatures or not tx.signatures[i].verify(msg.account_keys[i], mbytes):
        raise PayErr("invalid_signature", "The payer's signature on the transaction is missing or invalid.")
    return {"payload": p, "req": want, "tx": tx, "transfer": t, "payer": t["owner"], "memo": memo,
            "keys": ["memo:" + str(memo), "msg:" + hashlib.sha256(mbytes).hexdigest()]}

# ---------------------------------------------------------------- settlement + independent on-chain confirmation
def _map_chain_err(msg):
    m = str(msg)
    if "BlockhashNotFound" in m or "blockhash" in m.lower(): return "payment_expired", "The transaction's blockhash expired before settlement. Get a fresh quote and pay again."
    if "insufficient" in m.lower() or re.search(r'"Custom"\s*:\s*1\b|error: 0x1\b', m): return "insufficient_funds", "The payer's token account doesn't have enough balance."
    if "InvalidAccountData" in m or "AccountNotFound" in m: return "insufficient_funds", "The payer has no token account (or balance) for this mint."
    return "settlement_failed", m[:300]

def settle(cfg, ctx):
    """Returns the on-chain tx signature or raises PayErr. Funds move only here."""
    body = {"x402Version": 2, "paymentPayload": ctx["payload"], "paymentRequirements": ctx["req"]}
    if cfg.facilitator:
        v = requests.post(cfg.facilitator + "/verify", json=body, timeout=30).json()
        if not v.get("isValid"):
            raw = v.get("invalidMessage") or v.get("invalidReason") or "rejected"; r, m = _map_chain_err(raw)
            raise PayErr(r if r != "settlement_failed" else (v.get("invalidReason") or r), m if r != "settlement_failed" else raw,
                         extra={"facilitator_reason": v.get("invalidReason"), "facilitator_message": str(raw)[:300]})
        for attempt in range(6):
            s = requests.post(cfg.facilitator + "/settle", json=body, timeout=60).json()
            if s.get("success") and s.get("transaction"): return s["transaction"]
            if s.get("errorReason") == "settlement_pending":
                time.sleep(3); continue
            raw = s.get("errorMessage") or s.get("errorReason") or "rejected"; r, m = _map_chain_err(raw)
            raise PayErr(r if r != "settlement_failed" else (s.get("errorReason") or r), m if r != "settlement_failed" else raw,
                         extra={"facilitator_reason": s.get("errorReason"), "facilitator_message": str(raw)[:300], "transaction": s.get("transaction") or None})
        raise PayErr("settlement_unconfirmed", "The facilitator is still settling. Retry the same request with the same payment header in a few seconds.", extra={"retry_same_payment": True})
    # local sponsor: co-sign as fee payer, simulate, submit
    tx, kp = ctx["tx"], cfg.server_kp
    sigs = list(tx.signatures); sigs[0] = kp.sign_message(to_bytes_versioned(tx.message))
    full = VersionedTransaction.populate(tx.message, sigs); raw = base64.b64encode(bytes(full)).decode()
    sim = rpc("simulateTransaction", [raw, {"encoding": "base64", "sigVerify": True, "commitment": "confirmed"}], cfg)
    if (sim or {}).get("value", {}).get("err"):
        raise PayErr(*_map_chain_err(json.dumps(sim["value"]["err"]) + " " + " ".join(sim["value"].get("logs") or [])[-300:]))
    try: return rpc("sendTransaction", [raw, {"encoding": "base64", "preflightCommitment": "confirmed"}], cfg)
    except RuntimeError as ex: raise PayErr(*_map_chain_err(ex))

def confirm_onchain(cfg, sig, ctx, tries=15, gap=2.0):
    """Don't trust anyone: read the confirmed tx from Solana and check the payTo token account really got paid."""
    dst = ctx["transfer"]["dst"]
    for _ in range(tries):
        try:
            tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}], cfg)
        except RuntimeError: tx = None
        if tx:
            meta = tx.get("meta") or {}
            if meta.get("err"): raise PayErr("settlement_failed", f"The payment transaction failed on-chain: {meta['err']}", extra={"transaction": sig})
            keys = [k["pubkey"] if isinstance(k, dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
            def bal(rows):
                for b in rows or []:
                    if keys[b["accountIndex"]] == dst and b["mint"] == cfg.asset: return int(b["uiTokenAmount"]["amount"])
                return 0
            delta = bal(meta.get("postTokenBalances")) - bal(meta.get("preTokenBalances"))
            if delta < cfg.price:
                raise PayErr("wrong_amount", f"On-chain the recipient only received {delta} units.", extra={"transaction": sig})
            return {"slot": tx.get("slot"), "received": delta}
        time.sleep(gap)
    raise PayErr("settlement_unconfirmed", "Payment was submitted but isn't confirmed on devnet yet. Retry the same request with the same payment header; you won't be charged twice.",
                 extra={"transaction": sig, "explorer": explorer(sig), "retry_same_payment": True})

LEDGER = None
def ledger():
    global LEDGER
    if LEDGER is None:
        import core
        LEDGER = Ledger(os.path.join(core.CACHE, "x402_ledger.json"))
    return LEDGER

def pay(cfg, header, rid, now=None, lg=None):
    """Full gate. Returns (sig, ctx, onchain, prior). prior is set when this exact payment was already delivered."""
    lg = lg or ledger()
    ctx = verify_payload(cfg, header, rid, now)
    prior = lg.reserve(ctx["keys"])
    if prior:
        if prior.get("state") == "delivered":
            raise PayErr("replayed_payment", "This payment was already used. Each x402 payment buys one call. Get a fresh quote.",
                         extra={"transaction": prior.get("sig"), "job": prior.get("job")})
        if prior.get("state") == "pending" and prior.get("sig"):
            oc = confirm_onchain(cfg, prior["sig"], ctx, tries=3)   # retry of an unconfirmed payment: re-check, don't re-charge
            return prior["sig"], ctx, oc, None
        raise PayErr("payment_in_progress", "This payment is already being processed. Retry in a few seconds.", 409)
    try:
        sig = settle(cfg, ctx)
    except PayErr as e:
        if e.reason in ("settlement_unconfirmed",) or e.extra.get("transaction"):
            lg.update(ctx["keys"], state="pending", sig=e.extra.get("transaction"))
        else:
            lg.release(ctx["keys"])   # nothing moved, so the same quote may be paid properly
        raise
    except Exception as ex:
        lg.update(ctx["keys"], state="pending")
        raise PayErr("settlement_error", "Settlement service error: " + _scrub(ex)[:200], 502)
    lg.update(ctx["keys"], state="pending", sig=sig)
    oc = confirm_onchain(cfg, sig, ctx)
    return sig, ctx, oc, None

# ---------------------------------------------------------------- HTTP layer (called from server.py)
ENDPOINTS = {
    "wallet-check": {"kind": "wallet", "description": "Deep, fresh wallet check: verdict (copy / watch / skip), win rate, PnL, early entries, paperhands."},
    "coin-scan": {"kind": "token", "description": "Deep, fresh coin scan: first real buyers (snipers/bots filtered), each scored."},
}
PAID_JOBS = {}   # access token -> {jid, params}; token is only ever returned to the payer

def _headers_for(obj, name="PAYMENT-REQUIRED"):
    return {name: b64json(obj), "Access-Control-Expose-Headers": "PAYMENT-REQUIRED, PAYMENT-RESPONSE, X-PAYMENT-RESPONSE"}

def catalog(base):
    cfg = CFG
    return {"x402Version": 2, "enabled": cfg.enabled, "network": DEVNET, "asset": cfg.asset, "assetName": cfg.asset_name,
            "price": str(cfg.price), "priceDisplay": f"{cfg.price / 10 ** cfg.decimals:g}", "decimals": cfg.decimals, "payTo": cfg.pay_to,
            "settlement": "PayAI facilitator (fee sponsored)" if cfg.facilitator == PAYAI else ("facilitator " + str(cfg.facilitator) if cfg.facilitator else "self-sponsored (this server pays the fee)"),
            "resources": [{"url": f"{base}/api/x402/{k}?chain=sol&address=<addr>", "method": "GET", **v} for k, v in ENDPOINTS.items()],
            "notes": "Devnet only. The website is free and never asks for a wallet; this API is for agents paying with their own key."}

def recent(limit=20):
    return [{k: r.get(k) for k in ("t", "endpoint", "chain", "address", "amount", "asset", "payer", "tx", "explorer")} for r in ledger().d["paid"][:limit]]

def handle(h, srv, path, q):
    """h: the request handler (has .headers, ._send), srv: the server module (validate, start_job, JOBS, CHAINS, evm)."""
    cfg = CFG; base = ("https://" if h.headers.get("X-Forwarded-Proto") == "https" else "http://") + (h.headers.get("Host") or "localhost")
    if path in ("/api/x402", "/api/x402/"): return h._send(200, catalog(base))
    if path == "/api/x402/recent": return h._send(200, {"paid": recent()})
    if path.startswith("/api/x402/job/"):
        tok = path.rsplit("/", 1)[1]; pj = PAID_JOBS.get(tok)
        if not pj: return h._send(404, {"error": "Unknown job token."})
        j = srv.JOBS.get(pj["jid"]) or {}
        if j.get("state") == "error" and q.get("retry") == "1" and not pj.get("retried"):
            pj["retried"] = True; pj["jid"] = srv.start_job(*pj["params"], fresh=True)   # one free re-run if a paid scan failed
            j = srv.JOBS[pj["jid"]]
        return h._send(200, {"state": j.get("state"), "status": j.get("status"), "result": j.get("result") if j.get("state") == "done" else None,
                             "receipt": pj["receipt"], **({"hint": "The scan failed after payment. Call again with ?retry=1 for one free re-run."} if j.get("state") == "error" and not pj.get("retried") else {})})
    name = path[len("/api/x402/"):]
    if name not in ENDPOINTS: return h._send(404, {"error": "Unknown x402 resource. GET /api/x402 lists them."})
    if not cfg.enabled: return h._send(503, {"error": "The x402 agent API isn't configured on this server (X402_PAY_TO / facilitator)."})
    chain = (q.get("chain") or "sol").lower(); a = (q.get("address") or q.get("addr") or "").strip(); fresh = q.get("fresh", "1") != "0"
    kind = ENDPOINTS[name]["kind"]; asset = "nft" if chain == "btc" else (q.get("asset") or "coin")
    if chain in srv.evm.CHAINS: a = a.lower()
    if chain not in srv.CHAINS or asset not in ("coin", "nft") or not srv.validate(chain, asset, kind, a):
        return h._send(400, {"error": "Bad chain/address. Nothing was charged.", "chains": srv.CHAINS})   # never charge for invalid input
    rid = resource_id(name, chain, a, fresh)
    resource = {"url": f"{base}/api/x402/{name}?chain={chain}&address={a}" + ("" if fresh else "&fresh=0"),
                "description": ENDPOINTS[name]["description"], "mimeType": "application/json"}
    hdr = h.headers.get("PAYMENT-SIGNATURE") or h.headers.get("X-PAYMENT")
    def need_payment(reason, message, status=402, extra=None):
        try: req = requirements(cfg, rid)
        except Exception as ex: return h._send(503, {"error": "Payment sponsor unavailable: " + _scrub(ex)[:160]})
        pr = {"x402Version": 2, "error": message, "resource": resource, "accepts": [req]}
        body = {**pr, "reason": reason, **(extra or {})}
        hd = _headers_for(pr)
        if extra and extra.get("transaction"):
            hd.update(_headers_for({"success": False, "errorReason": reason, "transaction": extra["transaction"], "network": DEVNET}, "PAYMENT-RESPONSE"))
        return h._send(status, body, hd)
    if not hdr:
        return need_payment("payment_required", f"Pay {cfg.price / 10 ** cfg.decimals:g} {cfg.asset_name} on Solana devnet to run this call. Send the signed payment in the PAYMENT-SIGNATURE header.")
    try:
        sig, ctx, oc, _ = pay(cfg, hdr, rid)
    except PayErr as e:
        if e.status == 400: return h._send(400, {"x402Version": 2, "reason": e.reason, "error": e.message})
        return need_payment(e.reason, e.message, e.status, e.extra)
    receipt = {"success": True, "transaction": sig, "network": DEVNET, "payer": ctx["payer"], "explorer": explorer(sig), "slot": oc.get("slot"), "amount": str(oc.get("received"))}
    jid = srv.start_job(chain, asset, kind, a, fresh=fresh); tok = secrets.token_hex(16)
    PAID_JOBS[tok] = {"jid": jid, "params": (chain, asset, kind, a), "receipt": receipt}
    ledger().update(ctx["keys"], state="delivered", sig=sig, job=f"/api/x402/job/{tok}")
    ledger().add_paid({"t": int(time.time()), "endpoint": name, "chain": chain, "address": a, "amount": str(oc.get("received")), "asset": cfg.asset,
                       "payer": ctx["payer"], "tx": sig, "explorer": explorer(sig)})
    t0 = time.time()
    while time.time() - t0 < cfg.wait and srv.JOBS[jid]["state"] == "running": time.sleep(0.5)
    j = srv.JOBS[jid]; hd = _headers_for(receipt, "PAYMENT-RESPONSE"); hd["X-PAYMENT-RESPONSE"] = hd["PAYMENT-RESPONSE"]
    if j["state"] == "done": return h._send(200, {"paid": True, "receipt": receipt, "result": j["result"]}, hd)
    return h._send(202, {"paid": True, "receipt": receipt, "state": j["state"], "status": j.get("status"),
                         "poll": f"/api/x402/job/{tok}", "hint": "Paid. The fresh scan is still running; poll this URL (free) until state is done."}, hd)
