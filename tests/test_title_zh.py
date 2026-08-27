"""标题中文化单测：清洗 / 批量翻译(含降级) / sidecar 读写。"""
import json

import pytest

from app.ingest.title_zh import (
    build_titles_zh, clean_title, load_titles_zh, save_titles_zh,
)


ROWS = [
    {"photo_id": "a", "title": "Canton in the 1850-60s.jpg"},
    {"photo_id": "b", "title": "Godowns in Honam.jpg"},
    {"photo_id": "c", "title": "1919廣東省運會.jpg"},
]

RAW_OK = json.dumps({
    "items": [
        {"pid": "a", "zh": "十九世纪五十年代的广州"},
        {"pid": "b", "zh": "河南岛货栈"},
        {"pid": "c", "zh": "1919年广东省运动会"},
    ]}, ensure_ascii=False)


class ChatOK:
    def __call__(self, messages, json_mode=False, temperature=None,
                 model=None, settings=None):
        return RAW_OK


class ChatBoom:
    def __call__(self, *a, **k):
        raise RuntimeError("llm down")


def test_clean_title_strips_suffix_and_space():
    assert clean_title(" Boat Life from Bund Canton.JPG ") == \
        "Boat Life from Bund Canton"
    assert clean_title("x.png") == "x"
    assert clean_title("") == ""


def test_build_maps_llm_results_and_keeps_unknown_pid():
    mapping = build_titles_zh(ROWS, chat=ChatOK())
    assert mapping["a"] == "十九世纪五十年代的广州"
    assert mapping["b"] == "河南岛货栈"
    # LLM 返回了未知 pid 时不得越权写入
    assert set(mapping) == {"a", "b", "c"}


def test_build_degrades_to_clean_titles_on_llm_failure():
    mapping = build_titles_zh(ROWS, chat=ChatBoom())
    assert mapping["a"] == "Canton in the 1850-60s"


def test_build_empty_rows_returns_empty():
    assert build_titles_zh([], chat=ChatOK()) == {}


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "titles-zh.json"
    save_titles_zh({"a": "骑楼"}, p)
    assert load_titles_zh(p) == {"a": "骑楼"}


def test_load_broken_file_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not-json{", encoding="utf-8")
    assert load_titles_zh(p) == {}
    assert load_titles_zh(tmp_path / "missing.json") == {}


def test_uses_review_model_keyword():
    seen = {}

    class Spy:
        def __call__(self, messages, **kw):
            seen.update(kw)
            return RAW_OK

    build_titles_zh(ROWS, chat=Spy())
    assert seen.get("model") is not None
