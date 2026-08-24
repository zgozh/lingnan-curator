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


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="lingnan", description="岭南非遗 AI 策展人")
    sub = p.add_subparsers(dest="cmd", required=True)

    ig = sub.add_parser("ingest", help="入库管线：修复→上色→OCR→描述→向量化→Milvus")
    ig.add_argument("--src", default="data/raw", help="素材目录(含 meta.csv)")
    ig.add_argument("--limit", type=int, default=0, help="只处理前 N 张(0=全部)")
    ig.set_defaults(func=cmd_ingest)

    for name in ("serve", "narrate", "eval"):
        sp = sub.add_parser(name)
        sp.set_defaults(func=_not_impl(name))

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
