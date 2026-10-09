#!/usr/bin/env bash
# DreamLayer CLI wrapper. Reads the API key from the environment or from a local credentials file
# OUTSIDE the repository (~/.config/dreamlayer/credentials.env). Never commit keys.
set -euo pipefail
CRED="${DREAMLAYER_CREDENTIALS:-$HOME/.config/dreamlayer/credentials.env}"
if [ -z "${DREAMLAYER_API_KEY:-}" ] && [ -f "$CRED" ]; then
  set -a; . "$CRED"; set +a
fi
if [ -z "${DREAMLAYER_API_KEY:-}" ]; then
  echo "DREAMLAYER_API_KEY is not set and $CRED was not found." >&2
  exit 2
fi
# Redact the key from any output just in case.
npx --yes dreamlayer@0.4.0-beta.4 "$@" 2>&1 | sed -E 's/dlr_(live|test)_[A-Za-z0-9]+/<redacted>/g'
exit "${PIPESTATUS[0]}"
