# 叙事质量评测：LLM judge 四维 + 确定性禁用词统计。
import json
import logging
from pathlib import Path

from app.config import Settings
from app.infra import llm_client as lc
from app.narrator import detox as d

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = (
    "你是叙事质量评审。对照给定故事与粤语旁白，输出严格 JSON："
    '{"factual_score":0~1,"taste_score":0~1,"hook_score":0~1,'
    '"yue_score":0~1,"comment":"一段话"}。'
    "factual=是否仅在照片可见范围内；taste=去AI味/无套话；"
    "hook=开头抓人/结尾余韵；yue=粤语口语自然度。只输出 JSON。"
)


def run_narrative_eval(rows, settings=None, chat=None):
    chat = chat or lc.chat
    s = settings or Settings.load()
    per_row = []
    agg = {"factual_score": 0.0, "taste_score": 0.0, "hook_score": 0.0,
           "yue_score": 0.0, "banned_hits": 0}
    n = max(len(rows), 1)
    for r in rows:
        banned = d.scan_ai_smell(r.get("story", ""))
        agg["banned_hits"] += len(banned)
        try:
            raw = chat([{"role": "system", "content": JUDGE_SYSTEM},
                        {"role": "user", "content":
                            f"【故事】{r.get('story','')}\n【旁白】{r.get('narration','')}"}],
                       json_mode=True, temperature=0.2, model=s.review_model, settings=s)
            obj = json.loads(raw) if raw.strip().startswith("{") else {}
            scores = {k: float(obj.get(k, 0.0)) for k in
                      ("factual_score", "taste_score", "hook_score", "yue_score")}
        except Exception as exc:  # noqa: BLE001
            logger.warning("judge 失败，该行计 0: %s", exc)
            scores = {"factual_score": 0.0, "taste_score": 0.0,
                      "hook_score": 0.0, "yue_score": 0.0}
        for k, v in scores.items():
            agg[k] += v
        per_row.append({"pid": r.get("pid"), **scores,
                        "banned_hits": len(banned)})
    for k in ("factual_score", "taste_score", "hook_score", "yue_score"):
        agg[k] = round(agg[k] / n, 3)
    return {"per_row": per_row, "aggregate": agg}


def save_report(result, out="eval/reports/narrative_eval.json"):
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p
