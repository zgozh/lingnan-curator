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


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="lingnan", description="岭南非遗 AI 策展人")
    sub = p.add_subparsers(dest="cmd", required=True)

    ig = sub.add_parser("ingest", help="入库管线：修复→上色→OCR→描述→向量化→Milvus")
    ig.add_argument("--src", default="data/raw", help="素材目录(含 meta.csv)")
    ig.add_argument("--limit", type=int, default=0, help="只处理前 N 张(0=全部)")
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

    for name in ("serve",):
        sp = sub.add_parser(name)
        sp.set_defaults(func=_not_impl(name))

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
