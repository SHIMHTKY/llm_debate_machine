#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))


def main() -> None:
    import uvicorn

    host = os.getenv("DEBATE_STUDIO_HOST", "127.0.0.1")
    port = int(os.getenv("DEBATE_STUDIO_PORT", "8000"))
    uvicorn.run("llm_debat_machine.backend.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
