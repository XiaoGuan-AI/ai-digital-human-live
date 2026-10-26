"""等待某个本地端口就绪（给 live.cmd 用，替代盲等 45 秒）。

用法: python tools/wait_port.py 8010 90      # 最多等 90 秒
退出码: 0=就绪, 1=超时
"""
from __future__ import annotations

import socket
import sys
import time


def ready(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
    limit = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    t0 = time.time()
    while time.time() - t0 < limit:
        if ready(port):
            print(f"port {port} ready in {time.time() - t0:.0f}s")
            return 0
        time.sleep(1.5)
    print(f"port {port} NOT ready after {limit:.0f}s")
    return 1


if __name__ == "__main__":
    sys.exit(main())
