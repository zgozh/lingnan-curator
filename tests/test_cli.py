"""Task 8 RED：CLI 入口——ingest 子命令与 W2+ 占位。"""
import pytest

from app.cli import main


def test_serve_raises_not_implemented():
    with pytest.raises(SystemExit, match="W2"):
        main(["serve"])


def test_ingest_runs_with_defaults(tmp_path, monkeypatch):
    """冒烟级：ingest 走通 load_meta→run_pipeline 链（全 mock）。"""
    import app.cli as cli
    import app.ingest.meta as meta_mod
    from app.models import PhotoRecord

    seen = {}

    def fake_load(csv_path, raw_dir):
        return (
            [PhotoRecord(photo_id="p1", title="t", source_url="u", license="PD")],
            ["p9: 演示拒收"],
        )

    def fake_run(records, raw_dir, out_root, report_path):
        from app.models import IngestReport

        seen["n"] = len(records)
        return IngestReport()

    monkeypatch.setattr(meta_mod, "load_meta", fake_load)
    monkeypatch.setattr(cli, "_ingest_flow", fake_run)
    main(["ingest", "--src", str(tmp_path)])
    assert seen["n"] == 1


def test_narrate_ok(monkeypatch):
    """T11：narrate 跑完整叙事链，pid 透传、音频成功→[OK]。"""
    import app.narrator.story as story_mod

    calls = {}

    def fake_run(pid, settings=None, force=False):
        calls["pid"] = pid
        calls["force"] = force
        return {"story": "故事", "narration": "{}", "audio": True, "degraded": False}

    monkeypatch.setattr(story_mod, "run_story_chain", fake_run)
    main(["narrate", "--pid", "sample_a"])
    assert calls["pid"] == "sample_a"
    assert calls["force"] is False


def test_narrate_ng_degraded(monkeypatch, capsys):
    """T11：音频降级→[NG]，且 --force 透传给 run_story_chain。"""
    import app.narrator.story as story_mod

    calls = {}

    def fake_run(pid, settings=None, force=False):
        calls["pid"] = pid
        calls["force"] = force
        return {"story": "故事", "narration": "{}", "audio": False, "degraded": True}

    monkeypatch.setattr(story_mod, "run_story_chain", fake_run)
    main(["narrate", "--pid", "sample_a", "--force"])
    captured = capsys.readouterr()
    assert calls["pid"] == "sample_a"
    assert calls["force"] is True
    assert captured.out.startswith("[NG]")
