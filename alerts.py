"""Optional Telegram alerts. Set TELEGRAM_BOT_TOKEN to turn on.
Users talk to the bot: /watch <wallet> [sol|eth|base|robinhood], /unwatch <wallet>, /list.
A light checker polls only subscribed wallets every ALERT_INTERVAL seconds (default 300) and pings new buys / NFT mints.
Nothing is ever posted to X or any public channel."""
import os, json, time, threading, re
import core
from chains import evm

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API = "https://api.telegram.org/bot"
SUBS = os.path.join(core.CACHE, "alerts.json"); LOCK = threading.Lock()
INTERVAL = int(os.environ.get("ALERT_INTERVAL", 300)); MAX_WALLETS = int(os.environ.get("ALERT_MAX_WALLETS", 50))
SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"); EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
STATE = {"username": None, "error": None}

def tg(method, **params):
    try:
        r = core._sess.post(f"{API}{TOKEN}/{method}", json=params, timeout=40)
        return r.json()
    except Exception as e:
        STATE["error"] = core.redact(str(e)).replace(TOKEN, "***") if TOKEN else str(e); return {}

def load():
    try: return json.load(open(SUBS))
    except Exception: return {"subs": {}, "offset": 0, "last": {}}
def save(d):
    with LOCK:
        try: json.dump(d, open(SUBS, "w"))
        except OSError: pass

def info():
    return {"enabled": bool(TOKEN), "bot": STATE["username"], "interval": INTERVAL,
            "how": "Open the bot on Telegram and send /watch <wallet> <chain>. Chains: sol, eth, base, robinhood."}

def handle(d, msg):
    chat = str(msg["chat"]["id"]); text = (msg.get("text") or "").strip()
    if text.startswith("/start "):  # deep link: /start watch_<wallet>_<chain>
        p = text.split(" ", 1)[1].split("_")
        if len(p) >= 2 and p[0] == "watch": text = f"/watch {p[1]} {p[2] if len(p) > 2 else 'sol'}"
    parts = text.split()
    if not parts: return
    cmd = parts[0].split("@")[0].lower(); subs = d["subs"].setdefault(chat, [])
    if cmd == "/watch" and len(parts) >= 2:
        w = parts[1]; ch = (parts[2] if len(parts) > 2 else ("sol" if SOL_RE.match(w) else "eth")).lower()
        if not (SOL_RE.match(w) and ch == "sol") and not (EVM_RE.match(w) and ch in evm.CHAINS):
            return tg("sendMessage", chat_id=chat, text="That doesn't look right. Use /watch <wallet> <sol|eth|base|robinhood>.")
        total = len({(s["w"], s["c"]) for v in d["subs"].values() for s in v})
        if total >= MAX_WALLETS: return tg("sendMessage", chat_id=chat, text="The alert list is full right now, try again later.")
        if not any(s["w"] == w and s["c"] == ch for s in subs): subs.append({"w": w, "c": ch})
        save(d); tg("sendMessage", chat_id=chat, text=f"Watching {w[:4]}…{w[-4:]} on {ch}. I'll ping you on new buys and mints. Not financial advice.")
    elif cmd == "/unwatch" and len(parts) >= 2:
        d["subs"][chat] = [s for s in subs if s["w"] != parts[1]]; save(d); tg("sendMessage", chat_id=chat, text="Removed.")
    elif cmd == "/list":
        tg("sendMessage", chat_id=chat, text="\n".join(f"{s['w']} ({s['c']})" for s in subs) or "Not watching anything yet.")
    else:
        tg("sendMessage", chat_id=chat, text=f"{core.APP['APP_NAME']} alerts.\n/watch <wallet> <sol|eth|base|robinhood>\n/unwatch <wallet>\n/list\nAlerts are estimates, not financial advice.")

def new_events(w, ch, last):
    """Return (events, new_marker)."""
    ev = []
    if ch == "sol":
        sigs = core.rpc("getSignaturesForAddress", [w, {"limit": 20}], ttl=30) or []
        if not sigs: return [], last
        if last is None: return [], sigs[0]["signature"]
        for s in sigs:
            if s["signature"] == last: break
            if s.get("err"): continue
            t = core._safe_tx(s["signature"])
            if not t: continue
            d, solv, _ = core.tx_deltas(t, w)
            for m, amt in d.items():
                if amt > 0 and solv < -0.005: ev.append(f"bought {m[:4]}…{m[-4:]} for {-solv:.2f} SOL https://dexscreener.com/solana/{m}")
        return ev, sigs[0]["signature"]
    top = evm.latest(ch)
    if last is None: return [], top
    start = max(int(last) + 1, top - int(INTERVAL * 3 / evm.CHAINS[ch]["block_time"]))
    L = evm.logs_forward(ch, None, [evm.T_TRANSFER, None, evm.pad(w)], start, stop=top, want=200)
    for l in L:
        frm = evm.unpad(l["topics"][1])
        if len(l["topics"]) == 4 and frm == evm.ZERO: ev.append(f"minted an NFT from {l['address']} {evm.CHAINS[ch]['explorer']}/tx/{l['hash']}")
        elif len(l["topics"]) == 3 and l["address"] not in evm.CHAINS[ch]["stables"]: ev.append(f"received token {l['address']} {evm.CHAINS[ch]['explorer']}/tx/{l['hash']}")
    return ev[:5], top

def checker():
    while True:
        time.sleep(INTERVAL)
        d = load(); pairs = {}
        for chat, subs in d["subs"].items():
            for s in subs: pairs.setdefault((s["w"], s["c"]), []).append(chat)
        for (w, ch), chats in pairs.items():
            k = f"{ch}:{w}"
            try: ev, mark = new_events(w, ch, d["last"].get(k))
            except Exception: continue
            d["last"][k] = mark
            for e in ev:
                for chat in chats: tg("sendMessage", chat_id=chat, text=f"👀 {w[:4]}…{w[-4:]} ({ch}) {e}\nNot financial advice.", disable_web_page_preview=True)
        save(d)

def poller():
    me = tg("getMe"); STATE["username"] = (me.get("result") or {}).get("username")
    while True:
        d = load(); r = tg("getUpdates", offset=d.get("offset", 0), timeout=30)
        for u in r.get("result", []):
            d["offset"] = u["update_id"] + 1
            if u.get("message"):
                try: handle(d, u["message"])
                except Exception: pass
        save(d)
        if not r: time.sleep(10)

def start():
    if not TOKEN: return False
    threading.Thread(target=poller, daemon=True).start(); threading.Thread(target=checker, daemon=True).start(); return True
