from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from jass_chibre.webapp import run  # noqa: E402


def open_browser(host: str, port: int) -> None:
    webbrowser.open(f"http://{host}:{port}")


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    threading.Timer(1.0, open_browser, args=(host, port)).start()
    run(host=host, port=port)
