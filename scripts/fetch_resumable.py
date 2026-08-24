"""断点续传抓取器：对不稳定 CDN（GitHub releases 等）用 Range 循环补齐。

用法：python scripts/fetch_resumable.py <url> <dest_path>
"""
import sys
import time
import urllib.request
from pathlib import Path


def fetch(url: str, dest: str, tries: int = 15) -> bool:
    d = Path(dest)
    d.parent.mkdir(parents=True, exist_ok=True)
    have = d.stat().st_size if d.exists() else 0
    total: int | None = None
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url)
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                if have and getattr(r, "status", 200) != 206:
                    # 服务器不支持 Range：丢弃旧前缀重来
                    have = 0
                clen = r.headers.get("Content-Length")
                if clen:
                    total = int(clen) + have
                mode = "ab" if have else "wb"
                with open(d, mode) as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
                        pct = f"/{total / 1e6:.0f}MB" if total else ""
                        print(f"\r  {have / 1e6:.0f}MB{pct}", end="", flush=True)
            if total and have < total:
                # 连接提前关闭：不算完成，继续断点续传
                print(f"\n  incomplete {have}/{total}，续传…", flush=True)
                time.sleep(min(3 * attempt, 15))
                continue
            print(f"\n  done {d.name} {have:,}B")
            return True
        except Exception as exc:  # noqa: BLE001 —— 网络循环重试边界
            print(f"\n  retry {attempt}/{tries}: "
                  f"{type(exc).__name__} {str(exc)[:60]}", flush=True)
            time.sleep(min(3 * attempt, 15))
    return False


if __name__ == "__main__":
    ok = fetch(sys.argv[1], sys.argv[2])
    raise SystemExit(0 if ok else 1)
