from __future__ import annotations

import os
from pathlib import Path


def configure_tls_ca_bundle() -> None:
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return
    try:
        import certifi
    except ImportError:
        return
    bundle = Path(certifi.where())
    if bundle.is_file():
        os.environ["SSL_CERT_FILE"] = str(bundle)


configure_tls_ca_bundle()

from docferry_agent_kit.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
