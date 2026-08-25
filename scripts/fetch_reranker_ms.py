"""从 ModelScope 拉 Qwen3-Reranker-0.6B（hf-mirror 被掐时的备用源）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.fetch_resumable import fetch  # noqa: E402

BASE = "https://modelscope.cn/models/Qwen/Qwen3-Reranker-0.6B/resolve/master"
FILES = [
    "config.json",
    "generation_config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
]

DEST = Path("models/hub-local/qwen3-reranker-0.6b")


def main() -> None:
    ok_all = True
    for name in FILES:
        dest = DEST / name
        print(f"[fetch] {name}")
        if not fetch(f"{BASE}/{name}", str(dest)):
            ok_all = False
            print(f"[FAIL] {name}")
    print("ALL OK" if ok_all else "PARTIAL FAIL")
    raise SystemExit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
