import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("resolver", ROOT / "scripts/resolve-image.py")
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)


class RecipeTests(unittest.TestCase):
    def test_stable_versions(self):
        for raw, expected in (("2026.11.4", "2026.11.4"), ("v2026.9.5", "2026.9.5"), ("2026.11.4-1", "2026.11.4-1")):
            self.assertEqual(resolver.normalize_version(raw), expected)

    def test_untrusted_or_prerelease_inputs_are_rejected(self):
        for raw in ("", "main", "2026.11.5-beta.4", "2026.11.4;id", "../../etc/passwd", "v2026.11.4\nx", "$(id)"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                resolver.normalize_version(raw)

    def test_release_must_be_stable(self):
        for flag in ("draft", "prerelease"):
            with self.assertRaises(ValueError):
                resolver.release_version({"tag_name": "v2026.11.4", flag: True})

    def test_manifest_digest_and_platform(self):
        body = json.dumps({"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}]}).encode()
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        self.assertEqual(resolver.verify_manifest(body, digest, "linux/amd64"), digest)
        with self.assertRaises(ValueError):
            resolver.verify_manifest(body, "sha256:" + "0" * 64, "linux/amd64")
        with self.assertRaises(ValueError):
            resolver.verify_manifest(body, digest, "linux/arm64")

    def test_fingerprint_is_stable_and_base_sensitive(self):
        first = resolver.recipe_fingerprint("base@sha256:a")
        self.assertEqual(first, resolver.recipe_fingerprint("base@sha256:a"))
        self.assertNotEqual(first, resolver.recipe_fingerprint("base@sha256:b"))

    def test_outputs_refuse_line_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outputs"
            with self.assertRaises(ValueError):
                resolver.write_outputs(path, {"version": "2026.11.4\nother=true"})
            self.assertFalse(path.exists())

    def test_dockerfile_preserves_runtime_contract(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        directives = [line.strip().split()[0].upper() for line in dockerfile.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        for forbidden in ("ENTRYPOINT", "CMD", "HEALTHCHECK", "COPY", "ADD", "VOLUME"):
            self.assertNotIn(forbidden, directives)
        self.assertTrue(dockerfile.rstrip().endswith("USER node"))
        for package in ("vim", "netcat-openbsd", "ffmpeg", "fonts-noto-cjk"):
            self.assertIn(package, dockerfile)

    def test_default_pin_is_consistent(self):
        config = json.loads((ROOT / "image-config.json").read_text())
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn(f"{config['default_version']}-browser@{config['default_base_digest']}", dockerfile)

    def test_resolve_latest_and_manual_candidate_policy(self):
        manifest = json.dumps({"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}]}).encode()
        digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
        responses = [
            (json.dumps({"tag_name": "v2026.11.4", "draft": False, "prerelease": False}).encode(), {}),
            (b'{"token":"fake-test-token"}', {}),
            (manifest, {"Docker-Content-Digest": digest}),
        ]
        for selected, expected in (("latest", "true"), ("2026.11.4", "false")):
            with patch.object(resolver, "request", side_effect=responses):
                result = resolver.resolve(selected, "Shen-Chris/openclaw-image")
            self.assertEqual(result["update_candidate"], expected)
            self.assertTrue(result["image_ref"].startswith("ghcr.io/shen-chris/openclaw-image:2026.11.4-r1-"))
            self.assertNotIn("fake-test-token", json.dumps(result))

    def test_repository_input_is_validated_before_network(self):
        with patch.object(resolver, "request") as request:
            with self.assertRaises(ValueError):
                resolver.resolve("latest", "owner/repo;id")
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
