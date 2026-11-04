#!/usr/bin/env python3
"""
Publishes a GitHub release with the GitHub CLI (gh).

  python tools/create_github_release.py --version 1.4 [--arts DIR] [--draft]

1. builds the archives (tools/package_releases.py)
2. tags HEAD as v<version>-ptbr and pushes the tag
3. creates the release with notes from docs/release-notes/v<version>.md and uploads
   every releases/EDFC-N8-*.zip produced for this version
"""
import argparse, glob, os, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*cmd):
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=REPO)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--arts", help="folder with EDFC/ARTS for the covers archive")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    tag = f"v{a.version}-ptbr"
    notes = os.path.join(REPO, "docs", "release-notes", f"v{a.version}.md")
    if not os.path.exists(notes):
        sys.exit(f"missing release notes: {notes}")

    pkg = [sys.executable, os.path.join("tools", "package_releases.py"), "--version", a.version]
    if a.arts:
        pkg += ["--arts", a.arts]
    run(*pkg)
    assets = sorted(glob.glob(os.path.join(REPO, "releases", f"EDFC-N8-*v{a.version}.zip")))
    full = os.path.join(REPO, "releases", "EDFC-N8-ArtPack-Completo.zip")
    if os.path.exists(full):
        assets.append(full)

    if subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cwd=REPO,
                      capture_output=True).returncode != 0:
        run("git", "tag", "-a", tag, "-m", f"Release {tag}")
    run("git", "push", "origin", tag)
    cmd = ["gh", "release", "create", tag, "--verify-tag", "--latest",
           "--title", f"EverDrive N8 PT-BR v{a.version}", "--notes-file", notes]
    if a.draft:
        cmd.append("--draft")
    run(*cmd, *assets)


if __name__ == "__main__":
    main()
