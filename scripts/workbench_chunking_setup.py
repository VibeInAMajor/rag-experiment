"""Explicitly provision pinned tokenizer assets; runtime indexing never downloads them."""

import io
import json
from hashlib import sha256
from urllib.request import urlopen
from zipfile import ZipFile

from apps.workbench.api.chunking_adapters import (
    _ASSET_ROOT,
    _PUNKT_FILES,
    _PUNKT_LANGUAGES,
    _PUNKT_SHA256,
    _PUNKT_URL,
    _TOKEN_SHA256,
    _TOKEN_URL,
    _punkt_digest,
)


def _download(url: str, expected: str) -> bytes:
    with urlopen(url, timeout=30) as response:
        if response.url != url:
            raise RuntimeError("Tokenizer asset redirects are not allowed.")
        content = response.read(5_000_001)
    if len(content) > 5_000_000 or sha256(content).hexdigest() != expected:
        raise RuntimeError("Tokenizer asset does not match its reviewed digest.")
    return content


def main() -> None:
    """Download only approved assets and write only the reviewed EN/RU tables and encoding."""
    archive = _download(_PUNKT_URL, _PUNKT_SHA256)
    encoding = _download(_TOKEN_URL, _TOKEN_SHA256)
    _ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    revisions = {}
    with ZipFile(io.BytesIO(archive)) as package:
        for code, language in _PUNKT_LANGUAGES:
            destination = _ASSET_ROOT / "nltk/tokenizers/punkt_tab" / language
            destination.mkdir(parents=True, exist_ok=True)
            for name in _PUNKT_FILES:
                content = package.read(f"punkt_tab/{language}/{name}")
                if len(content) > 2_000_000:
                    raise RuntimeError("Tokenizer asset member exceeds its reviewed size.")
                (destination / name).write_bytes(content)
            revisions[code] = _punkt_digest(destination)
    (_ASSET_ROOT / "o200k_base.tiktoken").write_bytes(encoding)
    print(json.dumps({"assets": "provisioned", "sentence_resource_hashes": revisions}, sort_keys=True))


if __name__ == "__main__":
    main()
