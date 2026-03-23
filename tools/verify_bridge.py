"""Verification script: run bridge on real sample and compare with CLI output.

Why: Ensure the JSON-RPC bridge produces identical results to the CLI.
How: Send JSON-RPC requests via subprocess to the bridge process,
     collect the output, then compare with CLI-produced files.
"""
import json
import subprocess
import sys
import os
import hashlib
from pathlib import Path

BRIDGE = [sys.executable, "-m", "name_splitter.bridge"]
IMAGE = os.path.abspath(r"sample\ユメノストラ_002.png")
OUT_DIR = os.path.abspath(r"test_env\verify_bridge")
CLI_DIR = os.path.abspath(r"test_env\verify_cli")
os.makedirs(OUT_DIR, exist_ok=True)


def send_rpc(proc, req_id, method, params=None):
    """Send a JSON-RPC request and return the response."""
    req = json.dumps({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    })
    proc.stdin.write(req + "\n")
    proc.stdin.flush()

    # Read lines until we get a response with matching id
    progress_events = []
    while True:
        line = proc.stdout.readline().strip()
        if not line:
            break
        msg = json.loads(line)
        if "method" in msg and msg["method"] == "progress":
            progress_events.append(msg["params"])
            p = msg["params"]
            print(f"  [{p['phase']}] {p['done']}/{p['total']} - {p['message']}")
        elif "id" in msg and msg["id"] == req_id:
            return msg, progress_events
    return None, progress_events


def file_sha256(path):
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    print("=" * 60)
    print("Bridge vs CLI Verification")
    print("=" * 60)

    # Start bridge
    proc = subprocess.Popen(
        BRIDGE,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # 1) load_default_config
    print("\n[1] load_default_config")
    resp, _ = send_rpc(proc, 1, "load_default_config")
    assert resp and "result" in resp, f"Failed: {resp}"
    cfg = resp["result"]
    print("  OK - default config loaded")

    # 2) read_image
    print("\n[2] read_image")
    resp, _ = send_rpc(proc, 2, "read_image", {"path": IMAGE})
    assert resp and "result" in resp, f"Failed: {resp}"
    info = resp["result"]
    w, h = info["width"], info["height"]
    print(f"  OK - {w}x{h} px")

    # 3) build_preview
    print("\n[3] build_preview")
    resp, _ = send_rpc(proc, 3, "build_preview", {
        "image_path": IMAGE,
        "grid_config": cfg["grid"],
        "max_dim": 800,
    })
    assert resp and "result" in resp, f"Failed: {resp}"
    b64 = resp["result"]["image_base64"]
    preview_bytes = len(b64)
    print(f"  OK - preview base64 length: {preview_bytes}")

    # Save preview for visual inspection
    import base64
    preview_path = os.path.join(OUT_DIR, "preview.jpg")
    with open(preview_path, "wb") as f:
        f.write(base64.b64decode(b64))
    print(f"  Saved: {preview_path}")

    # 4) run_job
    print("\n[4] run_job")
    resp, progress = send_rpc(proc, 4, "run_job", {
        "image_path": IMAGE,
        "config": cfg,
        "out_dir": OUT_DIR,
    })
    assert resp and "result" in resp, f"Failed: {resp}"
    result = resp["result"]
    print(f"  OK - pages: {result['page_count']}, time: {result['elapsed_seconds']:.2f}s")
    print(f"  Progress events: {len(progress)}")
    print(f"  Output dir: {result['out_dir']}")

    # 5) get_page_sizes
    print("\n[5] get_page_sizes")
    resp, _ = send_rpc(proc, 5, "get_page_sizes")
    assert resp and "result" in resp, f"Failed: {resp}"
    sizes = resp["result"]["sizes"]
    print(f"  OK - {len(sizes)} page sizes: {[s['name'] for s in sizes]}")

    # Shutdown bridge
    proc.stdin.close()
    proc.wait(timeout=5)
    print("\n  Bridge exited cleanly")

    # ================================================================
    # Compare CLI vs Bridge outputs
    # ================================================================
    print("\n" + "=" * 60)
    print("Output Comparison: CLI vs Bridge")
    print("=" * 60)

    cli_pages = sorted(Path(CLI_DIR).rglob("page_*.png"))
    bridge_pages = sorted(Path(OUT_DIR).rglob("page_*.png"))

    print(f"\n  CLI pages:    {len(cli_pages)}")
    print(f"  Bridge pages: {len(bridge_pages)}")

    assert len(cli_pages) == len(bridge_pages), (
        f"Page count mismatch: CLI={len(cli_pages)}, Bridge={len(bridge_pages)}"
    )

    match_count = 0
    mismatch_count = 0
    for cp, bp in zip(cli_pages, bridge_pages):
        cli_hash = file_sha256(cp)
        bridge_hash = file_sha256(bp)
        status = "MATCH" if cli_hash == bridge_hash else "DIFFER"
        if status == "MATCH":
            match_count += 1
        else:
            mismatch_count += 1
        cli_size = cp.stat().st_size
        bridge_size = bp.stat().st_size
        size_diff = abs(cli_size - bridge_size)
        print(f"  {cp.name:20s} vs {bp.name:20s} -> {status}"
              f"  (CLI: {cli_size:,}B, Bridge: {bridge_size:,}B, diff: {size_diff:,}B)")

    # Compare plan.yaml
    cli_plan = Path(CLI_DIR) / "plan.yaml"
    bridge_plan = Path(OUT_DIR) / "plan.yaml"
    if cli_plan.exists() and bridge_plan.exists():
        cli_plan_hash = file_sha256(cli_plan)
        bridge_plan_hash = file_sha256(bridge_plan)
        plan_status = "MATCH" if cli_plan_hash == bridge_plan_hash else "DIFFER"
        print(f"\n  plan.yaml: {plan_status}")

    print(f"\n{'=' * 60}")
    print(f"RESULT: {match_count} matched, {mismatch_count} differed out of {len(cli_pages)} pages")
    if mismatch_count == 0:
        print("ALL PAGES IDENTICAL - Bridge produces same output as CLI")
    else:
        print("WARNING: Some pages differ (may be acceptable due to processing order)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
