# OpenRouter data sources for endpoint selection

Verified against this machine's key on 2026-11-10. Treat numbers as examples, not
constants: re-fetch them.

Keep the token out of argv: write a 600 `curlrc` once and pass `-K "$RC"` to every
request below, as `scripts/or-endpoints.sh` does. `-H "Authorization: Bearer $KEY"`
would expose the key to `ps`.

## 1. Endpoint detail — one request per model

```bash
RC=$(mktemp)
chmod 600 "$RC"
printf 'header = "Authorization: Bearer %s"\n' "$KEY" > "$RC"
curl -s -K "$RC" \
  https://openrouter.ai/api/v1/models/<author>/<slug>/endpoints
```

URL-encode each path segment (`@uri` in jq). A wrong or unlisted slug returns
`{"error":{"code":"Not Found"}}`, not an empty list.

| Field | Shape | Notes |
| --- | --- | --- |
| `tag` | `wafer/us`, `particle-ai/us/flex`, `google-vertex/global` | The value for `openRouterRouting.only[]`. Region and quantization are encoded in the tag, so one provider exposes several; there is no separate region field |
| `provider_name` | display name | Not usable for routing |
| `quantization` | `mxfp4`, `fp8`, `fp4`, `unknown` | Affects quality claims, not routing |
| `throughput_last_30m` | `{p50,p75,p90,p99}` tokens/s | p50 is the honest speed number |
| `latency_last_30m` | `{p50,...}` ms | Time to first response |
| `uptime_last_30m/5m/1d` | percent | 0 on `amazon-bedrock` for claude endpoints at check time |
| `pricing` | strings, **per token** | `prompt`, `completion`, `input_cache_read`, `input_cache_write`, `discount`. Multiply by 1e6 for pi's `cost` block |
| `context_length`, `max_completion_tokens` | ints | e.g. 1048576 / 943718 for `wafer/us`; 943718 is what that endpoint reports, not what a pin must contain — a pin may deliberately advertise a lower `maxTokens` (the live pin uses 262144) |
| `supports_implicit_caching` | bool | If false, expect cache misses and re-billed prompt tokens |

## 2. Data policy per endpoint — probe, do not read

The endpoint payload has no `zdr` field, and `?zdr=true` on the endpoints route is
accepted but does not filter (same tags in and out). OpenRouter applies the policy
at request time instead, so the verdict comes from a tiny live request:

```bash
curl -s -o out.json -w '%{http_code}\n' -K "$RC" \
  -H 'Content-Type: application/json' \
  -d '{"model":"<author/slug>","messages":[{"role":"user","content":"x"}],"max_tokens":1,
       "provider":{"only":["<tag>"],"zdr":true,"data_collection":"deny","allow_fallbacks":false}}' \
  https://openrouter.ai/api/v1/chat/completions
```

| Result | Meaning |
| --- | --- |
| `200` | endpoint serves ZDR + no-training traffic |
| `404` + `No endpoints found matching your data policy (Zero data retention)` | endpoint is excluded by the policy — pin it only if you accept data retention |
| `429` / other upstream error / `--max-time` timeout | inconclusive; the endpoint may still qualify. Retry only a 429 that arrives within ~2 s (a slow 429 is an upstream stall); never record as `not ZDR` |

Checks that produced this table: `wafer/us` → 200; `anthropic`, `azure`,
`google-vertex/global` (model `anthropic/claude-fable-5.2`) → the 404 above.

## 3. Model-level ZDR membership (cheap first pass) — one request for the whole catalogue

```bash
curl -s -K "$RC" 'https://openrouter.ai/api/v1/models?zdr=true' | jq '.data|length'
```

`zdr=true` (the string, not `1`) returned 320 of 429 models; the 109 excluded
include `anthropic/claude-fable-5.2`. Use this to answer "does this model have any
ZDR endpoint" without probing. Other working list params seen: `category=`; unknown
params are ignored rather than rejected, so a typo silently returns everything.

## 4. Cross-check a live cost figure

`usage.cost_details` in a chat response is authoritative for the request that
produced it. For 35 prompt + 8 completion tokens on `wafer/us`:

```text
upstream_inference_prompt_cost      0.00000133   → 0.038 / 1M
upstream_inference_completions_cost 0.000004     → 0.50  / 1M
```

That matches the endpoint `pricing` after the ×1e6 conversion, and it is also how
a wrong unit in `models.json` gets caught: pi divides catalog cost by 1e6, so
per-token values there under-report spend by a factor of 1e6.

## 5. Pi-side rules that break silently

| Rule | Failure if violated |
| --- | --- |
| `models[].id` equals the upstream slug exactly (a suffix in `name` is fine, in `id` is not) | `400: "<id> (wafer/us) is not a valid model ID"` — label belongs in `name` |
| `cost.*` in USD per million tokens | spend shown ~1e6 too low |
| Provider ID has a credential (`auth.json[<id>]`, `apiKey`, or env in the pi process) | model loads but never appears in `--list-models` or `/model` |
| `sendSessionAffinityHeaders` | auto-true when `baseUrl` contains `openrouter.ai`; set it explicitly to silence pi-cache-optimizer |
| Opening `/model` reloads `models.json` | after an edit, select again instead of restarting |
