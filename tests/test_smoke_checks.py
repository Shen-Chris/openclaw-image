"""Regression tests for checker control flow; these do not replace Docker CI."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "scripts/smoke-checks.sh"


class SmokeCheckTests(unittest.TestCase):
    def run_checks(self, *, missing=None, font="Noto Sans CJK SC", nc_flags="-X protocol -x proxy", node_status=0, cli_status=0, uid=1000):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            font_path = folder / "font.ttc"
            font_path.write_text("fake font fixture")
            mocks = {
                "id": f"printf '%s\\n' {uid}",
                "vim": "exit 0",
                "ffmpeg": "exit 0",
                "nc": "printf '%s\\n' \"$FAKE_NC_FLAGS\"; exit 1",
                "fc-match": "case \"$*\" in *'%{file}'*) printf '%s' \"$FAKE_FONT_FILE\" ;; *'Noto Sans CJK SC:lang=zh'*) printf '%s' \"$FAKE_FONT\" ;; *) printf '%s' 'DejaVu Sans' ;; esac",
                "node": f"exit {node_status}",
                "openclaw": f"exit {cli_status}",
                **{name: "exit 0" for name in ("python3", "git", "curl", "ssh")},
            }
            for name, body in mocks.items():
                if name == missing:
                    continue
                file = folder / name
                file.write_text("#!/bin/sh\n" + body + "\n")
                file.chmod(0o755)
            return subprocess.run(
                ["/bin/sh", str(CHECKS)], capture_output=True, text=True,
                env={**os.environ, "PATH": str(folder), "FAKE_FONT": font,
                     "FAKE_FONT_FILE": str(font_path), "FAKE_NC_FLAGS": nc_flags,
                     "EXPECTED_OPENCLAW_VERSION": "2026.11.4"}, timeout=10,
            )

    def test_explicit_font_passes_even_when_generic_default_is_dejavu(self):
        result = self.run_checks()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[PASS]", result.stdout)

    def test_missing_noto_font_still_fails(self):
        result = self.run_checks(font="DejaVu Sans")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Noto CJK family is not discoverable", result.stderr)

    def test_missing_executable_names_the_tool(self):
        result = self.run_checks(missing="vim")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing executable: vim", result.stderr)

    def test_wrong_nc_does_not_pass(self):
        result = self.run_checks(nc_flags="-x proxy only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nc does not expose -X", result.stderr)

    def test_runtime_version_or_browser_failure_names_the_stage(self):
        result = self.run_checks(node_status=7)
        self.assertEqual(result.returncode, 7)
        self.assertIn("stage=OpenClaw package version and Chromium executable exit=7", result.stderr)

    def test_cli_failure_is_not_swallowed(self):
        result = self.run_checks(cli_status=9)
        self.assertEqual(result.returncode, 9)
        self.assertIn("stage=OpenClaw CLI startup exit=9", result.stderr)

    def test_root_runtime_is_still_rejected(self):
        result = self.run_checks(uid=0)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("image must not run as root", result.stderr)


if __name__ == "__main__":
    unittest.main()
