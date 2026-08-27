"""文创产物渲染器：把 LLM 文案排版成真正的明信片/海报图。

纯本地 Pillow 实现（无网络）；任何异常返回 False 由上层降级为
纯文本响应（降级铁律）。字体按候选序探测本机中文字体，
全部缺失时用 Pillow 内置默认位图字体兜底（保证不崩）。

输出尺寸约定：
- 明信片横版 148×100mm @300dpi ≈ 1748×1181px（正/背面各一张）
- 标语海报 3:4 1080×1440px
"""
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

CARD_W, CARD_H = 1748, 1181          # 明信片正面/背面统一画布
POSTER_W, POSTER_H = 1080, 1440

_INK = (43, 36, 32)
_RED = (178, 34, 34)
_GRAY = (120, 112, 104)

# Windows 自带中文字体探测序；缺省回退 PIL 内置默认字体
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",   # 黑体
    r"C:\Windows\Fonts\simsun.ttc",   # 宋体
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int):
    for p in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:  # noqa: BLE001 —— 换下一个候选
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                   # 老 Pillow 无 size 参数
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """中文逐字换行（标点悬挂不做，简 suffit）。"""
    lines, cur = [], ""
    for ch in str(text or "").replace("\r", ""):
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def _fit_lines(draw, text, font_size, max_w, start_size=None, min_size=24):
    """字号从大到小试探，让整段文字行数≤给定预算内可排下。"""
    size = start_size or font_size
    while size >= min_size:
        f = _font(size)
        lines = _wrap(draw, text, f, max_w)
        if len(lines) <= 14 or size == min_size:
            return f, lines
        size -= 4
    return _font(min_size), _wrap(draw, text, _font(min_size), max_w)


def _seal(draw, x: int, y: int, s: int = 200) -> None:
    """印章式落款：红框 + 两行刻字。"""
    draw.rounded_rectangle([x, y, x + s, y + s], radius=18,
                           outline=_RED, width=7)
    f = _font(int(s * 0.30))
    draw.text((x + s / 2, y + s * 0.33), "湾区", font=f,
              fill=_RED, anchor="mm")
    draw.text((x + s / 2, y + s * 0.68), "记忆", font=f,
              fill=_RED, anchor="mm")


def _pick_src(src: Path | None) -> Path | None:
    if src is not None and Path(src).exists():
        return Path(src)
    return None


def pick_background(pid_dir: Path | str) -> Path | None:
    """选文创底图：上色图优先，其次修复图；都缺返回 None。"""
    d = Path(pid_dir)
    for name in ("colorized.jpg", "restored.jpg"):
        if (d / name).exists():
            return d / name
    return None


def render_postcard(src: Path | None, title: str, year: str, body: str,
                    meta_line: str, out_front: Path, out_back: Path) -> bool:
    """双面明信片：正面照片+标题印签；背面寄语+邮资框。任一失败→False。"""
    img_path = _pick_src(src)
    if img_path is None:
        logger.warning("明信片渲染缺底图，降级")
        return False
    try:
        # ---------- 正面 ----------
        card = Image.new("RGB", (CARD_W, CARD_H), "white")
        m = 56                                    # 白边
        photo = Image.open(img_path).convert("RGB")
        photo = ImageOps.exif_transpose(photo)
        photo = ImageOps.fit(photo, (CARD_W - 2 * m, CARD_H - 2 * m - 210),
                             method=Image.LANCZOS)
        card.paste(photo, (m, m))
        d = ImageDraw.Draw(card, "RGBA")
        # 底部渐变题字带
        ph = photo.size[1]
        band_h = 190
        for i in range(band_h):
            a = int(170 * i / band_h)
            d.line([(m, m + ph - band_h + i), (m + photo.size[0],
                    m + ph - band_h + i)], fill=(20, 16, 12, a))
        f_title = _font(64)
        caption = f"《{title}》{('·' + year) if year else ''}"
        d.text((m + 36, m + ph - 62), caption, font=f_title,
               fill=(255, 250, 240), anchor="lm")
        _seal(d, CARD_W - m - 224, m + ph - 258)
        card.save(out_front)

        # ---------- 背面 ----------
        back = Image.new("RGB", (CARD_W, CARD_H), (247, 242, 231))
        db = ImageDraw.Draw(back)
        db.rectangle([28, 28, CARD_W - 28, CARD_H - 28], outline=_GRAY, width=3)
        fb_head = _font(38)
        db.text((70, 64), "POST CARD · 湾区记忆 · 岭南非遗 AI 策展",
                font=fb_head, fill=_GRAY)
        divider_x = int(CARD_W * 0.60)
        db.line([(divider_x, 130), (divider_x, CARD_H - 130)],
                fill=_GRAY, width=3)
        # 寄语区（左侧）
        fb_body = _font(52)
        lines = _wrap(db, body, fb_body, divider_x - 150)[:16]
        y = 180
        for ln in lines:
            db.text((80, y), ln, font=fb_body, fill=_INK)
            y += 84
        # 邮编格（右下角六格）
        fx0, fy = CARD_W - 520, CARD_H - 150
        for k in range(6):
            db.rectangle([fx0 + k * 78, fy, fx0 + k * 78 + 64, fy + 74],
                         outline=_GRAY, width=3)
        # 邮票框（右上虚线框）
        sx0, sy0, sx1, sy1 = CARD_W - 480, 130, CARD_W - 100, 480
        step = 26
        for xx in range(sx0, sx1, step):
            db.line([(xx, sy0), (min(xx + 14, sx1), sy0)], fill=_GRAY, width=4)
            db.line([(xx, sy1), (min(xx + 14, sx1), sy1)], fill=_GRAY, width=4)
        for yy in range(sy0, sy1, step):
            db.line([(sx0, yy), (sx0, min(yy + 14, sy1))], fill=_GRAY, width=4)
            db.line([(sx1, yy), (sx1, min(yy + 14, sy1))], fill=_GRAY, width=4)
        db.text(((sx0 + sx1) / 2, (sy0 + sy1) / 2), "邮票\nSTAMP",
                font=_font(40), fill=_GRAY, anchor="mm", align="center")
        # 落款（版权与出处留痕）
        fb_meta = _font(30)
        db.text((70, CARD_H - 86), meta_line[:52], font=fb_meta, fill=_GRAY)
        back.save(out_back)
        return True
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("明信片渲染失败: %s", exc)
        return False


def render_poster(bg: Path | None, slogan: str, sub: str,
                  out_path: Path) -> bool:
    """标语海报：底图压暗 + 大字标语 + 小字副题。失败→False。"""
    img_path = _pick_src(bg)
    if img_path is None:
        logger.warning("海报渲染缺底图，降级")
        return False
    try:
        canvas = Image.new("RGB", (POSTER_W, POSTER_H), "black")
        photo = Image.open(img_path).convert("RGB")
        photo = ImageOps.exif_transpose(photo)
        photo = ImageOps.fit(photo, (POSTER_W, POSTER_H),
                             method=Image.LANCZOS)
        canvas.paste(photo, (0, 0))
        ov = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        for i in range(POSTER_H):                 # 上浅下深压暗
            a = int(200 * (i / POSTER_H) ** 1.5)
            do.line([(0, i), (POSTER_W, i)], fill=(10, 8, 6, a))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), ov).convert("RGB")
        d = ImageDraw.Draw(canvas)
        fs, lines = 132, []
        while fs >= 48:
            f = _font(fs)
            lines = _wrap(d, slogan, f, POSTER_W - 160)
            if all(d.textlength(ln, font=f) <= POSTER_W - 160
                   for ln in lines) and len(lines) <= 4:
                break
            fs -= 12
        total = sum(fs + 46 for _ in lines) - 46
        y = (POSTER_H - total) / 2 - 40
        for ln in lines:
            d.text((POSTER_W / 2, y), ln, font=_font(fs),
                   fill=(255, 249, 238), anchor="ma")
            y += fs + 46
        if sub:
            d.text((POSTER_W / 2, y + 30), sub, font=_font(44),
                   fill=(228, 216, 198), anchor="ma")
        d.text((POSTER_W - 40, POSTER_H - 54), "湾区记忆 · 岭南非遗 AI 策展人",
               font=_font(32), fill=(200, 188, 172), anchor="rs")
        canvas.save(out_path)
        return True
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("海报渲染失败: %s", exc)
        return False
