"""标题中文化：外文/繁体/超长档案名 → ≤16 字简体中文短标题。

一次 qwen-plus 批量调用处理全部馆藏标题（成本≈几分钱）；任何失败降级为
"清洗原名"（去 .jpg 后缀），绝不抛异常打断调用方（降级铁律）。

产物落 data/processed/titles-zh.json sidecar——不改 Milvus schema、
不重嵌入；Web 层按需合并展示（主标中文、原件可溯）。
"""
import json
import logging
import re
from pathlib import Path

from app.config import Settings
from app.infra import llm_client as lc
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)

_IMG_SUFFIX_RE = re.compile(r"\.(jpe?g|png|webp|avif)$", re.IGNORECASE)

ZH_SYSTEM = (
    "你是博物馆藏品的中文编目员。任务：把【照片档案名清单】里每一条外文、"
    "繁体或冗长啰嗦的老照片档案名，提炼成不超过16个字的简体中文名称。"
    "要求：忠实原意，保留年代、人名、地名等史实要点，不得虚构扩写；"
    "对很长的档案描述做信息提炼而非逐字直译；"
    "已经是规范简体中文短语的条目保持原样（仅去掉书名号外的冗余）。"
    '输出严格 JSON：{"items":[{"pid":"<pid>","zh":"<≤16字简体名>"}]}，'
    "条数与输入一一对应，不得增删。只输出 JSON。"
)


def clean_title(raw: str) -> str:
    """去图片扩展名与首尾空白；空串安全。"""
    return _IMG_SUFFIX_RE.sub("", (raw or "").strip()).strip()


def build_titles_zh(
    rows: list[dict], settings=None, chat=None,
) -> dict[str, str]:
    """rows=[{photo_id,title}] → {pid: 中文名}。

    单次批量 LLM 调用；解析失败/异常时整体降级为清洗原名。
    """
    chat = chat or lc.chat
    s = settings or Settings.load()
    mapping: dict[str, str] = {}
    entries: list[dict] = []
    for r in rows:
        pid = str(r.get("photo_id") or "").strip()
        title = clean_title(str(r.get("title") or ""))
        if not pid or not title:
            continue
        mapping[pid] = title
        entries.append({"pid": pid, "title": title})
    if not entries:
        return {}

    listing = "\n".join(
        f'{i}. {e["pid"]} | {e["title"]}' for i, e in enumerate(entries, start=1)
    )
    try:
        raw = chat(
            [{"role": "system", "content": ZH_SYSTEM},
             {"role": "user",
              "content": f"【照片档案名清单】共{len(entries)}条\n{listing}"}],
            json_mode=True, temperature=0.2, model=s.review_model, settings=s,
        )
        items = (extract_json(raw) or {}).get("items")
        replaced = 0
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            pid = str(it.get("pid") or "").strip()
            zh = str(it.get("zh") or "").strip()
            if pid in mapping and zh:
                mapping[pid] = zh
                replaced += 1
        if replaced == 0:
            logger.warning("标题翻译无有效结果，全部回退清洗原名")
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("标题翻译失败(%s)，回退清洗原名", exc)
    return mapping


def save_titles_zh(mapping: dict[str, str],
                   path: str | Path = "data/processed/titles-zh.json") -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mapping, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def load_titles_zh(path: str | Path = "data/processed/titles-zh.json",
                   ) -> dict[str, str]:
    """读 sidecar；缺失/损坏一律返回 {}（绝不抛）。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()
            if k and isinstance(v, str) and v.strip()}
