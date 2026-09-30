"""Local launcher: reuse a healthy studio, otherwise run main.py and open it."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_MODULES = (
    "fastapi", "uvicorn", "langgraph", "langchain", "langchain_core",
    "langchain_openai", "dotenv", "tavily",
)


def check_environment() -> bool:
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.", file=sys.stderr)
        return False
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        print("Missing dependencies: " + ", ".join(missing), file=sys.stderr)
        print(f'Run: "{sys.executable}" -m pip install -r "{ROOT / "requirements.txt"}"', file=sys.stderr)
        return False
    return True


def connection_info() -> tuple[str, int, str]:
    host = os.getenv("DEBATE_STUDIO_HOST", "127.0.0.1")
    port = int(os.getenv("DEBATE_STUDIO_PORT", "8000"))
    if not host or not 1 <= port <= 65535:
        raise ValueError("Set a non-empty DEBATE_STUDIO_HOST and a port between 1 and 65535.")
    connect_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    url_host = f"[{connect_host}]" if ":" in connect_host else connect_host
    return connect_host, port, f"http://{url_host}:{port}"


def server_is_ready(url: str) -> bool:
    # Local readiness checks should not go through a system HTTP proxy.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(url + "/api/health", timeout=1) as response:
            health = json.loads(response.read(65536))
        if not isinstance(health, dict) or health.get("status") != "ok":
            return False
        with opener.open(url + "/openapi.json", timeout=1) as response:
            schema = json.loads(response.read(1024 * 1024))
        info = schema.get("info") if isinstance(schema, dict) else None
        return isinstance(info, dict) and info.get("title") == "LLM Debate Studio"
    except (OSError, ValueError):
        return False


def port_is_busy(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def open_page(url: str) -> None:
    try:
        if webbrowser.open(url):
            return
    except (OSError, webbrowser.Error):
        pass
    print("The browser could not be opened automatically. Open the URL above manually.", flush=True)


def wait_for_ready(process: subprocess.Popen, url: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while not server_is_ready(url):
        if process.poll() is not None:
            raise RuntimeError(f"Server exited before startup (exit code {process.returncode}).")
        if time.monotonic() >= deadline:
            raise RuntimeError("Server did not become ready within 30 seconds. Check the startup errors above.")
        time.sleep(0.25)


def launch(host: str, port: int, url: str, browser: bool = True) -> int:
    if server_is_ready(url):
        print(f"Already running: {url}", flush=True)
        if browser:
            open_page(url)
        return 0
    if port_is_busy(host, port):
        raise RuntimeError(f"Port {port} is occupied by another service. Set DEBATE_STUDIO_PORT to a free port.")

    print(f"Starting LLM Debate Studio: {url}\nPython: {sys.executable}", flush=True)
    process = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=ROOT)
    try:
        wait_for_ready(process, url)
        print(f"Ready: {url}\nKeep this window open. Press Ctrl+C to stop the server.", flush=True)
        if browser:
            open_page(url)
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping the server...", flush=True)
        # Ctrl+C reaches the console child too; give Uvicorn time to shut down.
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check dependencies without starting anything.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically.")
    args = parser.parse_args(argv)
    if not check_environment():
        return 1
    if args.check:
        return 0
    try:
        host, port, url = connection_info()
        return launch(host, port, url, browser=not args.no_browser)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
