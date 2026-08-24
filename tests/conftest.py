"""共享 fixtures。

沙箱环境实测：pytest 内置 basetemp 的「整树删除再重建」机制会被文件沙箱
拒绝（目录一旦被拒即永久损坏）。这里用普通 pathlib 建删覆盖同名 fixture，
行为对测试透明：唯一临时目录 + 用后清理（失败静默，不阻塞）。
"""
import shutil
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest

_RUNS = Path(__file__).resolve().parent.parent / "data" / "test-runs"


@pytest.fixture
def tmp_path() -> Generator[Path, None, None]:
    d = _RUNS / uuid.uuid4().hex[:8]
    d.mkdir(parents=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)
