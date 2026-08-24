"""vendor 视觉节点：CodeFormer(人脸修复) / DDColor(上色)。

独立 venv + 子进程隔离（ADR-0002）；任何失败返回 False，由上层按
DEGRADED 降级（spec 边界案例），绝不抛异常——降级铁律。

spike 结论（2026-08-24）：
- PyPI basicsr sdist 在沙箱内构建被拒 → CF 子进程以 PYTHONPATH 借用
  DDColor 仓库内置的 basicsr（导入已实测可用），不再 pip 安装。
- DDColor 推理入口为 scripts/infer.py，目录进/出，权重经 hf-mirror 自动下载。
"""
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_VENDOR = Path(__file__).resolve().parents[2] / "models" / "vendor"
_DD_REPO = _VENDOR / "DDColor"
TIMEOUT = 300  # 单张/vendor 调用上限（秒）
_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _venv_python(kind: str) -> str | None:
    sub = "venv-cf" if kind == "cf" else "venv-dd"
    p = _VENDOR / sub / "Scripts" / "python.exe"
    return str(p) if p.exists() else None


def _repo(kind: str) -> Path:
    return _VENDOR / ("CodeFormer" if kind == "cf" else "DDColor")


def _build_cmd(kind: str, src: Path, dst: Path) -> list[str]:
    """构造 vendor 推理命令。所有路径必须绝对（子进程 cwd 在 vendor 仓库）。"""
    py = _venv_python(kind)
    if py is None:
        raise FileNotFoundError(f"vendor venv 缺失: kind={kind}")
    src = Path(src).resolve()
    out_dir = (dst.parent / f".vendor-{kind}").resolve()
    if kind == "cf":
        repo = _repo("cf")
        return [
            py, str(repo / "inference_codeformer.py"),
            "-w", "0.7", "-i", str(src), "-o", str(out_dir),
            "--face_upsample",
        ]
    in_dir = (dst.parent / ".vendor-dd-in").resolve()
    return [
        py, str(_DD_REPO / "scripts" / "infer.py"),
        "--model_name", "ddcolor_modelscope",
        "--input", str(in_dir), "--output", str(out_dir),
    ]


def _harvest(vendor_out: Path, dst: Path) -> bool:
    """从 vendor 输出目录里挑最大的图片搬到规范位置 dst。"""
    candidates = [p for p in vendor_out.rglob("*") if p.suffix.lower() in _IMG_EXTS]
    if not candidates:
        return False
    best = max(candidates, key=lambda p: p.stat().st_size)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(best), str(dst))
    return True


def _run_kind(kind: str, src: Path, dst: Path) -> bool:
    src, dst = Path(src), Path(dst)
    try:
        cmd = _build_cmd(kind, src, dst)
    except FileNotFoundError as exc:
        logger.warning("%s vendor 未就绪，按降级处理: %s", kind, exc)
        return False

    env = dict(os.environ)
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    # HF 缓存重定向进工作区（沙箱拒写 AppData）
    env.setdefault(
        "HF_HOME", str(_VENDOR.parent.parent / "models" / "hf-cache")
    )
    # spike 结论：借用 DDColor 内置 basicsr，绕开 PyPI sdist 沙箱构建失败
    env["PYTHONPATH"] = str(_DD_REPO)

    tmp_out = dst.parent / f".vendor-{kind}"
    try:
        if kind == "dd":  # infer.py 是目录进：把单张图放进临时输入目录
            in_dir = (dst.parent / ".vendor-dd-in").resolve()
            in_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, in_dir / Path(src).name)
        proc = subprocess.run(
            cmd, cwd=str(_repo(kind)), env=env, capture_output=True,
            timeout=TIMEOUT,
        )
        if proc.returncode != 0:
            logger.warning(
                "%s 推理失败 rc=%s: %s", kind, proc.returncode,
                proc.stderr.decode("utf-8", "ignore")[-300:],
            )
            return False
        return _harvest(tmp_out, dst)
    except subprocess.TimeoutExpired:
        logger.warning("%s 超时(>%ss)，降级", kind, TIMEOUT)
        return False
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("%s 异常，降级: %s", kind, exc)
        return False
    finally:
        shutil.rmtree(tmp_out, ignore_errors=True)
        shutil.rmtree(dst.parent / ".vendor-dd-in", ignore_errors=True)


def restore_face(src: Path, dst: Path) -> bool:
    """人脸修复：成功产出 dst(restored.jpg)=True；失败=False(上层用原图)。"""
    return _run_kind("cf", Path(src), Path(dst))


def colorize(src: Path, dst: Path) -> bool:
    """上色：成功产出 dst(colorized.jpg)=True；失败=False(上层用修复图)。"""
    return _run_kind("dd", Path(src), Path(dst))
