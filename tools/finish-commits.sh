#!/usr/bin/env bash
# Finishes the initial commit history.
#
# The first commit landed, then git stalled: the Claude session's mount does not
# permit unlinking files, so git could not clear its own .git/*.lock files.
# Running this from your own Terminal has no such restriction.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -f .git/index.lock .git/HEAD.lock

TRAILER="Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017UsJrADyP5ZwkxjjicBgPt"

git add shiftd/ launchd/ tests/ docs/DAEMON.md
git commit -q -m "Add shiftd daemon, launchd agent and tests

Holds the schedule and reconciles the phone toward it once a minute.

Locked shifts cannot be ended early, including from the Mac, which is the
commitment device the whole project exists for. Countdowns run off a monotonic
budget so changing the system clock does not end one. Reconcile is idempotent
and re-asserts the profile when the phone reappears, so unplugging is not a
bypass. transport.py is the only module that touches the device.

50 tests, transport mocked, no phone required.

$TRAILER"

git add -A
git commit -q -m "Add supervision runbook, recovery docs and keybag tooling

Phase 0.5 of the runbook generates and verifies the supervision identity before
anything is erased, which removes most of the risk from the erase.

verify_keybag.py replays the exact calls MobileConfigService.escalate() makes,
including building the real PKCS7 challenge signature, entirely offline. The
only step it cannot prove is the device accepting the certificate, and that
holds by construction when the device is prepared with the same organization.

make_keybag.py does the p12 conversion in Python rather than the openssl CLI,
because openssl pkcs12 -clcerts returns nothing when the identity certificate
is not flagged as a client cert, which is how Apple Configurator exports it.

$TRAILER"

echo
git log --oneline
echo
echo "tracked files: $(git ls-files | wc -l | tr -d ' ')"
echo
echo "secret check, should print nothing:"
# Read the device id out of the untracked local cache so this script never
# contains it, otherwise the grep matches itself.
UDID_FILE=results/artifacts/udid.txt
git ls-files | grep -Ei '\.(p12|pfx|pem|key|cer|crt)$' || true
if [ -s "$UDID_FILE" ]; then
  git grep -l "$(cat "$UDID_FILE")" -- . 2>/dev/null || true
fi
git ls-files -z | xargs -0 grep -lE "^-----BEGIN (RSA |EC )?PRIVATE KEY-----" 2>/dev/null || true
echo "(clean)"
