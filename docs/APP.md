# wagmi_tracker

A memecoin **and** NFT tracker. Paste a coin, an NFT collection or a wallet, and see who got in first and whether a wallet is worth following.
Chains: **Solana, Ethereum, Base, Robinhood Chain, Bitcoin (Ordinals / Runes)**. Free, public data. Every number is an estimate. Not financial advice.

Author: @heisevo

## How to use
1. Pick a chain (or just paste: base58 = Solana, `0x…` = EVM on the picked chain, `bc1…` = Bitcoin, rune name / inscription id = Bitcoin) and **Memecoins** or **NFTs**.
2. **Scan a coin / collection** shows the first buyers or minters, with snipers, bundles, bots, contracts and mint farms removed, plus each one's track record.
3. **Check a wallet** gives a verdict: **Copy it / Copy-mint it**, **Watch for alpha** or **Skip**, with reasons, confidence and a **Degen Score (0-1000) + badges**.
4. Under a wallet result: **🎁 Wrapped** (swipeable story + PNG), **🔥 Roast**, **🧪 Copy Simulator** ($100 copied → $X), **🧻 Paperhands Pain** (value if never sold vs what it got), **⚔️ Wallet vs Wallet**, **🔔 Alert me**.
5. Under a coin result: **🚦 Rug Check** (traffic light) and **🕸️ Cabal Detector**.
6. Top menu: **📡 Radar** (recent buys by top wallets already scanned), **🏆 Leaderboard**, **★ Watchlist** (this browser), **🔔 Alerts** (Telegram).
Every result has a share card (PNG for X). Cards carry no creator credit.

## What works per chain
| | Memecoin scan | Memecoin wallet | NFT scan | NFT wallet |
|---|---|---|---|---|
| Solana | pump.fun curve / pool / block scan (Helius or public RPC) | positions, win rate, timing, snipes | Helius DAS (needs `HELIUS_API_KEY`) | DAS holdings + mint origin, Magic Eden floors |
| Ethereum | Routescan (Etherscan-compatible) logs | 30 days of ERC-20 transfers | first mints from the zero address | 90 days of mints, OpenSea floors |
| Base | public RPC pool (thirdweb, Tenderly, drpc, publicnode; 1k-block windows) | 3 days keyless, 30 days with `ALCHEMY_API_KEY` | same | 3 days keyless, 90 days with `ALCHEMY_API_KEY` |
| Robinhood Chain | public RPC logs (30k-block windows) | 2 days, top 12 wallets | same, RPC | 2 days, RPC |
| Bitcoin | rune / inscription facts (ordinals.com) | n/a | n/a | rune mints and etchings decoded from runestones, inscriptions (mempool.space). No free price feed, so outcomes are not priced |

## Data sources (keyless by default)
Solana RPC or Helius, Routescan, Blockscout (Base, used only when it answers), public EVM RPCs (thirdweb, Tenderly, publicnode, drpc, Robinhood Chain RPC), DexScreener, GeckoTerminal, OpenSea, Magic Eden, mempool.space, ordinals.com.

Optional env vars (never committed, `sync:false` in `render.yaml`):
- `HELIUS_API_KEY` faster Solana + Solana NFTs
- `ETHERSCAN_API_KEY` faster Ethereum history. Etherscan's free plan does NOT cover Base (chain 8453); the app detects that and falls back automatically
- `ALCHEMY_API_KEY` optional, free tier: fast full Base (and Ethereum fallback) wallet history via `alchemy_getAssetTransfers` (30 days of trades, 90 days of mints). Without it Base uses the public RPC pool (3 days, slower)

### Base history fallback chain
1. Alchemy (`ALCHEMY_API_KEY`, if set and the key works)
2. Etherscan-compatible explorer API that answers a probe (paid Etherscan key, then keyless Blockscout), re-probed hourly
3. Public RPC pool, `eth_getLogs` over the Transfer topic with the wallet as from/to, 1,000-block windows in parallel

When Base history comes back empty the result says so in its notes, with the source used and whether the RPCs were rate limiting.
- `OPENSEA_API_KEY` NFT floors
- `TELEGRAM_BOT_TOKEN` Telegram alerts (users send `/watch <wallet> <sol|eth|base|robinhood>` to the bot; only subscribed wallets are polled every `ALERT_INTERVAL` seconds, default 300; nothing is posted to X)
- `XAI_API_KEY` optional AI roast (template roasts work without it)
- `ETH_RPC`, `BASE_RPC`, `ROBINHOOD_RPC` custom RPCs

## Run locally
```
pip install -r requirements.txt
python3 server.py         # http://localhost:8787
```

## Deploy on Render (free)
Push the repo, create a Blueprint from `render.yaml`, set any optional keys in the dashboard. The cache lives in `/tmp` (ephemeral). `samples/` ships demo results so the site isn't empty on a cold start.

## Files
- `server.py` HTTP server, job API, routing per chain/asset
- `core.py` Solana coin scans, caching, rate limits
- `wallet_check.py` Solana wallet check + verdict logic
- `chains/evm.py` Ethereum / Base / Robinhood Chain coins + NFTs
- `chains/sol_nft.py` Solana NFTs (Helius DAS)
- `chains/btc.py` Bitcoin Ordinals / Runes
- `extras.py` Paperhands, Rug Check, Cabal Detector, Radar, Leaderboard, AI roast
- `alerts.py` optional Telegram alerts
- `static/` plain HTML/CSS/JS (`features.js` is lazy-loaded)

## Limits (honest)
- Free APIs are rate limited and sampled: only recent history is read, and only the most-traded tokens get price history.
- Copy Simulator and Paperhands use today's price and ignore fees, slippage, gas and copy-bot delay.
- Rug Check: LP lock/burn is only known for pump.fun migrations; holder lists aren't free on EVM chains.
- Cabal Detector: same funder is traced on Solana only, for wallets with short histories; co-buyers only compare against coins already scanned here.
- Radar and Leaderboard use only results already cached on this server. Radar refresh is manual.
- Bitcoin: no free price feed, so no win rate or multiples; "first minters" of a rune need a paid indexer.
- Nothing here is financial advice.
