"""发布包打包脚本：显式排除规则 + UTF-8 文件名写入。

用法：uv run python scripts/pack_zip.py [输出zip路径]
默认输出 D:/develop/workspace/lingnan-curator-testpack.zip

排除（硬规则，防密钥/重资产泄漏）：
.env 及任何 .env.*            —— 绝不允许进包
.git / .venv / .uv-cache / .pytest-tmp / .tmp / .superpowers / tmp
models/                       —— 本机 21.9GB 权重
.ruff_cache / __pycache__ / pytest-cache-files-* / *.pyc / *.log
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT.parent / "lingnan-curator-testpack.zip"

EXCLUDE_DIRS = {".git", ".venv", ".uv-cache", ".pytest-tmp", ".tmp",
                ".superpowers", "tmp", "models", ".ruff_cache",
                "__pycache__", ".pytest_cache"}
EXCLUDE_FILES = {"*.pyc", "*.log", ".env"}

out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
entries = 0
with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED,
                     compresslevel=6) as zf:
    base = f"{ROOT.name}/"
    for p in sorted(ROOT.rglob("*")):
        rel_parts = p.relative_to(ROOT).parts
        if any(part in EXCLUDE_DIRS
               or part.startswith("pytest-cache-files-")
               for part in rel_parts[:-1] + ((rel_parts[-1],)
                                             if p.is_file() else ())):
            continue
        if not p.is_file():
            continue
        name = p.name
        if any(name.endswith(sfx.replace("*", ""))
               for sfx in EXCLUDE_FILES) or name == ".env":
            continue
        zf.write(p, arcname=base + "/".join(rel_parts))
        entries += 1

size_mb = out_path.stat().st_size / 1024 / 1024
print(f"[OK] {out_path}  共 {entries} 个文件，{size_mb:.0f} MB")
if entries < 400:
    raise SystemExit("[NG] 条目数异常偏少，请检查排除规则")
