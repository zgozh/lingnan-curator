"""T8 冒烟脚本：对运行中的展馆服务做端到端验证。

用法：先起服务 `uv run uvicorn app.web.main:app --port 8301`，
再 `uv run python scripts/smoke_web.py [base_url]`
"""
import json
import sys
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8301"


def get(path: str, timeout: int = 60):
    r = urllib.request.urlopen(BASE + path, timeout=timeout)
    return r.status, r.read().decode("utf-8", "ignore")


def post_json(path: str, payload: dict, timeout: int = 90):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req, timeout=timeout)
    return r.status, r.read().decode("utf-8", "ignore"), r.headers


def main() -> None:
    checks: list[tuple[str, bool]] = []

    status, body = get("/api/health")
    checks.append(("health 200", status == 200))
    print("[1] /api/health ->", status, body[:80])

    status, body = get("/")
    checks.append(("首页照片墙", status == 200))

    q = urllib.parse.quote("骑楼")
    status, body = get(f"/search?q={q}")
    hit = "sample_a" in body
    checks.append(("场景1 搜索'骑楼'命中 sample_a", status == 200 and hit))
    print("[3] /search?q=骑楼 ->", status, "hit sample_a =", hit)

    status, body = get("/photo/sample_a")
    checks.append(("详情页含 OCR 区块", status == 200 and "OCR" in body))
    print("[4] /photo/sample_a ->", status)

    status, body, _ = post_json(
        "/api/ask", {"q": "2025年广州地铁有多少条线路"})
    refused = '"refused": true' in body or '"refused":true' in body
    checks.append((f"场景2后半 超范围拒答(SSE {status})", refused))
    print("[5] ask 超范围 ->", status, "refused =", refused)

    ok = all(c for _, c in checks)
    print("\n=== SMOKE", "PASS" if ok else "FAIL", "===")
    for name, passed in checks:
        print(("  [OK] " if passed else "  [NG] "), name)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
