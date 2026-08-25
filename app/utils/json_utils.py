"""通用 JSON 防御解析：从模型自由文本中截取首个完整 JSON 对象。"""

import json


def extract_json(text: str):
    """取第一个 '{' 到最后一个 '}' 之间的内容尝试解析；失败返回 None。"""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
