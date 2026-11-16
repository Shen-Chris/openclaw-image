#!/usr/bin/env bash
set -euo pipefail

image="${1:?usage: smoke-test.sh IMAGE EXPECTED_VERSION}"
expected_version="${2:?expected OpenClaw version required}"

# No production volumes, no credentials, no network, no Docker socket.
docker run --rm --network none \
  --entrypoint /bin/sh \
  -e EXPECTED_OPENCLAW_VERSION="$expected_version" \
  "$image" -ec '
    test "$(id -u)" -ne 0
    for tool in vim nc ffmpeg fc-match python3 git curl ssh node; do
      command -v "$tool" >/dev/null
    done
    vim --version >/dev/null
    ffmpeg -version >/dev/null
    help="$(nc -h 2>&1 || true)"
    printf "%s\n" "$help" | grep -q -- "-X"
    printf "%s\n" "$help" | grep -q -- "-x"
    font="$(fc-match -f "%{family}" "sans:lang=zh")"
    printf "%s\n" "$font" | grep -qi "Noto.*CJK"
    node -e '\''
      const fs = require("node:fs");
      const expected = process.env.EXPECTED_OPENCLAW_VERSION;
      const actual = require("/app/package.json").version;
      if (actual !== expected) throw new Error(`Expected ${expected}, got ${actual}`);
      const browser = require("playwright-core").chromium.executablePath();
      fs.accessSync(browser, fs.constants.X_OK);
      console.log(`PASS: OpenClaw ${actual}, Chromium executable present`);
    '\''
    openclaw --version
    echo "PASS: non-root user, vim, nc HTTP/SOCKS proxy flags, ffmpeg, CJK font lookup"
  '
