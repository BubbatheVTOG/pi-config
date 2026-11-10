---
name: openrouter-pin
description: Pick and pin an OpenRouter endpoint for one model. Fetches every endpoint of a model ID, keeps those that serve zero-data-retention (ZDR) and no-training traffic, ranks them by measured speed and cost, asks the user to choose, then writes the provider block into ~/.pi/agent/models.json. Use when the user asks which OpenRouter provider or endpoint to use, asks for ZDR / no-training / US-region routing, or wants speed and cost compared across OpenRouter providers.
---

# OpenRouter endpoint pin

One model ID goes in, one verified provider block comes out. Never guess a tag,
a price, or a speed: everything below is measured from OpenRouter at run time.

```text
model ID ─ fetch endpoints ─ rank ─ ask user ─ edit models.json ─ verify ─ user reloads
                                  ▲ you stop here until the user confirms
```

## 1. Get the model ID

Use the ID the user gave. If it is fuzzy, run `pi --list-models <term>` and confirm
the exact `author/slug` before fetching. A suffix such as `:free` or `:batch` is not
stripped: each path segment is percent-encoded and passed through, so the endpoint
lookup takes a suffix as typed, while the membership check is an exact match on
`id`/`canonical_slug`. A variant ID that exists in the catalog passes both; an
invented one stops the run at exit 4. Drop the suffix unless you verified it.

## 2. Measure

```bash
scripts/or-endpoints.sh <model-id> --limit 10
```

Probes are the only expensive step, so the script caches: the endpoints payload in
`$XDG_CACHE_HOME/openrouter-pin/<slug>.endpoints.json`, the ZDR membership list in
`members.<query>.json` (12 h), and each verdict in `v.<slug>.<tag>`. `--ttl` sets the
endpoints window (600 s by default) and scales the verdict window to six times it, so
a verdict lives 1 h at the default; an inconclusive attempt is suppressed for 120 s so
a stalled provider is not re-probed on every run. `--refresh` bypasses all four: the
endpoints lookup, the membership check, the verdict cache, and the 120 s suppression.
First run costs one wave of probes, later runs cost milliseconds.

| Flag | Effect |
| --- | --- |
| `--sort speed\|cost\|latency` | ranking metric, default `speed`: `speed` is tok/s p50 highest first, `cost` is input $/M lowest first, `latency` is ms p50 lowest first |
| `--need N` | stop probing once N endpoints are confirmed `ok`; `0` probes every candidate |
| `--max-time S` | per-probe network ceiling (default 6); a stalled endpoint yields `inconclusive(timeout)` instead of gating the run |
| `--refresh` | bypass the endpoints, membership, and verdict caches plus the 120 s suppression |
| `--parallel N` | probes in flight at once, at least 1 (default 12) |
| `--no-probe` | stats only, no verdicts |

Exit codes: `0` table printed, `2` usage error or no key, `3` endpoint lookup failed
or no endpoint survived the filters, `4` the model is outside the ZDR membership set.
A non-zero exit means no data, so no provider block is written.

The script runs a funnel, and the order is deliberate: one stats request for
every endpoint, then free filtering, then probes only for what survives. Probes
are the only per-endpoint cost, so thresholds go *before* them.

```text
membership set (1 call, cached 12h) ─ endpoints.json (1 call, cached 600s)
        │  model not in set? stop now, zero probes
        ▼
region ─ capabilities ─ health ─ slice ─ probe survivors ─ rank
  free      free       free    free         ~0.3-6s each
```

Free filters, in order, then probes:

| Stage | Flags (default) | What it removes |
| --- | --- | --- |
| Membership | `--no-zdr-precheck` to skip; cached 12 h, only `--refresh` refetches | the whole model, when no endpoint can serve ZDR traffic with the required capabilities |
| Region | `--us` | non-US-hosted endpoints |
| Capabilities | `--require-sp tools` (comma list), `--require-sp ''` to disable | endpoints that cannot do tool calls, which pi cannot use at all |
| Health / size | `--min-speed 10` tok/s, `--min-uptime 50` %, `--max-latency`, `--max-in`, `--min-context 0` | dead or unreachable endpoints (0 tok/s, 0% uptime) and ones outside your cost or latency bar |

The funnel line on stderr reports every stage, e.g.
`funnel 50 endpoints -> 6 after region -> 6 after capabilities -> 5 after health -> 5 to probe`.
Pruning never changes the ranking: what survives is still ordered US-first, then by
`--sort`, so the best matches for your criteria stay at the top. A probe that hits
`--max-time` is `inconclusive`, not a verdict.

US hosting is preferred by default: endpoints whose tag carries a region segment
(`wafer/us`, `particle-ai/us/flex`) are ranked ahead of region-neutral ones, and
each group keeps the chosen metric order. Add `--us` to *exclude* region-neutral
endpoints entirely when the user wants US data centers only.

| Column | Source | Meaning |
| --- | --- | --- |
| `data policy` | probe with `{only:[tag], zdr:true, data_collection:"deny", allow_fallbacks:false}` plus `reasoning:{effort:"minimal"}` | `ok` = serves ZDR + no-training; `not ZDR` = the data-policy 404; `inconclusive(...)` = limit, stall, or timeout — never treat as a verdict |
| `tok/s p50` | `throughput_last_30m.p50` | tokens per second over the last 30 min |
| `latency ms p50` | `latency_last_30m.p50` | time to first response |
| `in/out/cache $/M` | `pricing.prompt`, `pricing.completion`, `pricing.input_cache_read` | OpenRouter returns per-token values; the script multiplies by 1e6 |
| `region` | region segment anywhere in the tag (`particle-ai/us/flex` → `us`) | derived: OpenRouter exposes no region field, only the tag |

`endpoints[].zdr` does not exist in the API, and `?zdr=true` on the endpoints route
does not filter. The probe is the only per-endpoint verdict. Model level, `GET
/api/v1/models?zdr=true` lists only models that have at least one ZDR endpoint.

Prefer a `us` endpoint when the user cares where their prompts are processed;
say so in the recommendation line. Read `references/api.md` before writing the provider block.

## 3. Rank, then ask

Pick the top 3 that are `ok`, cheapest-of-plausible first if the user cares about
spend, fastest first if they care about latency. Present the table, then ask:

- `ask_user_question` with one question, 2-4 options, each option labelled with the
  tag plus its p50 tok/s and in/out price so the trade-off is visible.
- Do not edit anything in the same turn as the question. The edit happens only after
  the user answers.

## 4. Write the provider block

`id` is the wire value sent to OpenRouter. Keep it byte-identical to the upstream
slug; a suffix like `(wafer/us)` produces `400: ... is not a valid model ID`. `name`
is the stable alias, not an endpoint label: the endpoint is already recorded in
`openRouterRouting.only`, and the alias has to survive a repoint. Cost values are USD
per million tokens, not per token.

Three names, three jobs, one entry:

| field                      | example value        | what it does                                                          |
| -------------------------- | -------------------- | --------------------------------------------------------------------- |
| `providers.or`             | `or`                 | namespace: the `[or]` badge in the picker, and `or/<slug>` selects it |
| `models[].name`            | `OR-OPTIMAL`         | the alias you type and see; picker search and `--model` both match it |
| `models[].id`              | upstream slug        | sent to the wire verbatim, so it must equal the upstream slug exactly |
| `compat.openRouterRouting` | `only: ["wafer/us"]` | pins the endpoint that slug resolves to                               |

`--model OR-OPTIMAL` resolves the alias directly, because CLI selection matches `name`
case-insensitively. `/model or-optimal` does not: its exact-match test reads `id` only,
so the alias just opens the picker pre-filtered, and `/model or/<slug>` selects at once.
The picker shows `deepseek/deepseek-v4.1-flash-1017 (OR-OPTIMAL) [or]`.

Repointing means rewriting one entry. Sessions restore by provider ID plus model ID: an
endpoint-only repoint (`openRouterRouting.only`) keeps saved sessions, while changing
`models[].id` drops them — resuming warns `Could not restore model <provider>/<id>` and
falls back to another model.

All pins live under `or`, so one grep lists every pin. Each entry carries its own
`openRouterRouting`, which is what pins that model's endpoint; adding a pin means
appending an entry, never a new provider. The live `~/.pi/agent/models.json` is
per-machine (`pi-refresh` lists it as an expected per-machine difference), so pins stay
in that file and are not promoted into the tracked `config/models.json`.

```json
"providers": {
  "or": {
    "api": "openai-completions",
    "apiKey": "$OPENROUTER_API_KEY",
    "baseUrl": "https://openrouter.ai/api/v1",
    "compat": { "sendSessionAffinityHeaders": true },
    "models": [{
      "id": "<author/slug>",
      "name": "<stable alias, e.g. OR-OPTIMAL>",
      "compat": {
        "openRouterRouting": { "only": ["<tag>"], "zdr": true, "data_collection": "deny", "allow_fallbacks": false }
      },
      "contextWindow": <endpoint context_length>,
      "maxTokens": <endpoint max_completion_tokens>,
      "cost": { "input": <in $/M>, "output": <out $/M>, "cacheRead": <cache $/M>, "cacheWrite": 0 },
      "reasoning": true,
      "input": ["text"]
    }]
  }
}
```

`input` describes the model, not the endpoint: it comes from the model catalog entry,
because the endpoint payload carries no modalities. `["text"]` is right only for a
text-only model; add `image` when the catalog says the model takes images.

Rules that decide whether the pin appears and routes:

- **Alias reach is picker + CLI selection, not `--list-models`.** The picker and `--model` both
  fuzzy-match `name` case-insensitively; `--list-models` filters and prints on `provider` + `id`
  only, so an alias is invisible there. Do not put the alias in `id`: it is the wire value,
  and a vanity string there returns `400: "… is not a valid model ID"`.
- **The picker hides an alias that adds no information.** It prints `(name)` only when some
  word of `name` is absent from the id, so an alias made of id words is silently dropped from
  the row. A distinct word like `OPTIMAL` survives.
- **`sendSessionAffinityHeaders` is already true for OpenRouter.** pi detects it from
  `baseUrl` containing `openrouter.ai`, so setting it explicitly is only for tools that read
  `models.json` alone (pi-cache-optimizer does, and warns without it).
- **Credential precedence.** An `auth.json` entry is not required. Pi resolves a key by
  provider ID in this order: `auth.json[<provider-id>]`, then `models.json` `apiKey`
  (`$NAME`/`${NAME}` interpolated from the environment), then the provider's environment
  variables — so the provider block above with `"apiKey": "$OPENROUTER_API_KEY"` and
  `OPENROUTER_API_KEY` in the pi process is enough for the pin to appear. A runtime
  `--api-key` still wins over all three. The trap is precedence: a stored
  `auth.json[<provider-id>]` credential outranks `models.json` `apiKey`, so rotating only
  the environment variable is ignored until the stored entry is updated or removed. To
  add a stored entry without printing the secret:

  ```bash
  tmp=$(mktemp) && chmod 600 "$tmp" \
    && jq '. + {"or": .openrouter}' ~/.pi/agent/auth.json > "$tmp" \
    && mv "$tmp" ~/.pi/agent/auth.json || { rm -f "$tmp"; false; }
  ```

  Guard the copy: `.openrouter` may be absent, and the unguarded form writes
  `"or": null`, which pi rejects as an invalid credential. Use
  `jq -e '.openrouter' ~/.pi/agent/auth.json >/dev/null` first, or
  `jq '. + (if .openrouter then {"or": .openrouter} else . end)'`.
- **No secrets in output.** Never echo a key, and do not copy one into a comment,
  commit, or `AGENTS.md`.

## 5. Verify, then hand off

Run all three; report which passed.

```bash
python3 - <<'PY'
import json, jsonschema
s=json.load(open("/home/bubba/.npm-global/lib/node_modules/@earendil-works/pi-coding-agent/schemas/models.schema.json"))
jsonschema.Draft202012Validator(s).validate(json.load(open("/home/bubba/.pi/agent/models.json")))
print("schema ok")
PY
pi --list-models | rg '<provider-id>'
pi -p --model '<provider-id>/<author/slug>' -t read "Reply with exactly: OK-$(date +%s)"
```

The live print-mode request is what proves routing; `--list-models` only proves
registration. Then tell the user: opening `/model` reloads `models.json`
(pi docs, models.md), so they select with `/model <provider-id>/<author/slug>`;
`/reload` covers extensions, skills, prompts, themes, and context files.
