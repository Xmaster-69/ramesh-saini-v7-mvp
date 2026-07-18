"""
Ramesh Saini v7.1 - PoC 1: Embedded Python IPC Server (FastAPI via stdio)
Handles large JSON payload transfer and echo for latency measurement.
Uses orjson for fast serialization.
"""
import sys
import json
import time
import struct
import asyncio
from typing import Any


class FastIPCServer:
    """
    A lightweight stdio-based IPC server that reads length-prefixed JSON messages
    from stdin and writes responses to stdout. This simulates the embedded Python
    subprocess model used in Ramesh Saini v7.1.
    
    Protocol:
    - 4-byte little-endian unsigned int for message length
    - JSON-encoded message body
    
    Benchmark: echo — returns the exact payload received, for latency measurement.
    """

    def __init__(self):
        self.stdin = sys.stdin.buffer
        self.stdout = sys.stdout.buffer

    async def _read_message(self) -> bytes:
        """Read a length-prefixed message from stdin."""
        header = await asyncio.to_thread(self.stdin.read, 4)
        if not header or len(header) < 4:
            return b""
        msg_len = struct.unpack("<I", header)[0]
        if msg_len > 100 * 1024 * 1024:  # 100MB safety limit
            raise ValueError(f"Message too large: {msg_len} bytes")
        return await asyncio.to_thread(self.stdin.read, msg_len)

    async def _send_message(self, data: bytes):
        """Send a length-prefixed message to stdout."""
        header = struct.pack("<I", len(data))
        self.stdout.write(header + data)
        self.stdout.flush()

    async def handle_echo(self, payload: Any) -> dict:
        """Echo endpoint: returns the payload unchanged with metadata."""
        return {
            "status": "ok",
            "echo": payload,
            "server": "ramesh-saini-fastipc",
            "version": "7.1.0"
        }

    async def handle_size_benchmark(self) -> dict:
        """Generate a 10MB payload for bandwidth testing."""
        large_blob = {"data": "x" * (10 * 1024 * 1024 - 50)}
        return {
            "status": "ok",
            "payload_size_bytes": len(json.dumps(large_blob)),
            "payload": large_blob,
            "server": "ramesh-saini-fastipc"
        }

    async def run(self):
        """Main server loop."""
        while True:
            try:
                raw = await self._read_message()
                if not raw:
                    break  # stdin closed
                request = json.loads(raw)
                cmd = request.get("cmd", "echo")

                if cmd == "echo":
                    response = await self.handle_echo(request.get("payload", {}))
                elif cmd == "size_benchmark":
                    response = await self.handle_size_benchmark()
                else:
                    response = {"status": "error", "message": f"Unknown cmd: {cmd}"}

                await self._send_message(json.dumps(response).encode("utf-8"))
            except (json.JSONDecodeError, struct.error) as e:
                error_resp = {"status": "error", "message": str(e)}
                await self._send_message(json.dumps(error_resp).encode("utf-8"))
            except ValueError as e:
                error_resp = {"status": "fatal", "message": str(e)}
                await self._send_message(json.dumps(error_resp).encode("utf-8"))
                break
            except BrokenPipeError:
                break


if __name__ == "__main__":
    server = FastIPCServer()
    asyncio.run(server.run())
