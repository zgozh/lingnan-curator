"""逐行诊断：每道应答题的 faithfulness/relevancy 明细。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.docent import ask  # noqa: E402
from app.cli import _contexts  # noqa: E402
from app.eval.ragas_runner import _evaluate, _shim_removed_langchain_modules  # noqa: E402


def main() -> None:
    _shim_removed_langchain_modules()
    from datasets import Dataset
    from langchain_openai import ChatOpenAI
    from ragas.metrics import answer_relevancy, faithfulness

    from app.config import Settings

    s = Settings.load()
    rows = [json.loads(l) for l in
            Path("eval/questions.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    data = []
    for q in rows:
        if q["refusal"]:
            continue
        res = ask(q["question"])
        if res.get("refused"):
            print(f"{q['qid']} REFUSED by docent")
            continue
        ctx = _contexts(res.get("photo_ids") or [])
        data.append({"question": q["question"], "answer": res["answer"],
                     "contexts": ctx or ["（无）"]})
    ds = Dataset.from_list(data)
    llm = ChatOpenAI(model=s.llm_model, temperature=0,
                     api_key=s.dashscope_api_key,
                     base_url=s.dashscope_base_url)
    from app.eval.ragas_runner import _EMBED_MODEL

    from langchain_openai import OpenAIEmbeddings

    emb = OpenAIEmbeddings(model=_EMBED_MODEL,
                           check_embedding_ctx_length=False,
                           api_key=s.dashscope_api_key,
                           base_url=s.dashscope_base_url)
    result = _evaluate(ds, metrics=[faithfulness, answer_relevancy],
                       llm=llm, embeddings=emb)
    for i, row_scores in enumerate(result.scores):
        print(f"row{i} f={row_scores.get('faithfulness')} "
              f"r={row_scores.get('answer_relevancy', 0):.2f} "
              f"Q={data[i]['question'][:22]} "
              f"A={data[i]['answer'][:36]}")


if __name__ == "__main__":
    main()
