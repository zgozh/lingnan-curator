"""qwen3-rerank 本地精排服务：/rerank + /health（F2 门面的对端）。

用法（主 venv）：
  uv run uvicorn scripts.rerank_server:app --port 8302
模型：BAAI/Qwen3-Reranker-0.6B → models/hub-local/qwen3-reranker-0.6b
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import FastAPI

logger = logging.getLogger(__name__)

MODEL_DIR = Path("models/hub-local/qwen3-reranker-0.6b")
_PREFIX = ('<|im_start|>system\nJudge whether the Document meets the '
           'requirements based on the Query and the Instruction provided.'
           ' Note that the answer can only be "yes" or "no".'
           '<|im_end|>\n<|im_start|>user\n')
_SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'

_model = None
_tokenizer = None
_device = None


def _load():
    global _model, _tokenizer, _device
    if _model is not None:
        return
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if _device == "cuda" else torch.float32
    _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    _model = AutoModelForCausalLM.from_pretrained(
        str(MODEL_DIR), torch_dtype=dtype).to(_device).eval()
    logger.info("rerank 模型加载完成: %s device=%s", MODEL_DIR, _device)


def _score_batch(query: str, docs: list[str]) -> list[float]:
    """整批一次前向：padding 对齐后取末 token yes/no softmax。"""
    import torch

    texts = [
        f"{_PREFIX}<Instruction>: 无\n<Query>: {query}\n"
        f"<Document>: {d}{_SUFFIX}" for d in docs
    ]
    inputs = _tokenizer(texts, return_tensors="pt", padding=True,
                        truncation=True, max_length=2048).to(_model.device)
    with torch.no_grad():
        logits = _model(**inputs).logits[:, -1, :]
    yes_id = _tokenizer.convert_tokens_to_ids("yes")
    no_id = _tokenizer.convert_tokens_to_ids("no")
    two = torch.stack([logits[:, yes_id], logits[:, no_id]], dim=1).float()
    return torch.softmax(two, dim=1)[:, 0].tolist()


app = FastAPI(title="qwen3-rerank")


@app.get("/health")
def health():
    try:
        _load()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:120]}


@app.post("/rerank")
def rerank(body: dict):
    query = str(body.get("query") or "")
    docs = [str(d) for d in (body.get("documents") or [])]
    if not docs:
        return {"scores": []}
    _load()
    return {"scores": _score_batch(query, docs)}
