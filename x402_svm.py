"""Shared x402 v2 'exact' scheme helpers for Solana (SVM).
Used by the server (x402.py), the demo agent (agent_demo.py) and the tests.
Spec: github.com/coinbase/x402 specs/schemes/exact/scheme_exact_svm.md + transports-v2/http.md"""
import base64, json, secrets, struct
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.message import MessageV0, to_bytes_versioned
from solders.transaction import VersionedTransaction
from solders.signature import Signature
from solders.hash import Hash

DEVNET = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"      # CAIP-2 id of Solana devnet
MAINNET = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"      # refused by this code on purpose
USDC_DEVNET = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"  # Circle's devnet USDC
TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ATA_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
COMPUTE_BUDGET = Pubkey.from_string("ComputeBudget111111111111111111111111111111")
MEMO_PROGRAM = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")

def b64json(obj): return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()
def unb64json(s):
    obj = json.loads(base64.b64decode(s.strip(), validate=True))
    if not isinstance(obj, dict): raise ValueError("payload is not a JSON object")
    return obj

def ata(owner, mint, program=TOKEN_PROGRAM):
    owner, mint = Pubkey.from_string(str(owner)), Pubkey.from_string(str(mint))
    return Pubkey.find_program_address([bytes(owner), bytes(program), bytes(mint)], ATA_PROGRAM)[0]

def ix_cu_limit(units): return Instruction(COMPUTE_BUDGET, bytes([2]) + struct.pack("<I", units), [])
def ix_cu_price(micro_lamports): return Instruction(COMPUTE_BUDGET, bytes([3]) + struct.pack("<Q", micro_lamports), [])
def ix_memo(text): return Instruction(MEMO_PROGRAM, text.encode(), [])
def ix_transfer_checked(src, mint, dst, owner, amount, decimals, program=TOKEN_PROGRAM):
    return Instruction(program, bytes([12]) + struct.pack("<QB", int(amount), int(decimals)), [
        AccountMeta(Pubkey.from_string(str(src)), False, True), AccountMeta(Pubkey.from_string(str(mint)), False, False),
        AccountMeta(Pubkey.from_string(str(dst)), False, True), AccountMeta(Pubkey.from_string(str(owner)), True, False)])

def build_payment_tx(payer_kp, req, blockhash, decimals=6, amount=None, mint=None, pay_to=None, memo=None):
    """Client side: the exact-scheme layout (CU limit, CU price, TransferChecked, Memo), fee payer = the
    sponsor named in req.extra.feePayer, signed only by the payer (the sponsor's slot stays empty).
    amount/mint/pay_to/memo overrides exist only so the demo and tests can build deliberately bad payments."""
    mint = mint or req["asset"]; pay_to = pay_to or req["payTo"]
    memo = memo if memo is not None else (req.get("extra", {}).get("memo") or secrets.token_hex(16))
    owner = payer_kp.pubkey(); fee_payer = Pubkey.from_string(req["extra"]["feePayer"])
    ixs = [ix_cu_limit(40_000), ix_cu_price(1),   # ~25.3k used (Memo ~25k for a 66-byte quote); PayAI caps the limit
           ix_transfer_checked(ata(owner, mint), mint, ata(pay_to, mint), owner, amount if amount is not None else int(req["amount"]), decimals),
           ix_memo(memo)]
    msg = MessageV0.try_compile(fee_payer, ixs, [], Hash.from_string(str(blockhash)))
    sigs = [Signature.default()] * msg.header.num_required_signatures
    keys = list(msg.account_keys)
    sigs[keys.index(owner)] = payer_kp.sign_message(to_bytes_versioned(msg))
    return VersionedTransaction.populate(msg, sigs)

def payment_header(payer_kp, payment_required, blockhash, **kw):
    """Pick the Solana devnet 'exact' offer and return (accepted_req, base64 PAYMENT-SIGNATURE header)."""
    req = next(a for a in payment_required["accepts"] if a.get("scheme") == "exact" and a.get("network") == DEVNET)
    tx = build_payment_tx(payer_kp, req, blockhash, **kw)
    payload = {"x402Version": 2, "resource": payment_required.get("resource"), "accepted": req,
               "payload": {"transaction": base64.b64encode(bytes(tx)).decode()}}
    return req, b64json(payload)

def explorer(sig): return f"https://explorer.solana.com/tx/{sig}?cluster=devnet"
