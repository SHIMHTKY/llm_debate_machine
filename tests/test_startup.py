"""Launcher regressions without starting the real backend or opening a browser."""

import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location("studio_startup", Path(__file__).resolve().parents[1] / "scripts" / "start.py")
startup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(startup)


class StartupTests(unittest.TestCase):
    def test_wildcard_and_ipv6_addresses_produce_browser_urls(self):
        for host, expected in (("0.0.0.0", "http://127.0.0.1:8123"), ("::", "http://[::1]:8123")):
            with self.subTest(host=host), patch.dict(os.environ, {"DEBATE_STUDIO_HOST": host, "DEBATE_STUDIO_PORT": "8123"}):
                self.assertEqual(startup.connection_info()[2], expected)

    def test_invalid_port_is_rejected(self):
        for value in ("0", "65536", "invalid"):
            with self.subTest(port=value), patch.dict(os.environ, {"DEBATE_STUDIO_PORT": value}):
                with self.assertRaises(ValueError):
                    startup.connection_info()

    def test_check_mode_does_not_connect_or_start_server(self):
        with patch.object(startup, "check_environment", return_value=True), patch.object(startup, "launch") as launch:
            self.assertEqual(startup.main(["--check"]), 0)
            launch.assert_not_called()

    def test_reuses_existing_server_without_spawning(self):
        with patch.object(startup, "server_is_ready", return_value=True), patch.object(startup, "open_page") as browser, patch.object(startup.subprocess, "Popen") as spawn:
            self.assertEqual(startup.launch("127.0.0.1", 8000, "http://127.0.0.1:8000"), 0)
            spawn.assert_not_called()
            browser.assert_called_once()

    def test_foreign_service_is_not_reused(self):
        with patch.object(startup, "server_is_ready", return_value=False), patch.object(startup, "port_is_busy", return_value=True), patch.object(startup.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "occupied"):
                startup.launch("127.0.0.1", 8000, "http://127.0.0.1:8000")
            spawn.assert_not_called()

    def test_health_ok_alone_cannot_identify_studio(self):
        health, schema = Mock(), Mock()
        health.__enter__ = Mock(return_value=io.BytesIO(b'{"status":"ok"}'))
        health.__exit__ = Mock(return_value=False)
        schema.__enter__ = Mock(return_value=io.BytesIO(b'{"info":{"title":"Unrelated API"}}'))
        schema.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = [health, schema]
        with patch.object(startup, "build_opener", return_value=opener):
            self.assertFalse(startup.server_is_ready("http://127.0.0.1:8000"))

    def test_readiness_checks_actual_http_and_handles_malformed_schema(self):
        class Handler(BaseHTTPRequestHandler):
            schema = {"info": {"title": "LLM Debate Studio"}}

            def do_GET(self):
                payload = {"status": "ok"} if self.path == "/api/health" else self.schema
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                self.assertTrue(startup.port_is_busy("127.0.0.1", server.server_port))
                self.assertTrue(startup.server_is_ready(url))
                Handler.schema = {"info": []}
                self.assertFalse(startup.server_is_ready(url))
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_opens_browser_only_after_startup(self):
        process = Mock()
        process.poll.return_value = 0
        process.wait.return_value = 0
        order = []
        with patch.object(startup, "server_is_ready", return_value=False), patch.object(startup, "port_is_busy", return_value=False), patch.object(startup.subprocess, "Popen", return_value=process) as spawn, patch.object(startup, "wait_for_ready", side_effect=lambda *_: order.append("ready")), patch.object(startup, "open_page", side_effect=lambda *_: order.append("browser")):
            self.assertEqual(startup.launch("127.0.0.1", 8000, "http://127.0.0.1:8000"), 0)
            self.assertEqual(order, ["ready", "browser"])
            self.assertEqual(spawn.call_args.kwargs["cwd"], startup.ROOT)

    def test_startup_timeout_cleans_up_spawned_process(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.return_value = 0
        with patch.object(startup, "server_is_ready", return_value=False), patch.object(startup, "port_is_busy", return_value=False), patch.object(startup.subprocess, "Popen", return_value=process), patch.object(startup, "wait_for_ready", side_effect=RuntimeError("timeout")), patch.object(startup, "open_page") as browser:
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                startup.launch("127.0.0.1", 8000, "http://127.0.0.1:8000")
            process.terminate.assert_called_once()
            browser.assert_not_called()

    def test_failed_child_is_reported_without_polling_forever(self):
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1
        with patch.object(startup, "server_is_ready", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "exit code 1"):
                startup.wait_for_ready(process, "http://127.0.0.1:8000")

    def test_keyboard_interrupt_waits_for_graceful_shutdown(self):
        process = Mock()
        process.poll.return_value = 0
        process.wait.side_effect = [KeyboardInterrupt(), 0]
        with patch.object(startup, "server_is_ready", return_value=False), patch.object(startup, "port_is_busy", return_value=False), patch.object(startup.subprocess, "Popen", return_value=process), patch.object(startup, "wait_for_ready"), patch.object(startup, "open_page"):
            self.assertEqual(startup.launch("127.0.0.1", 8000, "http://127.0.0.1:8000"), 0)
            process.terminate.assert_not_called()
            self.assertEqual(process.wait.call_args.kwargs, {"timeout": 5})


if __name__ == "__main__":
    unittest.main()
