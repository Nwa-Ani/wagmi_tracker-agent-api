#!/usr/bin/env python3
"""One-time DEVNET setup for the x402 demo (no mainnet, no real money).
  python3 x402_setup.py keygen          # create the two burner devnet keypairs in .secrets/ (prints public keys only)
  python3 x402_setup.py status          # balances of the burner wallets (public keys only)
  python3 x402_setup.py ata             # create the server's devnet USDC token account (paid by the agent's devnet SOL)
  python3 x402_setup.py test-token      # fallback: create a devnet SPL TEST token (6 decimals), mint 100 to the agent,
                                        # create both token accounts; prints the mint to use as X402_ASSET
Burner keys live in .secrets/ (gitignored). Secret keys are never printed."""
import json, os, struct, sys, base64
import requests
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solders.hash import Hash
from solders.system_program import create_account, CreateAccountParams
import x402_svm as s

ROOT = os.path.dirname(os.path.abspath(__file__)); SEC = os.path.join(ROOT, ".secrets")
RPC = os.environ.get("DEVNET_RPC", "https://api.devnet.solana.com")
def rpc(m, p):
    r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, timeout=30).json()
    if "error" in r: raise SystemExit(f"RPC error: {r['error']}")
    return r["result"]
def kp(name): return Keypair.from_bytes(bytes(json.load(open(os.path.join(SEC, name + ".json")))))
def ix_create_ata(payer, owner, mint):
    return Instruction(s.ATA_PROGRAM, bytes([1]), [AccountMeta(payer, True, True), AccountMeta(s.ata(owner, mint), False, True),
        AccountMeta(Pubkey.from_string(str(owner)), False, False), AccountMeta(Pubkey.from_string(str(mint)), False, False),
        AccountMeta(s.SYSTEM_PROGRAM, False, False), AccountMeta(s.TOKEN_PROGRAM, False, False)])  # CreateIdempotent
def send(payer, ixs, extra_signers=()):
    bh = rpc("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"]
    msg = MessageV0.try_compile(payer.pubkey(), ixs, [], Hash.from_string(bh))
    tx = VersionedTransaction(msg, [payer, *extra_signers])
    sig = rpc("sendTransaction", [base64.b64encode(bytes(tx)).decode(), {"encoding": "base64"}])
    print("  tx", sig, s.explorer(sig)); return sig
def token_bal(owner, mint):
    r = rpc("getTokenAccountBalance", [str(s.ata(owner, mint))]) if rpc("getAccountInfo", [str(s.ata(owner, mint)), {"encoding": "base64"}])["value"] else None
    return r["value"]["uiAmountString"] if r else "no token account"

def keygen():
    os.makedirs(SEC, mode=0o700, exist_ok=True)
    for name in ("server_payto", "agent_payer"):
        p = os.path.join(SEC, name + ".json")
        if not os.path.exists(p):
            with open(p, "w") as f: json.dump(list(bytes(Keypair())), f)
            os.chmod(p, 0o600)
        print(f"{name:13} {kp(name).pubkey()}")

def main(cmd):
    if cmd == "keygen": return keygen()
    agent, server = kp("agent_payer"), kp("server_payto"); mint = os.environ.get("X402_ASSET", s.USDC_DEVNET)
    if cmd == "status":
        for n, k in (("agent", agent), ("server", server)):
            print(f"{n:7} {k.pubkey()}  SOL {rpc('getBalance', [str(k.pubkey())])['value'] / 1e9:g}  token {mint[:6]}…: {token_bal(k.pubkey(), mint)}")
    elif cmd == "ata":
        send(agent, [ix_create_ata(agent.pubkey(), server.pubkey(), mint), ix_create_ata(agent.pubkey(), agent.pubkey(), mint)])
    elif cmd == "test-token":
        m = Keypair(); json.dump(list(bytes(m)), open(os.path.join(SEC, "test_mint.json"), "w")); os.chmod(os.path.join(SEC, "test_mint.json"), 0o600)
        rent = rpc("getMinimumBalanceForRentExemption", [82])
        init = Instruction(s.TOKEN_PROGRAM, bytes([20, 6]) + bytes(agent.pubkey()) + bytes([0]), [AccountMeta(m.pubkey(), False, True)])  # InitializeMint2
        mint_to = lambda: Instruction(s.TOKEN_PROGRAM, bytes([14]) + struct.pack("<QB", 100_000_000, 6),
            [AccountMeta(m.pubkey(), False, True), AccountMeta(s.ata(agent.pubkey(), m.pubkey()), False, True), AccountMeta(agent.pubkey(), True, False)])
        send(agent, [create_account(CreateAccountParams(from_pubkey=agent.pubkey(), to_pubkey=m.pubkey(), lamports=rent, space=82, owner=s.TOKEN_PROGRAM)), init,
                     ix_create_ata(agent.pubkey(), agent.pubkey(), m.pubkey()), ix_create_ata(agent.pubkey(), server.pubkey(), m.pubkey()), mint_to()], [m])
        print(f"TEST token mint (devnet stand-in for USDC): {m.pubkey()}\n  export X402_ASSET={m.pubkey()}")
    else: print(__doc__)

if __name__ == "__main__": main(sys.argv[1] if len(sys.argv) > 1 else "help")
