import subprocess
import sys
from pathlib import Path


def test_installed_runtime_imports_from_unrelated_directory_without_network(tmp_path: Path) -> None:
    program = """
import importlib.abc
import importlib.util
import socket
import sys
from unittest.mock import patch

for name in ('haystack', 'psycopg', 'psycopg2', 'pgvector', 'docling', 'torch', 'sentence_transformers'):
    assert importlib.util.find_spec(name) is None, name

blocked_imports = {
    'agent_framework', 'agent_framework_openai', 'openai', 'httpx', 'httpx2', 'haystack', 'apps', 'workbench'
}


class ProviderImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in blocked_imports:
            raise AssertionError(f'Unexpected runtime import: {fullname}')
        return None


sys.meta_path.insert(0, ProviderImportGuard())
with (
    patch.object(socket.socket, 'connect', side_effect=AssertionError('Unexpected outbound connection')),
    patch.object(socket, 'getaddrinfo', side_effect=AssertionError('Unexpected DNS lookup')),
):
    import agent_runtime.cli
    import agent_runtime.configuration
    import agent_runtime.contracts
    import agent_runtime.runtime
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", program], cwd=tmp_path, capture_output=True, text=True, timeout=10, check=False
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
