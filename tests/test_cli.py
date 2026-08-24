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
        seen["n"] = len(records)
        return object()

    monkeypatch.setattr(meta_mod, "load_meta", fake_load)
    monkeypatch.setattr(cli, "_ingest_flow", fake_run)
    main(["ingest", "--src", str(tmp_path)])
    assert seen["n"] == 1
