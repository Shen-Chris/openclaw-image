#!/usr/bin/env bash
set -euo pipefail

image="${1:?usage: smoke-test.sh IMAGE EXPECTED_VERSION}"
expected_version="${2:?expected OpenClaw version required}"

# No production volumes, no credentials, no network, no Docker socket.
# Feed the checks over stdin so they need not be baked into the runtime image.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
docker run --rm -i --network none \
  --entrypoint /bin/sh \
  -e EXPECTED_OPENCLAW_VERSION="$expected_version" \
  "$image" -eu < "$script_dir/smoke-checks.sh"
