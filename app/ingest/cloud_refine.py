"""云端精修节点：万相 wanx2.1-imageedit（超分/指令修复），异步任务轮询。

ADR-0011：保真优先——超分(super_resolution)为默认函数；划痕/霉斑修复
(description_edit)由人工逐张审阅后再采纳（本节点只产出 refined.jpg 副产物，
绝不覆盖 restored/colorized 主产物）。任何失败返回 False 由上层降级继续
用本地 CodeFormer/DDColor 产物（降级铁律）。

万相输入限制：宽高 [512,4096]px、≤10MB；本地文件转 base64 data URL 上传；
结果 URL 24h 有效，立即下载落盘。
"""
import base64
import logging
from pathlib import Path

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

_BASE = "https://dashscope.aliyuncs.com/api/v1"
_EDIT_URL = f"{_BASE}/services/aigc/image2image/image-synthesis"
MODEL = "wanx2.1-imageedit"

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".webp": "image/webp", ".bmp": "image/bmp", ".tif": "image/tiff",
         ".tiff": "image/tiff"}

MIN_SIDE, MAX_SIDE, MAX_BYTES = 512, 4096, 10 * 1024 * 1024

SR_PROMPT = "高清超分修复，保持画面内容、构图与历史风貌完全不变。"
REPAIR_PROMPT = (
    "修复这张老照片的划痕、折痕与霉斑，提升清晰度；"
    "严格保持人物面容、服饰纹理、文字招牌与画面构图不变，"
    "不得改换任何内容或添加风格化效果。")


def _data_url(src: Path) -> str | None:
    """本地图片 → base64 data URL；越界(尺寸/大小)返回 None。"""
    try:
        with Image.open(src) as im:
            w, h = im.size
        if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE):
            logger.warning("云精修跳过：尺寸 %dx%d 越界 [%d,%d]",
                           w, h, MIN_SIDE, MAX_SIDE)
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("云精修读图失败: %s", exc)
        return None
    mime = _MIME.get(src.suffix.lower())
    if mime is None:
        return None
    data = src.read_bytes()
    if len(data) > MAX_BYTES:
        logger.warning("云精修跳过：%d 字节超上限", len(data))
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def refine_image(
    src: Path,
    dst: Path,
    function: str = "super_resolution",
    prompt: str = "",
    settings=None,
    http: httpx.Client | None = None,
    poll_interval: float = 3.0,
    timeout: float = 300.0,
) -> bool:
    """提交→轮询→下载。成功产出 dst 返回 True；任何一步失败 False。

    http 参数为依赖注入 seam（测试用 MockTransport）；生产为新建 client。
    """
    src, dst = Path(src), Path(dst)
    try:
        s = settings or __import__("app.config",
                                   fromlist=["Settings"]).Settings.load()
        api_key = getattr(s, "dashscope_api_key", "") or ""
        if not api_key:
            logger.warning("云精修缺 API key，降级")
            return False
        payload_img = _data_url(src)
        if payload_img is None:
            return False

        body = {"model": MODEL,
                "input": {"function": function,
                          "prompt": (prompt or (SR_PROMPT if function ==
                                                "super_resolution" else
                                                REPAIR_PROMPT)),
                          "base_image_url": payload_img},
                "parameters": {}}
        if function == "super_resolution":
            body["parameters"] = {"upscale_factor": 2}

        own = http is None
        cli = http or httpx.Client(base_url=_BASE, timeout=30)
        try:
            r = cli.post(
                "/services/aigc/image2image/image-synthesis",
                headers={"Authorization": f"Bearer {api_key}",
                         "X-DashScope-Async": "enable"},
                json=body,
            )
            if r.status_code != 200:
                logger.warning("云精修提交失败 %s: %s",
                               r.status_code, r.text[:200])
                return False
            task_id = (r.json().get("output") or {}).get("task_id")
            if not task_id:
                logger.warning("云精修响应缺 task_id")
                return False

            waited = 0.0
            result_url = ""
            while waited < timeout:
                pr = cli.get(f"/tasks/{task_id}", headers={
                    "Authorization": f"Bearer {api_key}"})
                out = (pr.json() or {}).get("output") or {}
                status = out.get("task_status")
                if status == "SUCCEEDED":
                    results = out.get("results") or []
                    result_url = (results[0] or {}).get("url", "") \
                        if results else ""
                    break
                if status in ("FAILED", "CANCELED", "UNKNOWN"):
                    logger.warning("云精修任务 %s 失败: %s",
                                   status, out.get("message", ""))
                    return False
                import time as _t

                _t.sleep(poll_interval)
                waited += poll_interval
            if not result_url:
                logger.warning("云精修轮询超时(%.0fs)", timeout)
                return False
            dl = cli.get(result_url)
            if dl.status_code != 200 or not dl.content:
                logger.warning("云精修结果下载失败 %s", dl.status_code)
                return False
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(dl.content)
            return True
        finally:
            if own:
                cli.close()
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("云精修异常，降级: %s", exc)
        return False
