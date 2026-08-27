"""云精修单测：任务下发→轮询→下载 全链 mock；异常/超时全走降级 False。"""
import httpx
import pytest

from app.config import Settings
from app.ingest import cloud_refine as cr


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler),
                        base_url=cr._BASE)


def test_missing_key_degrades_false(tmp_path):
    s = Settings(dashscope_api_key="")
    src = tmp_path / "in.jpg"
    import io

    from PIL import Image
    Image.new("RGB", (640, 480), (1, 2, 3)).save(src)
    assert cr.refine_image(src, tmp_path / "o.jpg", function="super_resolution",
                           settings=s, http=_transport(
        lambda req: httpx.Response(500))) is False


def test_small_image_rejected_before_api(tmp_path):
    """短边 <512px 的图不满足万相输入下限，直接本地降级不打 API。"""
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={"output": {"task_id": "t"}})

    s = Settings(dashscope_api_key="k")
    import io

    from PIL import Image
    tiny = tmp_path / "tiny.jpg"
    Image.new("RGB", (300, 200)).save(tiny)
    assert cr.refine_image(tiny, tmp_path / "o.jpg",
                           settings=s, http=_transport(handler)) is False
    assert not calls                       # 没发任何请求


PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-bytes"


def test_full_flow_success_downloads_result(tmp_path):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            body = req.read()
            assert b'"wanx2.1-imageedit"' in body
            assert b'"base_image_url"' in body
            return httpx.Response(200, json={
                "output": {"task_id": "task-1", "task_status": "PENDING"}})
        path = str(req.url)
        if "/tasks/task-1" in path:
            return httpx.Response(200, json={
                "output": {"task_status": "SUCCEEDED",
                           "results": [{"url": "https://cdn/x.png"}]}})
        return httpx.Response(200, headers={"content-type": "image/png"},
                              content=PNG_BYTES)

    s = Settings(dashscope_api_key="k")
    src = tmp_path / "in.png"
    import io

    from PIL import Image
    Image.new("RGB", (800, 600)).save(src)
    dst = tmp_path / "out.jpg"
    ok = cr.refine_image(src, dst, function="super_resolution",
                         settings=s, http=_transport(handler))
    assert ok and dst.exists() and dst.read_bytes() == PNG_BYTES


def test_task_failed_degrades_false(tmp_path):
    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, json={
                "output": {"task_id": "t2"}})
        return httpx.Response(200, json={
            "output": {"task_status": "FAILED",
                       "message": "internal error"},
            "code": "InternalError"})

    s = Settings(dashscope_api_key="k")
    src = tmp_path / "in.jpg"
    import io

    from PIL import Image
    Image.new("RGB", (800, 600)).save(src)
    assert cr.refine_image(src, tmp_path / "o.jpg",
                           settings=s, http=_transport(handler)) is False
    assert not (tmp_path / "o.jpg").exists()


def test_poll_timeout_returns_false(tmp_path, monkeypatch):
    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, json={"output": {"task_id": "t3"}})
        return httpx.Response(200, json={
            "output": {"task_status": "RUNNING"}})

    s = Settings(dashscope_api_key="k")
    src = tmp_path / "in.jpg"
    import io

    from PIL import Image
    Image.new("RGB", (800, 600)).save(src)
    ok = cr.refine_image(src, tmp_path / "o.jpg", settings=s,
                         http=_transport(handler),
                         timeout=0.05, poll_interval=0.01)
    assert not ok


def test_submit_error_degrades_false(tmp_path):
    def handler(req):
        return httpx.Response(400, json={"code": "InvalidParameter",
                                         "message": "bad request"})

    s = Settings(dashscope_api_key="k")
    src = tmp_path / "in.jpg"
    import io

    from PIL import Image
    Image.new("RGB", (800, 600)).save(src)
    assert cr.refine_image(src, tmp_path / "o.jpg", settings=s,
                           http=_transport(handler)) is False


def test_pick_work_uses_colorized_first(tmp_path):
    d = tmp_path
    (d / "restored.jpg").write_bytes(b"x")
    from app.infra.artifact import pick_background
    assert pick_background(d).name == "restored.jpg"
