#!/usr/bin/env bash
# Generate synthetic checkout traffic against the payment app.
# Usage: PAYMENT_PORT=8081 DELAY=0.5 ./scripts/generate-checkout-traffic.sh [count]
# Omit count to run until Ctrl-C.
set -uo pipefail

base_url="http://localhost:${PAYMENT_PORT:-8081}"
delay="${DELAY:-0.5}"
count="${1:-0}"
countries=(US GB DE FR CA AU BR IN SY)
cards=(4111111111111111 4242424242424242 5555555555554444 378282246310005)

i=0
while [ "${count}" -eq 0 ] || [ "${i}" -lt "${count}" ]; do
  # Each GET mints a fresh checkout_id and a random amount; reuse both so the
  # POST looks like a real submission of the page the user was shown.
  page="$(curl -s --max-time 5 "${base_url}/checkout")" || { echo "GET failed"; sleep "${delay}"; continue; }
  checkout_id="$(printf '%s' "${page}" | sed -n 's/.*name="checkout_id" value="\([^"]*\)".*/\1/p')"
  amount="$(printf '%s' "${page}" | sed -n 's/.*name="amount" value="\([^"]*\)".*/\1/p')"
  [ -n "${checkout_id}" ] || { echo "no checkout_id in response"; sleep "${delay}"; continue; }

  status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST "${base_url}/checkout" \
    -d "checkout_id=${checkout_id}" \
    -d "amount=${amount}" \
    -d "currency=USD" \
    -d "country=${countries[RANDOM % ${#countries[@]}]}" \
    -d "card_number=${cards[RANDOM % ${#cards[@]}]}")"

  i=$((i + 1))
  printf '%4d  HTTP %s  %s  $%s\n' "${i}" "${status}" "${checkout_id:0:8}" "${amount}"
  sleep "${delay}"
done
