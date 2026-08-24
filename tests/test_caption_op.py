"""Task 5 RED：VLM caption 节点——JSON 解析/代码围栏清洗/异常与脏输出降级。"""
from pathlib import Path

from app.ingest.caption_op import Caption, caption_photo, fallback_caption
from app.models import PhotoRecord


def _rec() -> PhotoRecord:
    return PhotoRecord(
        photo_id="a1", title="骑楼街景", year="1930", location="广州",
        source_url="http://x", license="PD",
    )


class FakeClient:
    def __init__(self, text: str | Exception):
        self.text = text

    def describe(self, image_path, user_prompt):
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


def _img(tmp_path: Path) -> Path:
    p = tmp_path / "a.jpg"
    p.write_bytes(b"fake-jpeg")
    return p


def test_parses_clean_json(tmp_path):
    cap = caption_photo(
        _img(tmp_path), _rec(),
        client=FakeClient('{"description": "三层砖木骑楼", "tags": ["骑楼", "广州"]}'),
    )
    assert cap.description == "三层砖木骑楼"
    assert cap.tags == ["骑楼", "广州"]
    assert cap.model != "fallback"


def test_strips_markdown_code_fence(tmp_path):
    raw = '```json\n{"description": "老照片", "tags": []}\n```'
    cap = caption_photo(_img(tmp_path), _rec(), client=FakeClient(raw))
    assert cap.description == "老照片"


def test_tolerates_prose_around_json(tmp_path):
    raw = '好的，结果如下：{"description": "街景", "tags": ["街"]} 请查收'
    cap = caption_photo(_img(tmp_path), _rec(), client=FakeClient(raw))
    assert cap.description == "街景"


def test_fallback_on_dirty_json(tmp_path):
    cap = caption_photo(_img(tmp_path), _rec(), client=FakeClient("不是JSON{{{"))
    assert cap.model == "fallback"
    assert "骑楼街景" in cap.description


def test_fallback_on_client_exception(tmp_path):
    cap = caption_photo(
        _img(tmp_path), _rec(), client=FakeClient(RuntimeError("API 挂了")),
    )
    assert cap.model == "fallback"


def test_missing_description_key_is_fallback(tmp_path):
    cap = caption_photo(_img(tmp_path), _rec(), client=FakeClient('{"foo": 1}'))
    assert cap.model == "fallback"


def test_fallback_caption_fields():
    cap = fallback_caption(_rec())
    assert isinstance(cap, Caption)
    assert cap.model == "fallback"
    assert "骑楼街景" in cap.description and "1930" in cap.description and "广州" in cap.description
    assert cap.tags == []
