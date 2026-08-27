"""统一命令入口：python -m app.cli <ingest|serve|narrate|eval>。"""
import argparse
import sys
from pathlib import Path


def _not_impl(name: str):
    def _cmd(_args) -> None:
        raise SystemExit(f"{name}: 属于 W2+/W3 里程碑，尚未实现")
    return _cmd


def _ingest_flow(records, raw_dir, out_root, report_path):
    from app.ingest.pipeline import run_pipeline

    return run_pipeline(records, raw_dir, out_root, report_path)


def cmd_ingest(args) -> None:
    from app.config import Settings
    from app.ingest.meta import load_meta
    from app.models import StepStatus

    settings = Settings.load()
    raw = Path(args.src)
    records, errors = load_meta(raw / "meta.csv", raw)
    for e in errors:
        print(f"[拒收] {e}", file=sys.stderr)
    if getattr(args, "pid", ""):
        records = [r for r in records if r.photo_id == args.pid]
        if not records:
            raise SystemExit(f"[NG] meta.csv 中不存在 photo_id={args.pid}")
    if args.limit > 0:
        records = records[: args.limit]
    print(f"合法 {len(records)} 张，开始入库（Milvus={settings.milvus_uri}）……")
    report = _ingest_flow(
        records, raw,
        Path("data/processed"), Path("data/processed/_report.json"),
    )
    bad = [i for i in report.items if i.status != StepStatus.OK]
    print(f"完成：{len(report.items)} 个步骤，非OK {len(bad)} 个；"
          f"报告已写 data/processed/_report.json")
    for i in bad:
        print(f"  [{i.status.name}] {i.step}: {i.detail}")


def cmd_narrate(args) -> None:
    """F6 口播预生成：跑完整叙事链（故事→粤语旁白→TTS 音频）。"""
    from app.narrator.story import run_story_chain

    res = run_story_chain(args.pid, force=args.force)
    if res.get("audio"):
        print(f"[OK] {args.pid} 叙事+旁白+音频完成 "
              f"(story={len(res.get('story', ''))}字, degraded={res.get('degraded')})")
    else:
        print(f"[NG] {args.pid} 叙事完成但音频降级 degraded={res.get('degraded')}")


def _ask(question: str, settings=None) -> dict:
    """seam：评测批量问答入口（真实实现=docent.ask）。"""
    from app.agents.docent import ask

    return ask(question, settings=settings)


def _run_ragas(rows: list[dict], settings=None) -> dict:
    """seam：RAGAS 指标计算（懒加载重依赖，测试替换）。"""
    from app.eval.ragas_runner import run_ragas

    return run_ragas(rows, settings)


def _contexts(photo_ids: list[str], settings=None) -> list[str]:
    """seam：按 photo_ids 取证据文本（著录全字段），供 RAGAS 判卷。"""
    if not photo_ids:
        return []
    from app.infra.milvus_store import get_client

    s = settings or __import__("app.config",
                               fromlist=["Settings"]).Settings.load()
    client = get_client(s)
    out = []
    for pid in photo_ids[:5]:
        rows = client.query(
            collection_name=s.collection,
            filter=f'photo_id == "{pid}"',
            output_fields=["title", "year", "location", "caption"], limit=1)
        if rows:
            r = rows[0]
            meta = f"《{r.get('title')}》"
            if r.get("year"):
                meta += f"（{r['year']}）"
            if r.get("location"):
                meta += f"·{r['location']}"
            out.append(f"{meta}：{r.get('caption')}")
    return out


def cmd_eval_impl(questions_path, report_path, settings=None) -> bool:
    """F8：批量问答 → refused_accuracy + RAGAS 指标 → 报告落盘。

    返回是否达到验收线（faithfulness≥0.80 且 answer_relevancy≥0.75）。
    """
    import json
    import time
    from pathlib import Path as _Path

    rows = [json.loads(line) for line in
            _Path(questions_path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    answered, refusals = [], []
    for q in rows:
        res = _ask(q["question"], settings)
        entry = {"qid": q["qid"], "question": q["question"],
                 "answer": res.get("answer", ""),
                 "contexts": _contexts(res.get("photo_ids") or [], settings),
                 "refused": res.get("refused", False)}
        (refusals if q.get("refusal") else answered).append(entry)

    refused_correct = sum(
        1 for e in refusals if e["refused"]) if refusals else 0
    refused_accuracy = (refused_correct / len(refusals)) if refusals else None
    # 防刷分指标：应答题里被正确回答的比例（过度拒答会拉低它）
    answer_rate = (sum(1 for e in answered if not e["refused"])
                   / len(answered)) if answered else None

    ragas_rows = [e for e in answered if not e["refused"]]
    ragas_scores = (_run_ragas(ragas_rows, settings)
                    if ragas_rows else {})
    faith = float(ragas_scores.get("faithfulness", 0.0))
    relev = float(ragas_scores.get("answer_relevancy", 0.0))
    meets = (faith >= 0.80 and relev >= 0.75
             and refused_accuracy == 1.0 if refused_accuracy is not None
             else faith >= 0.80 and relev >= 0.75)

    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "total": len(rows), "answered": len(answered),
              "refusals": len(refusals),
              "refused_accuracy": refused_accuracy,
              "answer_rate": answer_rate,
              **ragas_scores, "meets_threshold": meets}
    out = _Path(report_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[eval] 报告已写入 {out} meets={meets}")
    return meets


def cmd_eval(args) -> None:
    from datetime import datetime
    from pathlib import Path

    ok = cmd_eval_impl(
        Path("eval/questions.jsonl"),
        Path("eval/reports") / f"{datetime.now():%Y%m%d-%H%M%S}.json")
    raise SystemExit(0 if ok else 2)


def cmd_zh_titles(args) -> None:
    """标题中文化：批量提炼/翻译馆藏档案名 → data/processed/titles-zh.json。"""
    from app.config import Settings
    from app.infra.milvus_store import get_client
    from app.ingest.title_zh import (
        build_titles_zh, clean_title, save_titles_zh,
    )

    s = Settings.load()
    rows = get_client(s).query(
        collection_name=s.collection,
        filter='photo_id != ""',
        output_fields=["photo_id", "title"],
        limit=1000,
    )
    if args.limit > 0:
        rows = rows[: args.limit]
    print(f"取到 {len(rows)} 条著录，开始提炼中文名……")
    mapping = build_titles_zh(rows, settings=s)
    out = save_titles_zh(mapping)
    orig = {str(r.get("photo_id")): clean_title(str(r.get("title") or ""))
            for r in rows}
    n_changed = sum(1 for k, v in mapping.items() if orig.get(k) != v)
    print(f"完成：{len(mapping)} 条 -> {out}（改写 {n_changed} 条）")


def cmd_refine(args) -> None:
    """云端精修：万相 imageedit 超分/修复 → 副产物 refined/repaired.jpg。

    只产出新文件，绝不覆盖 restored/colorized 主产物（保真红线）。
    """
    from pathlib import Path

    from app.config import Settings
    from app.infra.artifact import pick_background
    from app.ingest.cloud_refine import (
        MODEL, refine_image,
    )

    s = Settings.load()
    fn = {"sr": ("super_resolution", "refined.jpg"),
          "repair": ("description_edit", "repaired.jpg")}[args.function]
    function, out_name = fn

    if args.pid:
        pids = [args.pid]
    else:                                # --all：全量馆藏（用 Milvus 著录）
        from app.infra.milvus_store import get_client

        rows = get_client(s).query(
            collection_name=s.collection, filter='photo_id != ""',
            output_fields=["photo_id"], limit=1000)
        pids = [str(r.get("photo_id")) for r in rows]
    print(f"云端精修 model={MODEL} function={function} 待处理 {len(pids)} 张")
    ok_n = 0
    for pid in pids:
        d = Path("data/processed") / pid
        bg = pick_background(d)
        if bg is None:
            print(f"[NG] {pid}: 无本地底图(restored/colorized)，跳过")
            continue
        dst = d / out_name
        if dst.exists() and not args.force:
            print(f"[OK] {pid}: 已有 {out_name}，跳过(--force 重跑)")
            ok_n += 1
            continue
        t0 = __import__("time").time()
        okc = refine_image(bg, dst, function=function, settings=s)
        tag = "OK" if okc else "NG"
        if okc:
            ok_n += 1
        print(f"[{tag}] {pid}: {out_name} "
              f"({__import__('time').time() - t0:.0f}s)")
    print(f"完成 {ok_n}/{len(pids)}；副产物仅供人工比对采纳，未改主产物")


def cmd_enhance(args) -> None:
    """画质增强云链：纯上色+亮度合成(保脸)→enhanced.jpg 副产物。"""
    from pathlib import Path

    from app.config import Settings
    from app.ingest.enhance import build_enhanced

    if args.pid:
        pids = [args.pid]
    else:                                # --all：跳过已有 enhanced 的
        from app.infra.milvus_store import get_client

        s = Settings.load()
        rows = get_client(s).query(
            collection_name=s.collection, filter='photo_id != ""',
            output_fields=["photo_id"], limit=1000)
        pids = [str(r.get("photo_id")) for r in rows]
        if not args.force:
            pids = [p for p in pids
                    if not (Path("data/processed") / p /
                            "enhanced.jpg").exists()]
    print(f"E2 增强链待处理 {len(pids)} 张（--force 重跑已有）")
    ok_n = 0
    for i, b in enumerate(pids, start=1):
        t0 = __import__("time").time()
        ok = build_enhanced(b)
        ok_n += bool(ok)
        tag = "OK" if ok else "NG(降级沿用原产物)"
        print(f"[{tag}] ({i}/{len(pids)}) {b}: "
              f"({__import__('time').time() - t0:.0f}s)", flush=True)
    print(f"完成 {ok_n}/{len(pids)}；详情页/文创自动优先用 enhanced.jpg")


def cmd_tailor(args) -> None:
    """比稿候选：定制提示词 + E2 保脸 → enhanced-archive/tailored-{pid}.jpg。"""
    from pathlib import Path

    from app.config import Settings
    from app.infra.milvus_store import get_client
    from app.ingest.enhance import build_candidate

    s = Settings.load()
    if args.pid:
        pids = [args.pid]
        rows = {args.pid: {}}
    else:
        rows = {str(r.get("photo_id")): r for r in get_client(s).query(
            collection_name=s.collection, filter='photo_id != ""',
            output_fields=["photo_id", "title", "year", "location",
                           "caption"], limit=1000)}
        pids = list(rows)
    print(f"定制候选待生成 {len(pids)} 张（产物落 enhanced-archive/ 待人工评审）")
    ok_n = 0
    for i, b in enumerate(pids, start=1):
        dest = (Path("data/processed") / b / "enhanced-archive" /
                f"tailored-{b}.jpg")
        if dest.exists() and not args.force:
            print(f"[SKIP] ({i}/{len(pids)}) {b}: 候选已存在")
            continue
        t0 = __import__("time").time()
        ok = build_candidate(b, settings=s, row=rows.get(b) or {})
        ok_n += bool(ok)
        tag = "OK" if ok else "NG"
        print(f"[{tag}] ({i}/{len(pids)}) {b}: "
              f"({__import__('time').time() - t0:.0f}s)", flush=True)
    print(f"完成 {ok_n}/{len(pids)}；到 /review 页逐张评审启用")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="lingnan", description="岭南非遗 AI 策展人")
    sub = p.add_subparsers(dest="cmd", required=True)

    ig = sub.add_parser("ingest", help="入库管线：修复→上色→OCR→描述→向量化→Milvus")
    ig.add_argument("--src", default="data/raw", help="素材目录(含 meta.csv)")
    ig.add_argument("--limit", type=int, default=0, help="只处理前 N 张(0=全部)")
    ig.add_argument("--pid", default="",
                    help="只入库指定 photo_id（上传通道用）")
    ig.set_defaults(func=cmd_ingest)

    na = sub.add_parser("narrate", help="口播预生成：讲解词→粤语 TTS 音频")
    na.add_argument("--pid", required=True, help="photo_id")
    na.add_argument("--force", action="store_true", help="忽略已有缓存强制重生成")
    na.set_defaults(func=cmd_narrate)

    ev = sub.add_parser("eval", help="RAGAS 评测：批量问答→指标→报告")
    ev.add_argument("--questions", default="eval/questions.jsonl")
    ev.set_defaults(func=cmd_eval)

    zt = sub.add_parser("zh-titles",
                        help="标题中文化：批量提炼馆藏档案名→titles-zh.json")
    zt.add_argument("--limit", type=int, default=0, help="只处理前 N 条(0=全部)")
    zt.set_defaults(func=cmd_zh_titles)

    rf = sub.add_parser("refine",
                        help="云端精修：万相超分/修复→副产物图(不覆盖主产物)")
    rf.add_argument("--pid", default="", help="单张 photo_id；与 --all 二选一")
    rf.add_argument("--all", action="store_true", help="全量馆藏")
    rf.add_argument("--function", choices=("sr", "repair"), default="sr",
                    help="sr=超分保真(默认)；repair=划痕霉斑修复(需人工审)")
    rf.add_argument("--force", action="store_true", help="重跑已有副产物")
    rf.set_defaults(func=cmd_refine)

    en = sub.add_parser("enhance",
                        help="画质增强链(E2保脸)：纯上色+亮度合成→enhanced.jpg")
    en.add_argument("--pid", default="", help="单张 photo_id；与 --all 二选一")
    en.add_argument("--all", action="store_true", help="全量馆藏(跳过已有)")
    en.add_argument("--force", action="store_true", help="重跑已有 enhanced")
    en.set_defaults(func=cmd_enhance)

    tl = sub.add_parser("tailor",
                        help="比稿候选：定制提示词+E2保脸→enhanced-archive(待评审)")
    tl.add_argument("--pid", default="", help="单张 photo_id；与 --all 二选一")
    tl.add_argument("--all", action="store_true", help="全量馆藏")
    tl.add_argument("--force", action="store_true", help="重新生成已有候选")
    tl.set_defaults(func=cmd_tailor)

    for name in ("serve",):
        sp = sub.add_parser(name)
        sp.set_defaults(func=_not_impl(name))

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
