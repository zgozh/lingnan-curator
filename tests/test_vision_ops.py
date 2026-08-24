"""Task 7 RED：vendor 子进程封装——命令构造/harvest/失败降级语义。"""
import subprocess
from pathlib import Path

import app.ingest.vision_ops as vo


def test_build_cmd_restore_uses_cf_venv_and_script():
    cmd = vo._build_cmd("cf", Path("in.jpg"), Path("data/processed/a/restored.jpg"))
    assert isinstance(cmd, list) and "venv-cf" in cmd[0]
    assert any("inference_codeformer" in c for c in cmd)


def test_build_cmd_colorize_uses_dd_infer_script_with_model_name():
    cmd = vo._build_cmd("dd", Path("in.jpg"), Path("data/processed/a/colorized.jpg"))
    assert "venv-dd" in cmd[0]
    assert any(c.endswith("infer.py") for c in cmd)
    assert "--model_name" in cmd and "ddcolor_modelscope" in cmd


def test_build_cmd_colorize_prefers_local_weights(monkeypatch):
    """spike 结论：hub 1.28 与镜像元数据不兼容 → 本地权重优先。"""
    real_exists = Path.exists

    def fake_exists(self: Path):
        if self.name == "pytorch_model.pt" and "pretrain" in str(self):
            return True
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    cmd = vo._build_cmd("dd", Path("in.jpg"), Path("data/processed/a/colorized.jpg"))
    assert "--model_path" in cmd and "--model_name" not in cmd


def test_run_env_carries_hf_mirror_and_borrowed_basicsr(monkeypatch, tmp_path):
    """spike 结论落地：子进程必须带 HF_ENDPOINT 与指向 DDColor 的 PYTHONPATH。"""
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(vo.subprocess, "run", fake_run)
    monkeypatch.setattr(vo, "_harvest", lambda o, d: True)
    img = tmp_path / "in.jpg"
    img.write_bytes(b"x")
    ok = vo.colorize(img, tmp_path / "c.jpg")
    assert ok is True
    assert seen["env"]["HF_ENDPOINT"] == "https://hf-mirror.com"
    assert "DDColor" in seen["env"]["PYTHONPATH"]


def test_harvest_moves_largest_image(tmp_path):
    out = tmp_path / ".vendor-cf"
    (out / "final_results").mkdir(parents=True)
    (out / "final_results" / "small.jpg").write_bytes(b"x" * 10)
    (out / "final_results" / "big.png").write_bytes(b"x" * 999)
    dst = tmp_path / "restored.jpg"
    assert vo._harvest(out, dst) is True
    assert dst.exists() and dst.read_bytes().endswith(b"x" * 9)


def test_harvest_no_image_false(tmp_path):
    out = tmp_path / ".vendor-dd"
    out.mkdir()
    assert vo._harvest(out, tmp_path / "colorized.jpg") is False


def test_run_wraps_subprocess(monkeypatch, tmp_path):
    """成功路径：run 返回 0 且 harvest 命中 → True；并带 cwd 与 timeout。"""
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(vo.subprocess, "run", fake_run)
    monkeypatch.setattr(vo, "_harvest", lambda o, d: True)
    ok = vo.restore_face(tmp_path / "in.jpg", tmp_path / "r.jpg")
    assert ok is True
    assert seen["timeout"] == vo.TIMEOUT
    assert "CodeFormer" in seen["cwd"]


def test_timeout_returns_false(monkeypatch, tmp_path):
    def boom(**kw):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(vo.subprocess, "run", boom)
    assert vo.colorize(tmp_path / "in.jpg", tmp_path / "c.jpg") is False


def test_nonzero_return_false(monkeypatch, tmp_path):
    monkeypatch.setattr(
        vo.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess([], 3),
    )
    assert vo.restore_face(tmp_path / "in.jpg", tmp_path / "r.jpg") is False


def test_missing_venv_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(vo, "_venv_python", lambda kind: None)  # venv 不存在
    assert vo.restore_face(tmp_path / "in.jpg", tmp_path / "r.jpg") is False
