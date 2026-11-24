"""Explicit pinned-model provisioning; PDF uploads never download model assets."""

import argparse
import json
import shutil
from pathlib import Path

from apps.workbench.parsing.pdf.pdf_assets import pdf_assets_directory, pdf_assets_revision, verify_pdf_assets


def main() -> None:
    """Download pinned files, copy an existing offline installation, or verify the deployed files."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--download", action="store_true")
    mode.add_argument("--from-directory", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    options = parser.parse_args()
    root = pdf_assets_directory()
    manifest_path = Path(__file__).resolve().parents[1] / "apps/workbench/parsing/pdf/pdf_asset_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if options.verify_only and (options.download or options.from_directory):
        parser.error("--verify-only cannot provision assets")
    if options.download:
        from huggingface_hub import snapshot_download

        for repository in manifest["repositories"]:
            prefix = repository["directory"] + "/"
            patterns = [item["path"][len(prefix) :] for item in manifest["files"] if item["path"].startswith(prefix)]
            snapshot_download(
                repo_id=repository["repo_id"],
                revision=repository["revision"],
                local_dir=root / repository["directory"],
                allow_patterns=patterns,
            )
    elif options.from_directory:
        supplied = options.from_directory.resolve()
        verify_pdf_assets(supplied)
        for item in manifest["files"]:
            target = root / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if (supplied / item["path"]).resolve() != target.resolve():
                shutil.copyfile(supplied / item["path"], target)
    verify_pdf_assets(root)
    print(json.dumps({"status": "verified", "assets_revision": pdf_assets_revision(), "files": len(manifest["files"])}))


if __name__ == "__main__":
    main()
