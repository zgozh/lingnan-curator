# ADR-0004：生成与图片理解统一走 DashScope（qwen-plus / qwen-vl-plus）
状态：已接受
背景：三 Agent 文案生成、照片 caption/tags、RAGAS judge 都需要 LLM/VLM。
方案：文本=qwen-plus（复杂策划任务可升 qwen-max），图片理解=qwen-vl-plus，经 OpenAI 兼容端点接入，客户端封装在 `app.infra.llm`，超时/重试/空响应防御照搬 DocMind 经验。
理由：DocMind 已验证；账号与 key 均已有（复用优先）；Ollama 本地 8GB 显存放不下与 4060 并存的生成模型，不考虑。
代价：云端依赖与少量按量费用；VLM 故障时 caption 降级为标题+元数据拼接（spec 已定义）。
人工资源依赖：把已有 DashScope key 写入 `.env`（不入 git）。验证命令：一次真实 `qwen-vl-plus` 图片描述调用返回 JSON。
