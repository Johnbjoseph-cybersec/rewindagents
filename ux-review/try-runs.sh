#!/bin/sh
# Five-minute try of `fork` + `compare` with no agent needed: a recorded session is made by feeding the real
# hook the payloads Claude Code sends (as tests/test_rewind.py does), then a second attempt is made by hand in
# a fork. With a real agent, replace the `hook` lines with a session and the hand edit with a second session.
# Usage: sh ux-review/try-runs.sh [rewindagents command]   (default: rewindagents on PATH)
set -eu
RA=${1:-rewindagents}
T=$(mktemp -d)
P="$T/shop"
mkdir "$P" && cd "$P"
git init -q && printf 'def total(prices):\n    return sum(prices)\n' > cart.py && git add . \
  && git -c user.name=demo -c user.email=demo@localhost commit -qm init

call() {  # call <event> <tool> <input json> : one hook event, as Claude Code sends it
  printf '{"session_id":"demo-0001","cwd":"%s","hook_event_name":"%s","tool_name":"%s","tool_input":%s,"tool_response":{}}' \
    "$P" "$1" "$2" "$3" | $RA hook
}
write() {  # write <file> <content> : one agent Write step
  inp=$(python3 -c 'import json,sys; print(json.dumps({"file_path": sys.argv[1], "content": sys.argv[2]}))' "$P/$1" "$2")
  call PreToolUse Write "$inp"; printf '%s' "$2" > "$1"; call PostToolUse Write "$inp"
}

write cart.py 'def total(prices, discount=0):
    return sum(prices) - discount
'
write test_cart.py 'from cart import total
assert total([10, 5], discount=20) >= 0, "a total below zero"
'
write cart.py 'def total(prices, discount=0):
    return sum(prices) - discount  # TODO clamp
'
echo "--- the recorded session"
$RA replay
echo "--- fork step 2 into a second attempt"
$RA fork 2 --name clamp
printf 'def total(prices, discount=0):\n    return max(0, sum(prices) - discount)\n' > "$P-clamp/cart.py"
echo "--- compare, with the test file as the check"
$RA compare --check "python3 test_cart.py"
echo "--- how the second attempt differs"
$RA compare --diff shop clamp
echo "(left in $T; delete it when done)"
