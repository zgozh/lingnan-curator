"""T5 RED：eval 子命令——批量问答→refused_accuracy+RAGAS 指标→报告落盘。"""
import json

import app.cli as cli


def _write_questions(tmp_path, rows):
    p = tmp_path / "questions.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                 encoding="utf-8")
    return p


def _patch_docent(monkeypatch, answers):
    def fake_ask(q, settings=None):
        return answers[q]
    monkeypatch.setattr(cli, "_ask", fake_ask)


def test_refused_accuracy_computed(monkeypatch, tmp_path):
    qp = _write_questions(tmp_path, [
        {"qid": "q1", "question": "骑楼？", "refusal": False},
        {"qid": "q2", "question": "地铁？", "refusal": True},
    ])
    _patch_docent(monkeypatch, {
        "骑楼？": {"answer": "有骑楼", "photo_ids": ["a"], "refused": False},
        "地铁？": {"answer": "超出馆藏范围", "photo_ids": [], "refused": True},
    })
    called = {}

    def fake_ragas(rows, settings):
        called["rows"] = rows
        return {"faithfulness": 0.9, "answer_relevancy": 0.85}

    monkeypatch.setattr(cli, "_run_ragas", fake_ragas)
    out = tmp_path / "report.json"
    cli.cmd_eval_impl(qp, out)
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["refused_accuracy"] == 1.0
    assert called["rows"][0]["question"] == "骑楼？"  # 拒答样本不进 RAGAS


def test_report_flags_below_threshold(monkeypatch, tmp_path):
    qp = _write_questions(tmp_path, [
        {"qid": "q1", "question": "骑楼？", "refusal": False},
    ])
    _patch_docent(monkeypatch, {
        "骑楼？": {"answer": "x", "photo_ids": ["a"], "refused": False},
    })
    monkeypatch.setattr(
        cli, "_run_ragas",
        lambda rows, settings: {"faithfulness": 0.5, "answer_relevancy": 0.9})
    out = tmp_path / "report.json"
    ok = cli.cmd_eval_impl(qp, out)
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert ok is False  # faithfulness 0.5 < 0.80
    assert rep["meets_threshold"] is False


def test_no_answered_rows_skips_ragas(monkeypatch, tmp_path):
    qp = _write_questions(tmp_path, [
        {"qid": "q1", "question": "地铁？", "refusal": True},
    ])
    _patch_docent(monkeypatch, {
        "地铁？": {"answer": "拒", "photo_ids": [], "refused": True},
    })
    called = []
    monkeypatch.setattr(cli, "_run_ragas",
                        lambda rows, settings: called.append(rows) or {})
    out = tmp_path / "report.json"
    cli.cmd_eval_impl(qp, out)
    assert not called  # 无可评样本则不调 RAGAS
