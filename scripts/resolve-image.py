#!/usr/bin/env python3
"""Resolve an official stable browser image; no third-party Python packages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"20\d{2}\.\d{1,2}\.\d{1,2}(?:-\d+)?")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
RECIPE_FILES = (
    "Dockerfile", "image-config.json", "scripts/resolve-image.py",
    "scripts/smoke-test.sh", ".github/workflows/image.yml",
)
ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
))


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(newurl)
        if (new.scheme, new.netloc) != (old.scheme, old.netloc):
            raise RuntimeError("cross-origin redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url, headers=None):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("only HTTPS is allowed")
    opener = urllib.request.build_opener(SameOriginRedirect())
    for attempt in range(3):
        req = urllib.request.Request(url, headers={
            "User-Agent": "openclaw-image-release-resolver",
            **(headers or {}),
        })
        try:
            with opener.open(req, timeout=30) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise RuntimeError("response exceeds the size limit")
                return body, response.headers
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(
                    f"{urllib.parse.urlsplit(url).hostname} returned HTTP {error.code}"
                ) from None
            retry_after = error.headers.get("Retry-After", "")
            if retry_after.isdigit():
                delay = int(retry_after)
                if delay > 60:
                    raise RuntimeError("rate limited; retry on a later workflow run") from None
            else:
                delay = 2 ** (attempt + 1)
            time.sleep(delay)


def normalize_version(value):
    value = value.strip()
    if value.startswith("v"):
        value = value[1:]
    if not VERSION_RE.fullmatch(value):
        raise ValueError("expected a stable version, e.g. 2026.11.4; beta/rc are refused")
    return value


def release_version(release):
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("draft and prerelease builds are disabled")
    return normalize_version(release.get("tag_name", ""))


def verify_manifest(body, digest, platform):
    if not DIGEST_RE.fullmatch(digest or ""):
        raise ValueError("registry did not supply a valid manifest digest")
    if "sha256:" + hashlib.sha256(body).hexdigest() != digest:
        raise ValueError("manifest content does not match the registry digest")
    manifest = json.loads(body)
    os_name, architecture = platform.split("/", 1)
    if not any(
        item.get("platform", {}).get("os") == os_name
        and item.get("platform", {}).get("architecture") == architecture
        for item in manifest.get("manifests", [])
    ):
        raise ValueError(f"official browser image does not contain {platform}")
    return digest


def recipe_fingerprint(base_image):
    hasher = hashlib.sha256(base_image.encode())
    for relative in RECIPE_FILES:
        hasher.update(b"\0" + relative.encode() + b"\0")
        hasher.update((ROOT / relative).read_bytes())
    return hasher.hexdigest()[:16]


def write_outputs(path, values):
    for key, value in values.items():
        if "\n" in str(value) or "\r" in str(value):
            raise ValueError("multiline workflow outputs are refused")
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def resolve(selected, repository):
    config = json.loads((ROOT / "image-config.json").read_text())
    if config["platform"] != "linux/amd64":
        raise ValueError("this workflow currently supports linux/amd64 only")
    revision = config["recipe_revision"]
    if type(revision) is not int or revision < 1:
        raise ValueError("recipe_revision must be a positive integer")
    repository = repository.lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*", repository):
        raise ValueError("repository must be a GitHub owner/repository name")

    automatic = selected.strip() in ("", "latest")
    suffix = "latest" if automatic else "tags/v" + normalize_version(selected)
    api_headers = {"Accept": "application/vnd.github+json"}
    # The GitHub credential is sent only to api.github.com, never to a registry.
    if os.environ.get("GITHUB_TOKEN"):
        api_headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    body, _ = request(
        "https://api.github.com/repos/openclaw/openclaw/releases/" + suffix,
        api_headers,
    )
    version = release_version(json.loads(body))
    if not automatic and version != normalize_version(selected):
        raise ValueError("release version does not match the requested version")

    # An anonymous public pull token remains in memory; it is never an output.
    body, _ = request(
        "https://ghcr.io/token?service=ghcr.io&scope=repository:openclaw/openclaw:pull"
    )
    token_data = json.loads(body)
    pull_token = token_data.get("token") or token_data.get("access_token")
    if not isinstance(pull_token, str) or not pull_token:
        raise ValueError("registry did not issue an anonymous pull token")
    body, headers = request(
        f"https://ghcr.io/v2/openclaw/openclaw/manifests/{version}-browser",
        {"Authorization": "Bearer " + pull_token, "Accept": ACCEPT},
    )
    digest = verify_manifest(body, headers.get("Docker-Content-Digest"), config["platform"])
    base_image = f"ghcr.io/openclaw/openclaw:{version}-browser@{digest}"
    fingerprint = recipe_fingerprint(base_image)
    image = "ghcr.io/" + repository
    tag = f"{version}-r{revision}-{fingerprint}"
    return {
        "version": version,
        "base_image": base_image,
        "base_digest": digest,
        "platform": config["platform"],
        "recipe_fingerprint": fingerprint,
        "image": image,
        "image_ref": f"{image}:{tag}",
        "candidate_ref": f"{image}:candidate",
        # A manually selected old version must never downgrade candidate.
        "update_candidate": "true" if automatic else "false",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="latest")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--github-output", help="append outputs to this Actions output file")
    args = parser.parse_args()
    try:
        values = resolve(args.version, args.repository)
        if args.github_output:
            write_outputs(args.github_output, values)
        print(json.dumps(values, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f"resolve-image: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
