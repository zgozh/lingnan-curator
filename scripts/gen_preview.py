"""生成零依赖离线展馆「预览.html」：发布包测试者双击即可浏览/对比/听讲。

用法：uv run python scripts/gen_preview.py
- 卡片墙（26 张，enhanced 优先）
- 点击卡片弹出离线详情：修复↔上色对比滑块、粤语口播 <audio>、故事文本、文创产物链接
- 自校验：页面引用的每一条磁盘资源必须真实存在
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "data/raw/meta.csv"
ZH = ROOT / "data/processed/titles-zh.json"

PICKS = {
    "gz_file1919jpg_006": "修复上色全链样张：老照片里的省运会",
    "gz_filegodownsinhonamjp_031": "沙面码头船居：唯一直用原版上色反成经典的照片",
    "gz_filegsherwoodeddysun_048": "谢扶雅与孙中山：人物肖像上色的分寸感",
}

zh_map: dict[str, str] = {}
if ZH.exists():
    try:
        zh_map = json.loads(ZH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass


def esc(s) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;") \
        .replace('"', "&quot;")


def best_img(d: Path) -> str | None:
    for n in ("enhanced.jpg", "colorized.jpg", "restored.jpg"):
        if (d / n).exists():
            return n
    return None


rows = []
with open(META, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        pid = (r.get("photo_id") or "").strip()
        d = ROOT / f"data/processed/{pid}"
        if not pid or not d.exists():
            continue
        b = best_img(d)
        if not b:
            continue
        # 滑块"上色前"图：本地有 restored 用之；克隆版(不含405MB restored)
        # 自动回退到 data/raw 原始扫描件，浏览体验近似
        raws = list((ROOT / "data/raw").glob(f"{pid}.*"))
        raw_rel = f"data/raw/{raws[0].name}" if raws else ""
        story = ""
        try:
            sp = d / "story.json"
            if sp.exists():
                story = json.loads(
                    sp.read_text(encoding="utf-8")).get("text", "")[:160]
        except Exception:  # noqa: BLE001
            pass
        rows.append({
            "pid": pid,
            "zh": zh_map.get(pid) or r.get("title") or pid,
            "year": (r.get("year") or "年代不详").strip(),
            "loc": (r.get("location") or "地点不详").strip(),
            "lic": (r.get("license") or "").strip(),
            "src": r.get("source_url") or "",
            "best": b,
            "restored": (d / "restored.jpg").exists(),
            "raw": raw_rel,
            "colorized": (d / "colorized.jpg").exists(),
            "audio": (d / "narration.wav").exists(),
            "postcard": (d / "postcard-front.png").exists(),
            "postcard_back": (d / "postcard-back.png").exists(),
            "slogan": (d / "slogan.png").exists(),
            "story": story,
        })

config = json.dumps(rows, ensure_ascii=False)


def card(it: dict) -> str:
    return (
        f'<a class="card" href="#" data-pid="{esc(it["pid"])}" '
        f'onclick="openDetail(this.dataset.pid);return false;">'
        f'<img loading="lazy" src="data/processed/{it["pid"]}/{it["best"]}" '
        f'alt="{esc(it["zh"])}">'
        f"<div><strong>{esc(it['zh'])}</strong>"
        f"<small>{esc(it['year'])} · {esc(it['loc'])} · {esc(it['lic'])}"
        f"{' · 🎧有讲解' if it['audio'] else ''}</small></div></a>")


pick_html = "".join(card(r) for r in rows if r["pid"] in PICKS)
grid_html = "".join(card(r) for r in rows)

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>湾区记忆 · 离线展馆</title>
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
#mask{{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;z-index:50}}
#modal{{position:fixed;inset:5% 3%;background:#fffaf1;border-radius:10px;
overflow:auto;padding:18px 22px;display:none;z-index:51;box-shadow:0 8px 40px #0007}}
.cmp{{position:relative;width:min(680px,100%);margin:12px auto}}
.cmp img{{width:100%;display:block}}
.cmp .b{{position:absolute;inset:0;clip-path:inset(0 50% 0 0)}}
.cmp input[type=range]{{width:min(680px,100%);display:block;margin:6px auto}}
.lbl{{text-align:center;font-size:12px;color:#8a8177}}
.meta{{font-size:13px;line-height:1.9;color:#444}}
.linkout{{font-size:12px;margin-right:10px}}
</style></head><body>
<h1>🏛️ 湾区记忆 · 离线展馆（{len(rows)} 张馆藏）</h1>
<p class="note">零依赖浏览页：双击本文件即可<b>点卡片 → 拉滑块对比 → 听粤语讲解</b>，
无需安装任何环境。每张图的出处与许可见 <b>data/raw/meta.csv</b>；
完整交互（检索/问答/文创生成）按 START-HERE.md 的模式 B 部署。</p>
<h2>⭐ 先看这三张</h2><div class="grid picks">{pick_html}</div>
<h2>全部馆藏</h2><div class="grid">{grid_html}</div>

<div id="mask" onclick="closeDetail()"></div>
<div id="modal"></div>
<script>
const DATA = {config};
function openDetail(pid){{
  const it = DATA.find(x => x.pid === pid);
  const cmpLeft = it.restored ? 'restored.jpg'
                : (it.raw ? it.raw.replace(/^data\\/raw\\//, '') : '');
  const cmpBase = it.restored
    ? `data/processed/${{it.pid}}/` : 'data/raw/';
  const cmpRight = it.colorized ? 'colorized.jpg' : it.best;
  let cmp = '';
  if (cmpLeft && cmpLeft !== cmpRight) {{
    cmp = `<div class="cmp" id="cmp">
      <img src="${{cmpBase}}${{cmpLeft}}" alt="上色前">
      <img class="b" id="layB"
           src="data/processed/${{it.pid}}/${{cmpRight}}" alt="上色后">
      </div>
      <input type="range" min="0" max="100" value="50"
        oninput="document.getElementById('layB').style.clipPath=
          'inset(0 '+(100-this.value)+'% 0 0)'">
      <div class="lbl">左拖=上色前，右拉=AI 上色
        ${{it.restored ? '（修复灰度）' : '（原始扫描件）'}}</div>`;
  }} else {{
    cmp = `<div class="cmp"><img
      src="data/processed/${{it.pid}}/${{it.best}}"></div>`;
  }}
  const audio = it.audio
    ? `<p><b>🎧 粤语讲解：</b><br><audio controls preload="none"
         style="width:min(680px,100%)"
         src="data/processed/${{it.pid}}/narration.wav"></audio></p>`
    : '<p class="lbl">该照片未收录预生成口播。</p>';
  const links = [
    ['明信片正面', it.postcard],
    ['明信片背面', it.postcard_back],
    ['海报图', it.slogan]].filter(x => x[1])
    .map(([t, f]) =>
      `<a class="linkout" target="_blank"
         href="data/processed/${{it.pid}}/${{
           t === '明信片正面' ? 'postcard-front.png'
           : t === '明信片背面' ? 'postcard-back.png' : 'slogan.png'}}">${{t}}</a>`)
    .join('');
  document.getElementById('modal').innerHTML =
    `<h2 style="border:0;margin-top:0">${{esc(it.zh)}}
       <a href="#" onclick="closeDetail();return false;"
          style="float:right;font-size:13px">✕ 关闭</a></h2>
     ${{cmp}}${{audio}}
     <p class="meta">🗓 ${{esc(it.year)}} · 📍${{esc(it.loc)}} · ⚖️${{esc(it.lic)}}
       ${{it.src ? `· <a target="_blank" href="${{esc(it.src)}}">原始出处</a>` : ''}}</p>
     ${{it.story ? `<p class="meta"><b>AI 叙事：</b>${{esc(it.story)}}…</p>` : ''}}
     ${{links ? `<p>${{links}}</p>` : ''}}`;
  document.getElementById('mask').style.display = 'block';
  document.getElementById('modal').style.display = 'block';
}}
function closeDetail(){{
  document.getElementById('mask').style.display = 'none';
  document.getElementById('modal').style.display = 'none';
}}
function esc(s){{return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
}}
</script>
</body></html>
"""
out = ROOT / "预览.html"
out.write_text(html, encoding="utf-8")

# 自校验：页面引用的所有真实资源路径必须存在（跳过 JS 模板占位符 ${...}）
refs = [r_ for r_ in re.findall(r'(?:src|href)="((?:data/(?:processed|raw))/[^"]+)"', html)
        if "${" not in r_]
missing = [r_ for r_ in refs if not (ROOT / r_).exists()]
assert not missing, f"预览页引用了不存在的文件: {missing[:3]}"
for it in rows:
    assert (ROOT / f"data/processed/{it['pid']}/{it['best']}").exists()
print(f"[OK] 预览.html 已生成：{len(rows)} 张卡片"
      f"（必看 {sum(1 for r in rows if r['pid'] in PICKS)} 张）；"
      f"资源引用 {len(refs)} 条全部存在")
