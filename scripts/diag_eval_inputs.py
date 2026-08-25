"""诊断：逐题打印 docent.ask 的 refused/photo_ids/contexts 健康度。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json  # noqa: E402

from app.agents.docent import ask  # noqa: E402


def main() -> None:
    rows = [json.loads(l) for l in
            Path("eval/questions.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    from app.cli import _contexts
    for q in rows:
        res = ask(q["question"])
        ctx = _contexts(res.get("photo_ids") or [])
        print(f"{q['qid']} expect_refusal={q['refusal']} "
              f"refused={res.get('refused')} pids={res.get('photo_ids')} "
              f"ctx_len={sum(len(c) for c in ctx)}")
        if not q["refusal"]:
            print(f"   A: {res.get('answer', '')[:70]}")


if __name__ == "__main__":
    main()
