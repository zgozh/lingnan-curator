"""Task 8 RED：入库管线编排——降级链/单张失败不断批/UTF-8 报告。"""
import json
from pathlib import Path

import app.ingest.pipeline as pipe
from app.ingest.caption_op import Caption
from app.models import PhotoRecord, StepStatus


class FakeEmb:
    def texts(self, s):
        return ([[0.1] * 1024], [{1: 0.5}])

    def image(self, p):
        return [0.2] * 512

    def free(self):
        self.freed = True


def _rec(pid="p1"):
    return PhotoRecord(photo_id=pid, title="骑楼", year="1930", location="广州",
                       source_url="u", license="TEMP-DEMO")


def _setup(tmp_path, monkeypatch, *, restore=True, colorize=True, ocr="招牌",
           cap=None, store_calls=None):
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    (raw / "p1.jpg").write_bytes(b"x")
    (raw / "p2.jpg").write_bytes(b"x")
    out = tmp_path / "out"
    cap = cap or Caption(description="描述文字", tags=["x"], model="qwen-vl")
    monkeypatch.setattr(pipe, "restore_face", lambda s, d: restore)
    monkeypatch.setattr(pipe, "colorize", lambda s, d: colorize)
    monkeypatch.setattr(pipe, "run_ocr", lambda p: ocr)
    monkeypatch.setattr(pipe, "caption_photo", lambda img, rec: cap)
    monkeypatch.setattr(pipe, "_get_embedder", lambda: FakeEmb())
    calls = store_calls if store_calls is not None else []
    monkeypatch.setattr(pipe, "upsert_photo", lambda c, r, **kw: calls.append((r, kw)))
    monkeypatch.setattr(pipe, "get_client", lambda settings=None: object())
    return raw, out, calls


def test_happy_path_all_ok(tmp_path, monkeypatch):
    raw, out, calls = _setup(tmp_path, monkeypatch)
    rep_path = tmp_path / "report.json"
    report = pipe.run_pipeline([_rec()], raw, out, rep_path)
    statuses = {i.step: i.status for i in report.items}
    assert all(s == StepStatus.OK for s in statuses.values())
    assert calls[0][0].has_colorized is True and calls[0][0].restored is True
    assert calls[0][0].caption == "描述文字"
    json.loads(rep_path.read_text(encoding="utf-8"))  # 报告可按 UTF-8 解析


def test_colorize_degraded_still_ingests(tmp_path, monkeypatch):
    raw, out, calls = _setup(tmp_path, monkeypatch, colorize=False)
    rep_path = tmp_path / "report.json"
    pipe.run_pipeline([_rec()], raw, out, rep_path)
    statuses = {i.step: i.status for i in report_items(rep_path)}
    assert statuses["p1/colorize"] == StepStatus.DEGRADED
    assert calls[0][0].has_colorized is False


def test_ocr_failed_marks_and_continues(tmp_path, monkeypatch):
    def boom(_p):
        raise RuntimeError("ocr 引擎炸了")

    raw, out, calls = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(pipe, "run_ocr", boom)
    rep_path = tmp_path / "report.json"
    pipe.run_pipeline([_rec()], raw, out, rep_path)
    statuses = {i.step: i.status for i in report_items(rep_path)}
    assert statuses["p1/ocr"] == StepStatus.FAILED
    assert len(calls) == 1  # 照片仍然入库，ocr_text 为空


def test_two_records_one_bad_locate_skips_only_it(tmp_path, monkeypatch):
    raw, out, calls = _setup(tmp_path, monkeypatch)
    recs = [_rec("p1"), _rec("pX")]  # pX 无文件
    rep_path = tmp_path / "report.json"
    pipe.run_pipeline(recs, raw, out, rep_path)
    steps = {i.step for i in report_items(rep_path)}
    assert any(s.startswith("pX/locate") for s in steps)
    assert len(calls) == 1 and calls[0][0].photo_id == "p1"


def test_caption_fallback_marks_degraded(tmp_path, monkeypatch):
    fb = Caption(description="骑楼，约1930年，广州", tags=[], model="fallback")
    raw, out, calls = _setup(tmp_path, monkeypatch, cap=fb)
    rep_path = tmp_path / "report.json"
    pipe.run_pipeline([_rec()], raw, out, rep_path)
    statuses = {i.step: i.status for i in report_items(rep_path)}
    assert statuses["p1/caption"] == StepStatus.DEGRADED


def report_items(path: Path):
    import json

    from app.models import StepResult, StepStatus

    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        StepResult(step=d["step"], status=StepStatus(d["status"]), detail=d["detail"])
        for d in data["items"]
    ]
