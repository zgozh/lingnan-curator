# ADR-0006：Agent 编排用 LangGraph 三图结构
状态：已接受
背景：策展/讲解/文创三个 Agent 流程各异（讲解员需强制证据检索+拒答路由），需要可控的条件路由而非 if-else 堆叠。
方案：每 Agent 一个独立 graph 文件（main_graph + state + nodes + prompt 分离，DocMind 目录模板）；讲解员图内置"检索空→固定拒答"条件边；SSE 流式从 LangGraph 事件流桥接。
理由：DocMind 已验证同款编排；三人格共享 retrieval 但 prompt/state 隔离，互不污染。
代价：LangGraph 学习成本已在 DocMind 支付；新增需求若超出三图能力再评估，不预先加框架（YAGNI）。
人工资源依赖：无新增。验证命令：对 mock 检索结果单测三图各跑通一条 happy path。
