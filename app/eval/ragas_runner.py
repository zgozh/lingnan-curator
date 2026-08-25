"""F8 RAGAS 适配器：评测行 → ragas.evaluate → 指标 dict。

重依赖（ragas/datasets/langchain）全部懒加载，单测打桩 _evaluate。
LLM/Embeddings 走 DashScope OpenAI 兼容端点。
"""
import logging

logger = logging.getLogger(__name__)

_METRIC_KEYS = ("faithfulness", "answer_relevancy")
_EMBED_MODEL = "text-embedding-v3"


def _evaluate(dataset, metrics=None, llm=None, embeddings=None, **kw):
    """seam：真实 evaluate 入口，测试替换此函数。"""
    from ragas import evaluate

    return evaluate(dataset, metrics=metrics, llm=llm,
                    embeddings=embeddings, **kw)


def _shim_removed_langchain_modules() -> None:
    """ragas 0.3.1 顶层 import 已被新版 langchain-community 移除的
    vertexai 模块——注入空壳防崩；真实链路只用 OpenAI 包装器。"""
    import importlib
    import sys
    import types

    name = "langchain_community.chat_models.vertexai"
    try:
        importlib.import_module(name)
    except Exception:  # noqa: BLE001 —— 模块已被上游移除属预期
        if name not in sys.modules:
            stub = types.ModuleType(name)
            stub.ChatVertexAI = type("ChatVertexAI", (), {})
            sys.modules[name] = stub


def run_ragas(rows: list[dict], settings=None) -> dict:
    _shim_removed_langchain_modules()
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas.metrics import answer_relevancy, faithfulness

    from app.config import Settings

    s = settings or Settings.load()
    data = [{"question": r["question"], "answer": r["answer"],
             # 空 contexts 会崩 RAGAS 的指标计算，给占位串
             "contexts": r.get("contexts") or ["（无检索证据）"]}
            for r in rows]
    ds = Dataset.from_list(data)

    common = {"api_key": s.dashscope_api_key,
              "base_url": s.dashscope_base_url}
    llm = ChatOpenAI(model=s.llm_model, temperature=0, **common)
    # 关键：关掉 tiktoken 预切分，否则发给 DashScope 的是 token 数组而非字符串
    emb = OpenAIEmbeddings(model=_EMBED_MODEL,
                           check_embedding_ctx_length=False, **common)

    result = _evaluate(ds, metrics=[faithfulness, answer_relevancy],
                       llm=llm, embeddings=emb)
    scores = _extract_scores(result)
    logger.info("RAGAS 指标: %s", scores)
    return scores


def _extract_scores(result) -> dict:
    """兼容两种返回形态：EvaluationDataset(.scores 列表) / 平面映射。"""
    import statistics

    if hasattr(result, "scores"):
        row_list = list(result.scores)
        out = {}
        for k in _METRIC_KEYS:
            vals = [float(r[k]) for r in row_list
                    if isinstance(r, dict) and k in r]
            if vals:
                out[k] = statistics.mean(vals)
        return out
    return {k: float(result[k]) for k in _METRIC_KEYS if k in result}
