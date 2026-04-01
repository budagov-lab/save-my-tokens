"""Test that the MCP server can start up without errors."""

import subprocess
import time
import signal
import sys


def test_server_starts():
    """Test that the MCP server starts without crashing."""
    # Start the server as a subprocess
    proc = subprocess.Popen(
        [sys.executable, "run_mcp.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Give it a moment to start
    time.sleep(0.5)

    # If it's still running, that's good (no immediate crash)
    if proc.poll() is None:
        # Kill it gracefully
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        assert True  # Server started successfully
    else:
        # Server crashed immediately
        stdout, stderr = proc.communicate()
        assert False, f"Server failed to start. Stderr: {stderr}"
