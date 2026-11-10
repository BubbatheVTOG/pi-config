#!/usr/bin/env bash
# Rank OpenRouter endpoints for one model by data policy, region, speed, and cost.
# Usage: or-endpoints.sh <model-id> [options]; -h lists every flag.
#
# Values come from OpenRouter: endpoint tags, p50 throughput (tokens/s) and
# latency (ms) over the last 30 minutes, uptime, and unit pricing scaled to USD
# per million tokens. The data-policy verdict comes from a live probe, because the
# endpoints payload carries no retention field.
#
# Cost model: the endpoints lookup is one request and is cached; each probe is a
# full chat round trip, so probes are cached per endpoint and stop once --need
# eligible endpoints have been confirmed.
set -euo pipefail

API=https://openrouter.ai/api/v1
MODEL="" LIMIT=12 SORT=speed PROBE=1 US=0 PARALLEL=12 NEED=5 TTL=600 MAXT=6
MIN_SPEED=10 MIN_UPTIME=50 MAX_IN=999 MAX_LATENCY=99999
MIN_CONTEXT=0 SP_REQ=tools ZDR_PRECHECK=1 MEM_TTL=43200 REFRESH=0

usage() {
  printf 'usage: %s <model-id> [options]\n' "$(basename "$0")"
  printf '  %-26s %s\n' \
    '--limit N' 'candidates kept after filtering (default 12)' \
    '--sort speed|cost|latency' 'ranking metric (default speed)' \
    '--us' 'drop endpoints with no us segment in the tag' \
    '--parallel N' 'probes in flight at once, at least 1 (default 12)' \
    '--need N' 'stop after N confirmed endpoints, 0 probes all (default 5)' \
    '--ttl S' 'endpoints cache window, verdicts use six times it (default 600)' \
    '--refresh' 'ignore every cache, including the 120 s inconclusive suppression' \
    '--no-probe' 'stats only, no data-policy verdicts' \
    '--max-time S' 'per-probe network ceiling in seconds, above 0 (default 6)' \
    '--min-speed T' 'drop endpoints under T tokens/s p50 (default 10)' \
    '--min-uptime P' 'drop endpoints under P percent uptime (default 50)' \
    '--max-in USD' 'drop endpoints over USD per 1M input tokens (default 999)' \
    '--max-latency MS' 'drop endpoints over MS ms p50 (default 99999)' \
    '--min-context N' 'drop endpoints under N context tokens (default 0)' \
    '--require-sp LIST' 'required supported_parameters, comma list (default tools); empty disables' \
    '--no-zdr-precheck' 'skip the model-level ZDR membership request'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --limit | --sort | --parallel | --need | --ttl | --max-time | --min-speed | \
      --min-uptime | --max-in | --max-latency | --require-sp | --min-context)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      case "$1" in
        --limit) LIMIT=$2 ;;
        --sort) SORT=$2 ;;
        --parallel) PARALLEL=$2 ;;
        --need) NEED=$2 ;;
        --ttl) TTL=$2 ;;
        --max-time) MAXT=$2 ;;
        --min-speed) MIN_SPEED=$2 ;;
        --min-uptime) MIN_UPTIME=$2 ;;
        --max-in) MAX_IN=$2 ;;
        --max-latency) MAX_LATENCY=$2 ;;
        --require-sp) SP_REQ=$2 ;;
        --min-context) MIN_CONTEXT=$2 ;;
      esac
      shift 2 ;;
    --no-probe) PROBE=0; shift ;;
    --no-zdr-precheck) ZDR_PRECHECK=0; shift ;;
    --us) US=1; shift ;;
    --refresh) REFRESH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2 ;;
    *) [ -z "$MODEL" ] && MODEL=$1; shift ;;
  esac
done

case "$SORT" in speed | cost | latency) ;; *) usage >&2; exit 2 ;; esac
if [ -z "$MODEL" ]; then usage >&2; exit 2; fi
for pair in "$LIMIT:--limit" "$PARALLEL:--parallel" "$NEED:--need" "$TTL:--ttl"; do
  value=${pair%%:*}
  case "$value" in '' | *[!0-9]*) echo "${pair##*:} must be a positive integer or 0" >&2; exit 2 ;; *) ;; esac
done
[ "$PARALLEL" -ge 1 ] || { echo "--parallel must be at least 1" >&2; exit 2; }
# Thresholds reach jq as JSON numbers, so they must parse as one before any
# request is made; a bad value is a usage error, not a 404 or a silent zero.
for pair in "$MAXT:--max-time" "$MIN_SPEED:--min-speed" "$MIN_UPTIME:--min-uptime" \
  "$MAX_IN:--max-in" "$MAX_LATENCY:--max-latency" "$MIN_CONTEXT:--min-context"; do
  if [[ ! ${pair%%:*} =~ ^-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$ ]]; then
    echo "${pair##*:} must be a number" >&2
    exit 2
  fi
done
awk -v t="$MAXT" 'BEGIN { exit !(t > 0) }' \
  || { echo "--max-time must be greater than 0 (curl reads 0 as no limit)" >&2; exit 2; }

CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/openrouter-pin
mkdir -p "$CACHE"
chmod 700 "$CACHE"
find "$CACHE" -type f -mtime +7 -delete 2>/dev/null || true
SLUG=${MODEL//[\/:]/_}
STATS=$CACHE/$SLUG.endpoints.json

cache_fresh() {
  local file=$1 span=$2 stamp
  [ -f "$file" ] || return 1
  stamp=$(stat -c %Y "$file" 2>/dev/null || printf 0)
  [ "$(( $(date +%s) - stamp ))" -lt "$span" ]
}

if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  KEY=$OPENROUTER_API_KEY
else
  AUTH=$HOME/.pi/agent/auth.json
  [ -f "$AUTH" ] || { echo "no OpenRouter key: \$OPENROUTER_API_KEY unset and $AUTH missing" >&2; exit 2; }
  KEY=$(jq -r '.openrouter.key // empty' "$AUTH")
fi
[ -n "$KEY" ] || { echo "no OpenRouter key: set \$OPENROUTER_API_KEY or $AUTH .openrouter.key" >&2; exit 2; }

# One temp dir and one trap cover every exit path, so the curlrc holding the
# bearer token is deleted even when a lookup or a probe fails. Requests read it
# through -K, which keeps the key out of the process argument list.
WORK=$(mktemp -d)
chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT
printf 'header = "Authorization: Bearer %s"\n' "$KEY" > "$WORK/curlrc"
chmod 600 "$WORK/curlrc"

if [ "$REFRESH" = 0 ] && cache_fresh "$STATS" "$TTL"; then
  :
else
  EID=$(jq -rn --arg s "$MODEL" '$s | split("/") | map(@uri) | join("/")')
  status=$(curl -s -K "$WORK/curlrc" -o "$WORK/endpoints.json" -w '%{http_code}' "$API/models/$EID/endpoints")
  if [ "$status" != 200 ]; then
    echo "endpoint lookup for '$MODEL' failed (HTTP $status): $(jq -c '.error' "$WORK/endpoints.json" 2>/dev/null || true)" >&2
    exit 3
  fi
  jq -e '.data.endpoints | type == "array"' "$WORK/endpoints.json" >/dev/null || {
    echo "endpoint lookup for '$MODEL' returned an unexpected shape" >&2
    exit 3
  }
  mv "$WORK/endpoints.json" "$STATS"
fi

model_is_eligible() {
  local query members
  # A model outside the ZDR set has no endpoint that can satisfy the data policy,
  # so the run ends here without a single probe.
  if [ "$ZDR_PRECHECK" = 0 ]; then return 0; fi
  query="zdr=true"
  if [ -n "$SP_REQ" ]; then
    query="zdr=true&supported_parameters=$(printf '%s' "$SP_REQ" | sed 's/,/&supported_parameters=/g')"
  fi
  members="$CACHE/members.$(printf '%s' "$query" | tr '&=' '__').json"
  if [ "$REFRESH" = 1 ] || ! cache_fresh "$members" "$MEM_TTL"; then
    if curl -s -K "$WORK/curlrc" -o "$members.tmp" "$API/models?$query" \
       && jq -e '.data | type == "array"' "$members.tmp" >/dev/null; then
      mv "$members.tmp" "$members"
    else
      rm -f "$members.tmp"
      # The precheck can only narrow the run, so a failed request must not gate it.
      echo "membership check unavailable: the ZDR model list could not be fetched, continuing without it" >&2
      return 0
    fi
  fi
  if jq -e --arg m "$MODEL" '[.data[] | (.id, (.canonical_slug // ""))] | index($m) != null' "$members" >/dev/null; then
    return 0
  fi
  echo "'$MODEL' is outside the ZDR set${SP_REQ:+ (capabilities: $SP_REQ)}; no endpoint can qualify, stopping without probes" >&2
  return 1
}

model_is_eligible || exit 4
CANDIDATES=$WORK/candidates.json
SELECTION='
  def region: (.tag | split("/")) as $p
    | ([ "us", "eu" ] | map(select(. as $c | $p | index($c)))
      | (if length > 0 then .[0] else null end)) as $r
    | if $r != null then $r elif ($p | index("global")) then "global" else "-" end;
  def with_region: map(. + {region: region});
  def after_region: (if $us == 1 then map(select(.region == "us")) else . end);
  def capabilities_ok: ((.supported_parameters // []) as $have
    | ($sp | split(",") | all(. as $need | ($have | index($need)) != null)));
  def after_caps: map(select(capabilities_ok));
  def healthy: ((.throughput_last_30m.p50 // 0) >= $ms)
    and ((.uptime_last_30m // 0) >= $mu)
    and ((.latency_last_30m.p50 // 1e9) <= $ml)
    and (((.pricing.prompt // "1e9") | tonumber) * 1000000 <= $mi)
    and ((.context_length // 0) >= $mc);
  def after_health: map(select(healthy));
  def picked: sort_by(if $sk == "speed" then -(.throughput_last_30m.p50 // 0)
      elif $sk == "latency" then (.latency_last_30m.p50 // 1e9)
      else ((.pricing.prompt // "1e9") | tonumber) end)
    | ((map(select(.region == "us")) + map(select(.region != "us")))[:$lim]);
  def funnel: "funnel \(length) endpoints -> \(after_region | length) after region"
    + " -> \(after_region | after_caps | length) after capabilities"
    + " -> \(after_region | after_caps | after_health | length) after health"
    + " -> \(after_region | after_caps | after_health | picked | length) to probe\n";
  .data.endpoints | with_region | funnel
'
COUNTS=$(jq -r --argjson us "$US" --argjson lim "$LIMIT" --arg sp "$SP_REQ" \
  --argjson ms "$MIN_SPEED" --argjson mu "$MIN_UPTIME" --argjson mi "$MAX_IN" \
  --argjson ml "$MAX_LATENCY" --argjson mc "$MIN_CONTEXT" --arg sk "$SORT" -r "$SELECTION" "$STATS")
printf '%s\n' "$COUNTS" >&2

jq -c --argjson us "$US" --arg sp "$SP_REQ" --argjson ms "$MIN_SPEED" --argjson mu "$MIN_UPTIME" \
   --argjson mi "$MAX_IN" --argjson ml "$MAX_LATENCY" --argjson mc "$MIN_CONTEXT" --arg sk "$SORT" \
   --argjson lim "$LIMIT" '
  def region: (.tag | split("/")) as $p
    | ([ "us", "eu" ] | map(select(. as $c | $p | index($c)))
      | (if length > 0 then .[0] else null end)) as $r
    | if $r != null then $r elif ($p | index("global")) then "global" else "-" end;
  def capabilities_ok: ((.supported_parameters // []) as $have
    | ($sp | split(",") | all(. as $need | ($have | index($need)) != null)));
  def healthy: ((.throughput_last_30m.p50 // 0) >= $ms)
    and ((.uptime_last_30m // 0) >= $mu)
    and ((.latency_last_30m.p50 // 1e9) <= $ml)
    and (((.pricing.prompt // "1e9") | tonumber) * 1000000 <= $mi)
    and ((.context_length // 0) >= $mc);
  .data.endpoints
  | map(. + {region: region})
  | (if $us == 1 then map(select(.region == "us")) else . end)
  | map(select(capabilities_ok))
  | map(select(healthy))
  | sort_by(if $sk == "speed" then -(.throughput_last_30m.p50 // 0)
      elif $sk == "latency" then (.latency_last_30m.p50 // 1e9)
      else ((.pricing.prompt // "1e9") | tonumber) end)
  | ((map(select(.region == "us")) + map(select(.region != "us")))[:$lim])[]
' "$STATS" > "$CANDIDATES"

TAGS=$WORK/tags.txt
jq -r '.tag' "$CANDIDATES" > "$TAGS"
TAGCOUNT=$(wc -l < "$TAGS")
if [ "$TAGCOUNT" -eq 0 ]; then
  if [ "$US" = 1 ]; then
    echo "no endpoints matched for '$MODEL' (--us keeps us-region tags only; retry without it)" >&2
  else
    echo "no endpoints matched for '$MODEL' (the capability or health thresholds filtered every endpoint)" >&2
  fi
  exit 3
fi

verdict_cache_file() { printf '%s/v.%s.%s' "$CACHE" "$SLUG" "$(printf '%s' "$1" | tr '/:.' '___')"; }

probe() {
  local tag=$1 file=$2 body result code note elapsed _attempt cache_file
  body=$(jq -n --arg m "$MODEL" --arg t "$tag" \
    '{model: $m, messages: [{role: "user", content: "x"}], max_tokens: 1,
     reasoning: {effort: "minimal"},
     provider: {only: [$t], zdr: true, data_collection: "deny", allow_fallbacks: false}}')
  cache_file=$(verdict_cache_file "$tag")
  for _attempt in 1 2; do
    result=$(curl -s --max-time "$MAXT" -o "$WORK/resp.$file" -w '%{http_code} %{time_total}' \
      -K "$WORK/curlrc" -H 'Content-Type: application/json' -d "$body" "$API/chat/completions" || printf '000 0')
    code=${result%% *}
    elapsed=${result##* }
    # A 429 that arrives fast is a rate limit worth one retry; a 429 after many
    # seconds is an upstream stall, and retrying only burns time.
    [ "$code" = 429 ] || break
    case "$elapsed" in 0.* | 1.* | 2.*) sleep 1; continue ;; *) break ;; esac
  done
  case "$code" in
    200) printf 'ok\n' | tee "$WORK/verdict.$file" > "$cache_file" ;;
    000) printf 'inconclusive(timeout %ss)\n' "$MAXT" > "$WORK/verdict.$file"
         printf 'inconclusive(timeout %ss)\n' "$MAXT" > "$(verdict_cache_file "$tag").recent" ;;
    *)
      note=$(jq -r '.error.message // "upstream error"' "$WORK/resp.$file" 2>/dev/null | tr -d '\n')
      case "$note" in
        *'data policy'*)
          printf 'not ZDR\n' | tee "$WORK/verdict.$file" > "$cache_file" ;;
        *) printf 'inconclusive(%s) %s\n' "$code" "$(printf %s "$note" | cut -c1-40)" | tee "$WORK/verdict.$file" > "$(verdict_cache_file "$tag").recent" ;;
      esac ;;
  esac
}

ok_count=0
i=0
while [ "$i" -lt "$TAGCOUNT" ]; do
  wave_end=$((i + PARALLEL))
  if [ "$wave_end" -gt "$TAGCOUNT" ]; then wave_end=$TAGCOUNT; fi
  j=$i
  while [ "$j" -lt "$wave_end" ]; do
    tag=$(sed -n "$((j + 1))p" "$TAGS")
    if [ "$PROBE" = 0 ]; then
      printf 'unprobed\n' > "$WORK/verdict.$j"
    else
      cached=$(verdict_cache_file "$tag")
      recent=$(verdict_cache_file "$tag").recent
      if [ "$REFRESH" = 0 ] && cache_fresh "$cached" $((TTL * 6)); then
        cat "$cached" > "$WORK/verdict.$j"
      elif [ "$REFRESH" = 0 ] && cache_fresh "$recent" 120; then
        cat "$recent" > "$WORK/verdict.$j"
      else
        probe "$tag" "$j" &
      fi
    fi
    j=$((j + 1))
  done
  wait
  j=$i
  while [ "$j" -lt "$wave_end" ]; do
    if [ "$(cat "$WORK/verdict.$j" 2>/dev/null)" = ok ]; then
      ok_count=$((ok_count + 1))
    fi
    j=$((j + 1))
  done
  i=$wave_end
  if [ "$PROBE" = 1 ] && [ "$NEED" -gt 0 ] && [ "$ok_count" -ge "$NEED" ]; then break; fi
done

VERDICTS=$WORK/verdicts.txt
: > "$VERDICTS"
k=0
while [ "$k" -lt "$TAGCOUNT" ]; do
  if [ -f "$WORK/verdict.$k" ]; then
    cat "$WORK/verdict.$k" >> "$VERDICTS"
  else
    printf 'not probed (stopped early)\n' >> "$VERDICTS"
  fi
  k=$((k + 1))
done

if [ "$PROBE" = 1 ]; then
  probed=$(grep -c 'not probed (stopped early)' "$VERDICTS" || true)
  [ "$probed" = "$TAGCOUNT" ] && echo "warning: no data-policy probe produced a verdict; the table is unverified" >&2
fi

jq -r '
  def money: if . == null then "" else (((. | tonumber) * 1000000 * 100 | round) / 100) end;
  [ .tag, (.provider_name // "?"), (.quantization // "?"), .region,
    (.throughput_last_30m.p50 // 0), (.latency_last_30m.p50 // 0), (.uptime_last_30m // 0),
    (.pricing.prompt | money), (.pricing.completion | money), (.pricing.input_cache_read | money),
    (.context_length // 0), (.max_completion_tokens // 0) ] | map(tostring) | join("\t")
' "$CANDIDATES" > "$WORK/rows.tsv"

paste "$VERDICTS" "$WORK/rows.tsv" \
  | awk -F'\t' -v OFS='\t' '{
      flag = ($1 == "ok") ? 0 : 1
      urank = ($5 == "us") ? 0 : 1
      print flag, urank, $0
    }' > "$WORK/body.tsv"

{
  printf 'data policy\ttag\tprovider\tquant\tregion\ttok/s p50\tlatency ms p50\tuptime %%\tin $/M\tout $/M\tcache $/M\tcontext\tmax-out\n'
  sort -s -t"$(printf '\t')" -k1,1n -k2,2n "$WORK/body.tsv" | cut -f3-
} | column -t -s"$(printf '\t')"
