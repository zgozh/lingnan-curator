# ADR-0001：技术基座沿用 DocMind 配方
状态：已接受
背景：项目需 FastAPI 服务 + 多步 Agent 编排 + 向量检索，单人一个月工期不允许重新试错基础件。
方案：uv + Python 3.12 + FastAPI + LangGraph + Milvus standalone(docker compose) + BGE-M3 + qwen3-rerank + DashScope(OpenAI 兼容)。
理由：全套在本人 DocMind 项目生产验证过；"复用你已经有的"是第一优先级。
代价：绑定 Docker Desktop 与 DashScope 云端可用性（均有降级预案，见 spec 边界案例）。
人工资源依赖：无新增安装；需在 W1 核对 DocMind 的 BGE-M3/qwen3-rerank 权重缓存与服务启动方式。验证命令：`uv --version && python --version`。
