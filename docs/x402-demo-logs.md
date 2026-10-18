# wagmi_tracker x402 – live devnet demo logs (Oct 18, 2026, WAT)

PayAI facilitator, Solana devnet, 0.01 devnet USDC per call. Secret keys are never printed.

## happy
```
$ python3 agent_demo.py --server http://localhost:8799 --address 862TYSvRYoiHAK3F3WwTRYAfuGiQaGdxedN9AGvRGWo2 --fresh 0
wagmi_tracker x402 agent  (Solana devnet, test money only)
    agent wallet   C6t86bKHdZzXx7tyBdswNXicT82LzpcYSjGjCgTnQYTf

[1] GET http://localhost:8799/api/x402/wallet-check?chain=sol&address=862TYSvRYoiHAK3F3WwTRYAfuGiQaGdxedN9AGvRGWo2&fresh=0  (no payment)
    status         402 Payment Required
    scheme         exact on solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1
    price          0.01 (atomic 10000) of mint 4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU
    payTo          8tJsqvPs45eFEU8Wj6nUiDMe6cpFdHgcYwpQJDN5r1ct
    fee sponsor    2wKupLR9q6wXYppw8Gr2NvWxKBUqm4PPJKkQfoxHDBg4
    quote memo     wagmi402:e51a97b3375a:1792322933:2a01bc0505f5047b:fe4ead078957989f
    expires in     120s

[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    blockhash      QXBoCjeANxbh41BvbdL3aTPdZYuqsvuT36AXxnduzxX
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1884 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         200  (4.1s)
    tx signature   3jSt7AbuYnGSanoSWbZ1QaMDYSqkxpFdwFtp9yc3imUpVd3GgyCS9CHN9febcD1KYmNYMKZYDL3cYoeYYyAwW4C
    explorer       https://explorer.solana.com/tx/3jSt7AbuYnGSanoSWbZ1QaMDYSqkxpFdwFtp9yc3imUpVd3GgyCS9CHN9febcD1KYmNYMKZYDL3cYoeYYyAwW4C?cluster=devnet
    payer          C6t86bKHdZzXx7tyBdswNXicT82LzpcYSjGjCgTnQYTf

[4] Deliver the resource
    verdict        Good for alpha (watch its buys/sells)  (confidence High)
    win rate       100% over 16 tokens, PnL +173.97 SOL
    • Win rate ~100% on 16 tokens, net +173.97 SOL on 242.33 SOL spent.
    • Snipes launches: 100% of buys in the launch block or first 2s.
    • Typical entry 0s after launch/pool (100% within 1h).
    full JSON      14046 bytes delivered

done
```

## fail-replay
```
$ python3 agent_demo.py --server http://localhost:8799 --address 862TYSvRYoiHAK3F3WwTRYAfuGiQaGdxedN9AGvRGWo2 --fresh 0 --fail replay
wagmi_tracker x402 agent  (Solana devnet, test money only)
    agent wallet   C6t86bKHdZzXx7tyBdswNXicT82LzpcYSjGjCgTnQYTf

[1] GET http://localhost:8799/api/x402/wallet-check?chain=sol&address=862TYSvRYoiHAK3F3WwTRYAfuGiQaGdxedN9AGvRGWo2&fresh=0  (no payment)
    status         402 Payment Required
    scheme         exact on solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1
    price          0.01 (atomic 10000) of mint 4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU
    payTo          8tJsqvPs45eFEU8Wj6nUiDMe6cpFdHgcYwpQJDN5r1ct
    fee sponsor    2wKupLR9q6wXYppw8Gr2NvWxKBUqm4PPJKkQfoxHDBg4
    quote memo     wagmi402:e51a97b3375a:1792322939:f40c39c7c6fb17b8:914a0578ce5f3cea
    expires in     120s

[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    blockhash      32QQ6cQcQWNrSrqryNGjnPA99YEELBkHGKWGProTSqco
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1884 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         200  (4.4s)
    tx signature   41rRpJLuYjH4DpaLfXq2VvR814KCw1ouBYScUi1KcnFTxppSvgAEPkoRyC1aBYtzdZAAki9jEmGhpEBrJqFMXAaZ
    explorer       https://explorer.solana.com/tx/41rRpJLuYjH4DpaLfXq2VvR814KCw1ouBYScUi1KcnFTxppSvgAEPkoRyC1aBYtzdZAAki9jEmGhpEBrJqFMXAaZ?cluster=devnet
    payer          C6t86bKHdZzXx7tyBdswNXicT82LzpcYSjGjCgTnQYTf

[4] Deliver the resource
    verdict        Good for alpha (watch its buys/sells)  (confidence High)
    win rate       100% over 16 tokens, PnL +173.97 SOL
    • Win rate ~100% on 16 tokens, net +173.97 SOL on 242.33 SOL spent.
    • Snipes launches: 100% of buys in the launch block or first 2s.
    • Typical entry 0s after launch/pool (100% within 1h).
    full JSON      14046 bytes delivered

[5] Replay the SAME payment header (should be refused)
    status         402
    reason         replayed_payment
    message        This payment was already used. Each x402 payment buys one call. Get a fresh quote.

done
```

## fail-wrong-amount
```
$ python3 agent_demo.py --server http://localhost:8799 --address 862TYSvRYoiHAK3F3WwTRYAfuGiQaGdxedN9AGvRGWo2 --fresh 0 --fail wrong-amount
wagmi_tracker x402 agent  (Solana devnet, test money only)
    agent wallet   C6t86bKHdZzXx7tyBdswNXicT82LzpcYSjGjCgTnQYTf

[1] GET http://localhost:8799/api/x402/wallet-check?chain=sol&address=862TYSvRYoiHAK3F3WwTRYAfuGiQaGdxedN9AGvRGWo2&fresh=0  (no payment)
    status         402 Payment Required
    scheme         exact on solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1
    price          0.01 (atomic 10000) of mint 4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU
    payTo          8tJsqvPs45eFEU8Wj6nUiDMe6cpFdHgcYwpQJDN5r1ct
    fee sponsor    2wKupLR9q6wXYppw8Gr2NvWxKBUqm4PPJKkQfoxHDBg4
    quote memo     wagmi402:e51a97b3375a:1792322878:a1642aeff33b12a0:d0679652e7a93923
    expires in     120s

[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    demo failure: paying only half the price
    blockhash      GoonLs4xQQQfGmqEGeYsfHNfiUPZPBp5nCZYpheYgfUk
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1884 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         402  (0.0s)
    reason         wrong_amount
    message        You paid 5000 atomic units, the price is 10000 (0.01 USDC (devnet)).
    ✓ nothing was delivered without a valid payment
```

## fresh-coin-scan
```
$ python3 agent_demo.py --server http://localhost:8799 --endpoint coin-scan --address D61pTaTqR93axxVvu7AX5TW6c3a4vhffPPMfCnsYpump --fresh 1
wagmi_tracker x402 agent  (Solana devnet, test money only)
    agent wallet   C6t86bKHdZzXx7tyBdswNXicT82LzpcYSjGjCgTnQYTf

[1] GET http://localhost:8799/api/x402/coin-scan?chain=sol&address=D61pTaTqR93axxVvu7AX5TW6c3a4vhffPPMfCnsYpump  (no payment)
    status         402 Payment Required
    scheme         exact on solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1
    price          0.01 (atomic 10000) of mint 4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU
    payTo          8tJsqvPs45eFEU8Wj6nUiDMe6cpFdHgcYwpQJDN5r1ct
    fee sponsor    2wKupLR9q6wXYppw8Gr2NvWxKBUqm4PPJKkQfoxHDBg4
    quote memo     wagmi402:a1fb976e252a:1792322966:8f8dc074fe168910:12015ba0b293da65
    expires in     120s

[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    blockhash      JBofr3ySeY6JAPi9i6umfdUQ7KYDNUW2SNhMPjQAUsNi
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1844 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         202  (24.0s)
    tx signature   2PBXZCi1MpBFaBYaMNnVnkMJ97TjGLnrLkhZqLJLUswHyxtoGxQCYhLNKYiwWVaf1nQfgTu4NY2LEZtr8iueBycR
    explorer       https://explorer.solana.com/tx/2PBXZCi1MpBFaBYaMNnVnkMJ97TjGLnrLkhZqLJLUswHyxtoGxQCYhLNKYiwWVaf1nQfgTu4NY2LEZtr8iueBycR?cluster=devnet
    payer          C6t86bKHdZzXx7tyBdswNXicT82LzpcYSjGjCgTnQYTf

[4] Deliver the resource
    poll (free)    /api/x402/job/59d41e5442b536f51988675ba5ed11d2
    …pumpswap pool (block scan): 47 blocks read, 8 unique buyers
    …pumpswap pool (block scan): 55 blocks read, 8 unique buyers
    …Building track records for 1 wallets…
    …Building track records for 1 wallets…
    …Peak prices (GeckoTerminal, slow): 7/25
    …Peak prices (GeckoTerminal, slow): 7/25
    …Peak prices (GeckoTerminal, slow): 8/25
    …Peak prices (GeckoTerminal, slow): 10/25
    …Peak prices (GeckoTerminal, slow): 12/25
    …Peak prices (GeckoTerminal, slow): 14/25
    …Peak prices (GeckoTerminal, slow): 17/25
    coin           The Owldacity (OWLDACITY)
    early buyers   1 real wallets, 7 snipers/bots filtered
    full JSON      12488 bytes delivered

done
```

## fail-wrong-mint
```
[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    demo failure: paying with the wrong token
    blockhash      GrF5nvUkoFc222mQ1i3gofWLaGQZ9qqmoV9W8WonP96z
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1884 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         402  (0.0s)
    reason         wrong_asset
    message        You paid with mint So11111111111111111111111111111111111111112, but this endpoint takes USDC (devnet) (4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU).
    ✓ nothing was delivered without a valid payment
```

## fail-wrong-recipient
```
[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    demo failure: paying someone else instead of payTo
    blockhash      3G5aa2ogsg4YXWixHiSNd8HhC52sRqjBNUS6oLYoA5BD
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1884 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         402  (0.0s)
    reason         wrong_recipient
    message        The transfer goes to E9xTM38yRL5LU8EE939go9g72Nz7Cg8syu4d27hFxwGT, not to the token account of payTo 8tJsqvPs45eFEU8Wj6nUiDMe6cpFdHgcYwpQJDN5r1ct.
    ✓ nothing was delivered without a valid payment
```

## fail-tampered-quote
```
[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    demo failure: agent edits the quote to extend its expiry
    blockhash      5tbqJeY8x2VPGoWU6kuWTYBCkEcrZiFDPVrXsAvxvqou
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1884 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         402  (0.0s)
    reason         invalid_quote
    message        The quote signature doesn't match (tampered memo, or price/asset/recipient changed). Get a fresh quote.
    ✓ nothing was delivered without a valid payment
```

## fail-expired
```
[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    demo failure: waiting 122s so the quote expires (run the server with X402_TIMEOUT=10 to keep this short)
    blockhash      2Rt38cpnKEYAMsJPy22hRR99JwfpZa7y8VHq1Fyfu4zF
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1884 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         402  (0.0s)
    reason         payment_expired
    message        The quote expired at 11:26:29 UTC. Request again for a fresh 402 and pay within 120s.
    ✓ nothing was delivered without a valid payment
```

## fail-garbage
```
[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    demo failure: malformed payment header
    blockhash      FiTAZwqUDuDaLiLX5QfQr6ebZrPTckAPfRV4EhYWq411
    header         PAYMENT-SIGNATURE: e25vdCBqc29u… (12 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         400  (0.0s)
    reason         invalid_payload
    message        PAYMENT-SIGNATURE must be base64-encoded JSON (an x402 PaymentPayload).
    ✓ nothing was delivered without a valid payment
```

## fail-no-funds
```
[2] Build + sign the payment (TransferChecked + Memo; sponsor pays the network fee)
    demo failure: a brand-new empty wallet tries to pay
    blockhash      DZPpUu3tVGPNpmp1TdGSPSVzNXkRUgSPifXYJ3myGiLN
    header         PAYMENT-SIGNATURE: eyJ4NDAyVmVyc2lvbiI6MiwicmVzb3VyY2UiOnsidXJsIjoi… (1884 chars)

[3] Retry with PAYMENT-SIGNATURE → server verifies, settles on Solana devnet, confirms on-chain
    status         402  (1.3s)
    reason         insufficient_funds
    message        The payer has no token account (or balance) for this mint.
    ✓ nothing was delivered without a valid payment
```
