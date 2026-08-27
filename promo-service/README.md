# Promo Service

Evaluates promo codes for the payment checkout app and returns the discount
to apply. Rules live in an in-process SQLite store seeded at startup; each
rule fetch pays a simulated round trip (`RULE_STORE_RTT_SECONDS`, default
15ms) standing in for a remote rule database.

`POST /evaluate` with `{"code": "..."}` returns
`{"valid": ..., "discount_percent": ..., "rule_count": ...}`.

The `promo-rule-lookup-misconfigured` Unleash flag switches rule loading from
one batched query to one query per rule. It defaults to off, and to off when
Unleash is unreachable.
