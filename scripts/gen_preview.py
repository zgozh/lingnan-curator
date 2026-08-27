"""生成零依赖离线画廊「预览.html」：发布包测试者双击即可浏览全部馆藏。

用法：uv run python scripts/gen_preview.py
读取 data/raw/meta.csv 与 data/processed/<pid>/ 成果图，产出根目录 预览.html。
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "data/raw/meta.csv"
ZH = ROOT / "data/processed/titles-zh.json"

# 必看推荐位（解说文案人工审定）
PICKS = {
    "gz_file1919jpg_006": "修复上色全链样张：老照片里的省运会",
    "gz_filegodownsinhonamjp_031": "沙面码头船居：唯一直用原版上色反成经典案例的照片",
    "gz_filegsherwoodeddysun_048": "谢扶雅与孙中山：历史人物肖像的上色分寸感",
}

zh_map = {}
if ZH.exists():
    try:
        zh_map = json.loads(ZH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass


def pick_img(pid_dir: Path) -> str | None:
    for name in ("enhanced.jpg", "colorized.jpg", "restored.jpg"):
        if (pid_dir / name).exists():
            return name
    return None


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;") \
        .replace('"', "&quot;")


def card(pid: str, row: dict, best: str, rel: str) -> str:
    zh = esc(zh_map.get(pid) or row.get("title") or pid)
    loc = esc(row.get("location") or "")
    year = esc(row.get("year") or "")
    lic = esc(row.get("license") or "")
    return (
        f'<a class="card" target="_blank" '
        f'href="{rel}/{pid}/{best}">'
        f'<img loading="lazy" src="{rel}/{pid}/{best}" alt="{zh}">'
        f"<div><strong>{zh}</strong>"
        f"<small>{year or '年代不详'} · {loc or '地点不详'} · {lic}</small></div></a>")


rows: list[tuple[str, dict, str]] = []
with open(META, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        pid = (r.get("photo_id") or "").strip()
        d = ROOT / f"data/processed/{pid}"
        if not pid or not d.exists():
            continue
        best = pick_img(d)
        if best:
            rows.append((pid, r, best))

pick_html = "".join(
    card(p, r, b, "../data/processed")
    for p, r, b in rows if p in PICKS)
grid_html = "".join(card(p, r, b, "../data/processed") for p, r, b in rows)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>湾区记忆 · 离线预览画廊</title>
<style>
body{{font-family:"Microsoft YaHei",sans-serif;background:#f7f2e9;margin:0;
padding:32px;max-width:1280px;margin-inline:auto}}
h1{{font-size:22px}} h2{{font-size:16px;color:#7a6a55;border-top:1px solid #e4dcd0;
padding-top:18px;margin-top:34px}}
.note{{background:#fff8ec;border-left:4px solid #d9b48f;padding:10px 14px;
font-size:13px;line-height:1.7}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));
gap:14px}}
.card{{display:block;text-decoration:none;color:#333;background:#fff;
border-radius:8px;overflow:hidden;border:1px solid #e4dcd0}}
.card img{{width:100%;height:170px;object-fit:cover;display:block}}
.card div{{padding:8px 10px;font-size:12px;line-height:1.5}}
.card small{{color:#8a8177;display:block;margin-top:2px}}
.picks .card{{border-color:#c9a36a}}
</style>
</head>
<body>
<h1>🏛️ 湾区记忆 · 离线预览画廊（{len(rows)} 张馆藏）</h1>
<p class="note">这是随项目分发的<b>零依赖浏览页</b>：直接双击本文件即可，
无需安装 Python/Milvus。点击任意卡片查看大图。
想体验检索问答/文创生成等完整功能，见同目录 <b>START-HERE.md</b> 的模式 B。
每张图的原始出处与许可协议见 <b>data/raw/meta.csv</b>。</p>

<h2>⭐ 先看这三张（各有代表性）</h2>
<div class="grid picks">{pick_html}</div>

<h2>全部馆藏（{len(rows)} 张）</h2>
<div class="grid">{grid_html}</div>

<h2>还可以看看</h2>
<p style="font-size:13px;line-height:2">
🎧 粤语口播：<code>data/processed/&lt;id&gt;/narration.wav</code>（任意播放器可放）
<br>📮 文创明信片：<code>data/processed/&lt;id&gt;/postcard-front.png / postcard-back.png</code>
<br>🧪 RAGAS 评测报告：<code>eval/reports/</code>（faithfulness 0.888 / relevancy 0.858 / 拒答准确率 1.0）
<br>📖 完整设计文档：<code>docs/superpowers/specs/</code> · 决策记录 <code>docs/adr/</code>
<br>🔧 本页由 <code>scripts/gen_preview.py</code> 生成（素材更新后重跑一次即可刷新）</p>
</body>
</html>
"""
out = ROOT / "预览.html"
out.write_text(html, encoding="utf-8")
print(f"[OK] 预览.html 已生成：{len(rows)} 张卡片（必看 {sum(1 for p, _, _ in rows if p in PICKS)} 张）")
