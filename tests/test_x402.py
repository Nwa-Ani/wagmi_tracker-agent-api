"""Offline tests for the x402 verification logic (no network, no funds). Run: python3 -m unittest tests.test_x402 -v"""
import base64, json, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("X402_SECRET", "test-secret-only-for-unit-tests")
from solders.keypair import Keypair
from solders.hash import Hash
import x402, x402_svm as s

PAYER, PAYTO, SPONSOR, OTHER = Keypair(), Keypair(), Keypair(), Keypair()
BH = str(Hash.new_unique())
FAKE_MINT = str(Keypair().pubkey())

def cfg():
    c = x402.Cfg({"X402_PAY_TO": str(PAYTO.pubkey()), "X402_FACILITATOR": "payai"}); return c
x402.fee_payer = lambda c=None: str(SPONSOR.pubkey())   # no network in tests
RID = x402.resource_id("wallet-check", "sol", "X", True)

def offer(c, rid=RID, now=None):
    return {"x402Version": 2, "resource": {"url": "http://t/api/x402/wallet-check"}, "accepts": [x402.requirements(c, rid, x402.make_memo(c, rid, now))]}

def header(c, **kw):
    pr = kw.pop("pr", None) or offer(c)
    _, h = s.payment_header(kw.pop("kp", PAYER), pr, BH, **kw); return h

class T(unittest.TestCase):
    def reason(self, h, rid=RID, now=None, c=None):
        with self.assertRaises(x402.PayErr) as e: x402.verify_payload(c or cfg(), h, rid, now)
        return e.exception.reason, e.exception.status

    def test_valid_payment_passes(self):
        ctx = x402.verify_payload(cfg(), header(cfg()), RID)
        self.assertEqual(ctx["payer"], str(PAYER.pubkey())); self.assertEqual(ctx["transfer"]["amount"], 10_000)
    def test_overpay_is_tolerated(self):
        self.assertEqual(x402.verify_payload(cfg(), header(cfg(), amount=20_000), RID)["transfer"]["amount"], 20_000)
    def test_wrong_amount(self): self.assertEqual(self.reason(header(cfg(), amount=9_999)), ("wrong_amount", 402))
    def test_wrong_mint(self): self.assertEqual(self.reason(header(cfg(), mint=FAKE_MINT))[0], "wrong_asset")
    def test_wrong_recipient(self): self.assertEqual(self.reason(header(cfg(), pay_to=str(OTHER.pubkey())))[0], "wrong_recipient")
    def test_memo_tampered(self): self.assertEqual(self.reason(header(cfg(), memo="hello"))[0], "memo_mismatch")
    def test_expired_quote(self):
        c = cfg(); pr = offer(c, now=time.time() - 3600)
        self.assertEqual(self.reason(header(c, pr=pr))[0], "payment_expired")
    def test_quote_for_other_request(self):
        self.assertEqual(self.reason(header(cfg()), rid=x402.resource_id("wallet-check", "sol", "Y", True))[0], "quote_resource_mismatch")
    def test_forged_quote(self):
        c = cfg(); pr = offer(c); m = pr["accepts"][0]["extra"]["memo"].split(":"); m[4] = "0" * 16
        pr["accepts"][0]["extra"]["memo"] = ":".join(m)
        self.assertEqual(self.reason(header(c, pr=pr))[0], "invalid_quote")
    def test_accepted_price_edited(self):
        c = cfg(); pr = offer(c); pr["accepts"][0]["amount"] = "1"
        self.assertEqual(self.reason(header(c, pr=pr, amount=1))[0], "wrong_amount")
    def test_mainnet_refused(self):
        c = cfg(); pr = offer(c); pr["accepts"][0]["network"] = s.MAINNET
        p = json.loads(base64.b64decode(header(c))); p["accepted"]["network"] = s.MAINNET
        self.assertEqual(self.reason(s.b64json(p))[0], "invalid_network")
    def test_bad_signature(self):
        p = json.loads(base64.b64decode(header(cfg()))); raw = bytearray(base64.b64decode(p["payload"]["transaction"]))
        raw[1 + 64 + 5] ^= 0xFF   # flip a byte of the payer's signature
        p["payload"]["transaction"] = base64.b64encode(bytes(raw)).decode()
        self.assertEqual(self.reason(s.b64json(p))[0], "invalid_signature")
    def test_malformed(self):
        self.assertEqual(self.reason("not base64 !!"), ("invalid_payload", 400))
        self.assertEqual(self.reason(s.b64json({"x402Version": 2, "accepted": {}, "payload": {"transaction": "AAAA"}}))[1], 402)
        p = json.loads(base64.b64decode(header(cfg()))); p["payload"]["transaction"] = base64.b64encode(b"junk").decode()
        self.assertEqual(self.reason(s.b64json(p)), ("invalid_transaction", 400))
        self.assertEqual(self.reason(s.b64json({"x402Version": 1}))[0], "invalid_x402_version")

    def test_replay_rejected_and_no_double_charge(self):
        c = cfg(); h = header(c); calls = []
        lg = x402.Ledger(os.path.join(tempfile.mkdtemp(), "l.json"))
        x402.settle = lambda c, ctx: calls.append(1) or "SIG1"
        x402.confirm_onchain = lambda c, sig, ctx, tries=15, gap=2.0: {"slot": 1, "received": 10_000}
        sig, ctx, _, _ = x402.pay(c, h, RID, lg=lg)
        lg.update(ctx["keys"], state="delivered", sig=sig)
        with self.assertRaises(x402.PayErr) as e: x402.pay(c, h, RID, lg=lg)
        self.assertEqual(e.exception.reason, "replayed_payment"); self.assertEqual(len(calls), 1)

    def test_unconfirmed_then_retry_same_payment(self):
        c = cfg(); h = header(c); lg = x402.Ledger(os.path.join(tempfile.mkdtemp(), "l.json")); calls = []
        x402.settle = lambda c, ctx: calls.append(1) or "SIG2"
        def never(c, sig, ctx, tries=15, gap=2.0): raise x402.PayErr("settlement_unconfirmed", "not yet", extra={"transaction": sig})
        x402.confirm_onchain = never
        with self.assertRaises(x402.PayErr) as e: x402.pay(c, h, RID, lg=lg)
        self.assertEqual(e.exception.reason, "settlement_unconfirmed")
        x402.confirm_onchain = lambda c, sig, ctx, tries=15, gap=2.0: {"slot": 2, "received": 10_000}
        sig, *_ = x402.pay(c, h, RID, lg=lg)      # same header again: re-checks the chain, doesn't settle twice
        self.assertEqual((sig, len(calls)), ("SIG2", 1))

    def test_failed_settlement_releases_quote(self):
        c = cfg(); h = header(c); lg = x402.Ledger(os.path.join(tempfile.mkdtemp(), "l.json"))
        def boom(c, ctx): raise x402.PayErr("insufficient_funds", "no funds")
        x402.settle = boom
        with self.assertRaises(x402.PayErr): x402.pay(c, h, RID, lg=lg)
        self.assertEqual(lg.d["used"], {})

    def test_chain_error_mapping(self):
        self.assertEqual(x402._map_chain_err("Simulation failed: BlockhashNotFound")[0], "payment_expired")
        self.assertEqual(x402._map_chain_err('{"InstructionError":[2,{"Custom":1}]}')[0], "insufficient_funds")
        self.assertEqual(x402._map_chain_err("weird 0x10")[0], "settlement_failed")

if __name__ == "__main__": unittest.main()
