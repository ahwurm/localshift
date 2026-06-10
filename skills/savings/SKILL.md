---
description: Aggregate the LocalShift run ledger into a receipts table — calls/day moved off frontier, token volume, API-equivalent dollars. Use for status checks and launch-post receipts.
---

# /localshift:savings

Reads `workloads/*/runs/ledger.jsonl` (repo root = `$CLAUDE_PLUGIN_ROOT` if set, else `~/localshift`) and produces the honest receipts. Fail explicitly if no ledger rows exist.

Ledger row shape: `{ts, workload, engine: local|frontier, model_id, tokens_in, tokens_out, cache_read, duration_s, verified}`.

## Procedure

1. Aggregate per workload and total, trading-day aware: calls/day by engine, tokens/day, mean duration.
2. **Dollar figure**: API-equivalent spend of the calls now running local, priced at CURRENT posted frontier rates for the model the workload used (look the rates up via the `claude-api` reference — never hardcode or recall prices). Show the formula inline: `(in×rate_in + cache_read×rate_cache + out×rate_out)/1e6` per day, ×21 trading days/month.
3. **Framing (use this wording)**: "API-equivalent spend at posted rates; from June 15, 2026 these headless calls draw from a metered credit pool." True before and after the billing change.
4. **Degrade honestly**: if frontier token counts are missing/unparsable, report call counts + local-side token volume only and label the dollar figure ESTIMATE with the gap named. Never fabricate a precise number.
5. Output: one markdown table (workload | calls/day moved | tokens/day | $-equiv/month | verified?) + a one-paragraph receipts summary suitable for screenshots.
