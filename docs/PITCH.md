# wagmi_tracker

**Your own personal wallet and coin tracker. Anywhere, anytime.**
Live: https://wagmi-tracker.onrender.com · Code: https://github.com/Nwa-Ani/wagmi_tracker · Built by [@heisevo](https://x.com/heisevo)

---

## The problem
Every memecoin and NFT mint has wallets that got in early and made money. Finding them is hard. The first buyers you see are mostly snipers, bundlers and bots, and the "alpha wallets" people share on X are often wallets that got lucky once. Checking a wallet by hand means jumping between explorers, DEX charts and NFT marketplaces on five different chains.

## The solution
Paste a coin, an NFT collection or a wallet. wagmi_tracker does the digging and gives a plain answer.

- **Scan a coin or collection** to see the real early buyers or minters, with snipers, bundles, bots, contracts and mint farms filtered out, plus each wallet's track record.
- **Check a wallet** to get a verdict, **Copy it / Copy-mint it**, **Watch for alpha** or **Skip**, with the reasons, a confidence level and a Degen Score.

No wallet connection, no sign-up. A "Not Financial Advice" gate explains the risks before anyone gets in.

## Chains
Solana · Ethereum · Base · Robinhood Chain (Arbitrum L2) · Bitcoin Ordinals and Runes. Memecoins **and** NFTs on each one where the data allows it.

## Features
| Find | Check | Share and compete |
|---|---|---|
| Early-buyer scan (bots filtered) | Wallet verdict + reasons | 🎁 Wallet Wrapped (swipeable story + PNG) |
| 🚦 Rug Check (traffic light) | 🧪 Copy Simulator ($100 copied → $X) | 🔥 Roast Mode |
| 🕸️ Cabal Detector (shared funders, co-buyers) | 🧻 Paperhands Pain (if you never sold) | ⚔️ Wallet vs Wallet fight |
| 📡 Smart Money Radar | Degen Score 0-1000 + badges | 🏆 Leaderboard |
| ★ Watchlist | 🔔 Telegram alerts (@wagmi_100x_bot) | Share cards for X on every result |

## How it works
- **Python backend** with background scan jobs, a disk cache and rate limiting; **plain HTML/CSS/JS** front end that loads fast on a phone.
- **Data:** Solana RPC / Helius (DAS for NFTs), Etherscan-compatible APIs (Routescan, Blockscout), Alchemy for Base history, a pool of public EVM RPCs (including Robinhood Chain), DexScreener and GeckoTerminal for prices and pools, OpenSea and Magic Eden for NFT floors, mempool.space and ordinals.com for Bitcoin.
- **Filtering:** buys in the launch block, bundled buys, bot-like timing, contracts and mint farms are dropped before anything is ranked.
- **Verdicts** weigh win rate, entry timing, realised and unrealised multiples, and how many trades back them up.
- Works with **no keys at all**. Optional free keys make it faster and deeper.

## What makes it different
1. **Memecoins and NFTs in one tool, across five ecosystems**, including Robinhood Chain and Bitcoin Runes, which most trackers skip.
2. **A verdict, not a spreadsheet.** One answer with reasons a normal person can read.
3. **Built to be shared.** Wrapped, Roast, Wallet vs Wallet and share cards turn a wallet check into something people post.
4. **Safe by design.** It never asks anyone to connect a wallet, and it says clearly that nothing here is financial advice.
5. **Honest about its limits.** Every number is an estimate, and the app tells you when data was thin.

## Roadmap
- **Next:** more chains (Arbitrum One, NEAR, BNB), faster Bitcoin pricing, alerts for whole watchlists.
- **Then:** a public API and a Telegram mini app, saved profiles for wallets you follow, and a weekly "top early wallets" digest.
- **Later:** an AI analyst that explains why a wallet wins, and community-tagged wallets (known cabals, KOLs, dev wallets).

## Links
- Live app: https://wagmi-tracker.onrender.com
- Code: https://github.com/Nwa-Ani/wagmi_tracker
- Telegram alerts: https://t.me/wagmi_100x_bot
- Builder: https://x.com/heisevo

*Not financial advice. On-chain data is public; every result is an estimate.*

---

## Hackathon blurbs

### NEAR hackathon (Nov 1-15)
wagmi_tracker finds the wallets that really get in early on memecoins and NFTs, and tells you in one line whether they're worth copying. It already runs live on Solana, Ethereum, Base, Robinhood Chain and Bitcoin, with bots and snipers filtered out and no wallet connection needed. For NEAR we'll add NEAR as a chain: early-buyer scans for NEAR tokens and NFTs, wallet verdicts and Telegram alerts. That puts NEAR traders in the same cross-chain view as everyone else, in a tool that's built to be shared.

### RYO-CHAN SocialFi (Nov 11)
On-chain trading is social: everyone wants to know who's winning and to show off their own wallet. wagmi_tracker turns any wallet into shareable content. Wallet Wrapped is a swipeable story of your trades, Roast Mode gives you a savage verdict, Wallet vs Wallet is a head-to-head fight with a winner banner, and the Degen Score, badges and Leaderboard add the bragging rights. Every result comes with a share card for X. It's live today across five chains, needs no wallet connection or sign-up, and makes people send it to their friends.

### Arbitrum Online Buildathon (Nov 16-Dec 6)
wagmi_tracker already supports **Robinhood Chain, an Arbitrum L2** (chain ID 4663): early-buyer scans for memecoins and NFTs, wallet verdicts (Copy it / Watch for alpha / Skip), Degen Score and alerts, all from public RPC data. During the buildathon we'll bring the same tools to Arbitrum One and other Orbit chains, so traders can find the smart wallets on any Arbitrum chain from one link. It's live, open source and free to use, and it never asks anyone to connect a wallet.
