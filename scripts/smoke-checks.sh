#!/bin/sh
# Executed only inside the throwaway smoke-test container; no production state.
set -eu

stage=initialization
trap 'result=$?; if [ "$result" -ne 0 ]; then printf "[FAIL] stage=%s exit=%s\n" "$stage" "$result" >&2; fi' 0

check() {
    stage="$1"
    printf '\n[CHECK] %s\n' "$stage"
}

fail() {
    printf '[FAIL] %s\n' "$1" >&2
    exit 1
}

check 'non-root runtime user'
uid="$(id -u)"
printf 'Runtime uid: %s\n' "$uid"
[ "$uid" -ne 0 ] || fail 'image must not run as root'

check 'required executables'
for tool in vim nc ffmpeg fc-match python3 git curl ssh node openclaw; do
    location="$(command -v "$tool")" || fail "missing executable: $tool"
    printf '%s: %s\n' "$tool" "$location"
done

check 'vim version'
vim --version >/dev/null

check 'ffmpeg version'
ffmpeg -version >/dev/null

check 'nc HTTP CONNECT / SOCKS proxy options'
help="$(nc -h 2>&1 || true)"
case "$help" in *-X*) ;; *) fail 'nc does not expose -X proxy protocol selection' ;; esac
case "$help" in *-x*) ;; *) fail 'nc does not expose -x proxy address selection' ;; esac

check 'installed Noto CJK font, independent of the default font choice'
font="$(fc-match -f '%{family}' 'Noto Sans CJK SC:lang=zh')"
printf 'Explicit CJK font match: %s\n' "$font"
case "$font" in *Noto*CJK*) ;; *) fail 'Noto CJK family is not discoverable' ;; esac
font_file="$(fc-match -f '%{file}' 'Noto Sans CJK SC:lang=zh')"
printf 'CJK font file: %s\n' "$font_file"
[ -r "$font_file" ] || fail 'matched CJK font file is not readable'

check 'OpenClaw package version and Chromium executable'
: "${EXPECTED_OPENCLAW_VERSION:?expected version is required}"
node -e '
    const fs = require("node:fs");
    const expected = process.env.EXPECTED_OPENCLAW_VERSION;
    const actual = require("/app/package.json").version;
    if (actual !== expected) throw new Error(`Expected ${expected}, got ${actual}`);
    const browser = require("playwright-core").chromium.executablePath();
    fs.accessSync(browser, fs.constants.X_OK);
    console.log(`PASS: OpenClaw ${actual}, Chromium executable present`);
'

check 'OpenClaw CLI startup'
openclaw --version

printf '\n[PASS] All isolated image smoke checks passed.\n'
