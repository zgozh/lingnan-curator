# ADR-0009：RAGAS 评测作为质量闭环与答辩差异化武器
状态：已接受
背景：spec 场景 3 要求 faithfulness ≥ 0.80 / answer_relevancy ≥ 0.75 的量化报告，这是答辩核心差异点。
方案：ragas 库 + DashScope OpenAI 兼容端点做 judge（LLMWrapper 指向 qwen-plus）；评测集 ≥20 条（含 ≥3 条超范围拒答样本）存 `eval/dataset.jsonl`；报告输出 JSON+Markdown 到 `eval/reports/`（gitignore，答辩版手动保留）。版本在 requirements 中钉死，W3 第一天先用 3 条样本冒烟验证兼容性。
理由：库现成、指标权威、与 LangChain 生态兼容；自写 LLM 评分无公信力且重复造轮子。
代价：judge 调用按量计费（一次全量约几十次调用，成本可忽略）；ragas 版本升级频繁需锁版。
人工资源依赖：无新增（key 复用）。验证命令：`python -m app.cli eval --smoke 3` 输出四指标 JSON。
