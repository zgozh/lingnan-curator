"""Task 4 RED：OCR 节点——mock 引擎，验证拼接/阈值/永不抛异常。

行格式与 RapidOCR 真实返回一致：[box, text, score]。
"""
from app.ingest import ocr_op


def _row(text: str, score: float):
    return [[[0, 0], [9, 9]], text, score]


def test_filters_low_score(monkeypatch, tmp_path):
    rows = [_row("招牌 A字", 0.92), _row("模糊小字", 0.30)]
    monkeypatch.setattr(ocr_op, "_get_engine", lambda: (lambda p: (rows, 0.1)))
    assert ocr_op.run_ocr(tmp_path / "x.jpg") == "招牌 A字"


def test_two_lines_joined_by_newline(monkeypatch, tmp_path):
    rows = [_row("第一行", 0.90), _row("第二行", 0.80)]
    monkeypatch.setattr(ocr_op, "_get_engine", lambda: (lambda p: (rows, 0.1)))
    assert ocr_op.run_ocr(tmp_path / "x.jpg") == "第一行\n第二行"


def test_bare_list_result_ok(monkeypatch, tmp_path):
    rows = [_row("文本", 0.90)]
    monkeypatch.setattr(ocr_op, "_get_engine", lambda: (lambda p: rows))
    assert ocr_op.run_ocr(tmp_path / "x.jpg") == "文本"


def test_never_raises_on_bad_image(monkeypatch, tmp_path):
    f = tmp_path / "bad.jpg"
    f.write_bytes(b"not-an-image")

    def boom(_p):
        raise RuntimeError("decode fail")

    monkeypatch.setattr(ocr_op, "_get_engine", lambda: boom)
    assert ocr_op.run_ocr(f) == ""


def test_malformed_row_skipped(monkeypatch, tmp_path):
    rows = [_row("正常", 0.90), ["坏行"], None]
    monkeypatch.setattr(ocr_op, "_get_engine", lambda: (lambda p: rows))
    assert ocr_op.run_ocr(tmp_path / "x.jpg") == "正常"
