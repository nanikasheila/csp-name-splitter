"""Tests for the JSON-RPC bridge module.

Why: The bridge is the critical IPC layer between Tauri and Python.
     Any serialisation bug or dispatch error silently breaks the UI.
How: Spawns bridge.main() in a subprocess, sends JSON-RPC requests
     via stdin, and asserts structured responses from stdout.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _send_rpc(
    proc: subprocess.Popen[str],
    method: str,
    params: dict | None = None,
    request_id: int = 1,
) -> dict:
    """Send a JSON-RPC request and read the response.

    Why: Helper to avoid boilerplate in every test case.
    How: Writes a JSON line to stdin, reads lines from stdout until
         we get a response (skipping progress notifications).
    """
    request = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        request["params"] = params

    assert proc.stdin is not None
    assert proc.stdout is not None

    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()

    while True:
        line = proc.stdout.readline().strip()
        if not line:
            continue
        response = json.loads(line)
        # Why: Skip progress notifications (no id field)
        if "id" in response:
            return response


def _start_bridge() -> subprocess.Popen[str]:
    """Start the bridge process.

    Why: Each test needs a fresh bridge instance.
    How: Runs bridge.py as a module via subprocess.
    """
    return subprocess.Popen(
        [sys.executable, "-m", "name_splitter.bridge"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(_PROJECT_ROOT),
    )


class TestBridgeLoadDefaultConfig(unittest.TestCase):
    def test_returns_valid_config(self) -> None:
        proc = _start_bridge()
        try:
            resp = _send_rpc(proc, "load_default_config")
            self.assertIn("result", resp)
            result = resp["result"]
            self.assertIn("grid", result)
            self.assertIn("output", result)
            self.assertEqual(result["grid"]["rows"], 4)
            self.assertEqual(result["grid"]["cols"], 4)
        finally:
            proc.terminate()
            proc.wait()


class TestBridgeReadImage(unittest.TestCase):
    def test_reads_valid_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "test.png"
            Image.new("RGB", (200, 300)).save(img_path)

            proc = _start_bridge()
            try:
                resp = _send_rpc(proc, "read_image", {"path": str(img_path)})
                self.assertIn("result", resp)
                self.assertEqual(resp["result"]["width"], 200)
                self.assertEqual(resp["result"]["height"], 300)
            finally:
                proc.terminate()
                proc.wait()

    def test_returns_error_for_missing_file(self) -> None:
        proc = _start_bridge()
        try:
            resp = _send_rpc(proc, "read_image", {"path": "/nonexistent.png"})
            self.assertIn("error", resp)
            self.assertEqual(resp["error"]["code"], -32002)
        finally:
            proc.terminate()
            proc.wait()


class TestBridgeBuildPreview(unittest.TestCase):
    def test_returns_base64_jpeg(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "test.png"
            Image.new("RGB", (400, 600)).save(img_path)

            proc = _start_bridge()
            try:
                resp = _send_rpc(proc, "build_preview", {
                    "image_path": str(img_path),
                    "grid_config": {"rows": 2, "cols": 2, "dpi": 300},
                    "max_dim": 400,
                })
                self.assertIn("result", resp)
                b64 = resp["result"]["image_base64"]
                self.assertIsInstance(b64, str)
                self.assertGreater(len(b64), 100)
            finally:
                proc.terminate()
                proc.wait()


class TestBridgeGetPageSizes(unittest.TestCase):
    def test_returns_known_sizes(self) -> None:
        proc = _start_bridge()
        try:
            resp = _send_rpc(proc, "get_page_sizes")
            self.assertIn("result", resp)
            names = [s["name"] for s in resp["result"]["sizes"]]
            self.assertIn("A4", names)
            self.assertIn("B5", names)
            self.assertIn("Custom", names)
        finally:
            proc.terminate()
            proc.wait()


class TestBridgeRunJob(unittest.TestCase):
    def test_splits_image_and_returns_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "test.png"
            Image.new("RGB", (800, 1200)).save(img_path)
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()

            proc = _start_bridge()
            try:
                assert proc.stdin is not None
                assert proc.stdout is not None

                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "run_job",
                    "params": {
                        "image_path": str(img_path),
                        "config": {
                            "grid": {"rows": 2, "cols": 2, "dpi": 300},
                            "output": {"out_dir": str(out_dir), "container": "png"},
                        },
                        "out_dir": str(out_dir),
                    },
                }
                proc.stdin.write(json.dumps(request) + "\n")
                proc.stdin.flush()

                progress_count = 0
                final_response = None

                while True:
                    line = proc.stdout.readline().strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    if "id" in msg:
                        final_response = msg
                        break
                    if msg.get("method") == "progress":
                        progress_count += 1

                self.assertIsNotNone(final_response)
                self.assertIn("result", final_response)
                self.assertGreater(final_response["result"]["page_count"], 0)
                self.assertGreater(progress_count, 0)
            finally:
                proc.terminate()
                proc.wait()


class TestBridgeCancelJob(unittest.TestCase):
    def test_cancel_returns_ok(self) -> None:
        proc = _start_bridge()
        try:
            resp = _send_rpc(proc, "cancel_job")
            self.assertIn("result", resp)
            self.assertTrue(resp["result"]["ok"])
        finally:
            proc.terminate()
            proc.wait()


class TestBridgeMethodNotFound(unittest.TestCase):
    def test_unknown_method_returns_error(self) -> None:
        proc = _start_bridge()
        try:
            resp = _send_rpc(proc, "nonexistent_method")
            self.assertIn("error", resp)
            self.assertEqual(resp["error"]["code"], -32601)
        finally:
            proc.terminate()
            proc.wait()


class TestBridgeInvalidJson(unittest.TestCase):
    def test_malformed_json_returns_parse_error(self) -> None:
        proc = _start_bridge()
        try:
            assert proc.stdin is not None
            assert proc.stdout is not None
            proc.stdin.write("not-valid-json\n")
            proc.stdin.flush()
            line = proc.stdout.readline().strip()
            resp = json.loads(line)
            self.assertIn("error", resp)
            self.assertEqual(resp["error"]["code"], -32700)
        finally:
            proc.terminate()
            proc.wait()


if __name__ == "__main__":
    unittest.main()
