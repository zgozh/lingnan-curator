# W2 实现计划 —— F2 混合检索 + 三 Agent + Web 展馆最小闭环

对应 spec F2/F3/F4/F5/F7；验收锚点：场景 1（骑楼检索前 3）、场景 2 前半（带证据回答+超范围拒答）、
验收标准「停掉 rerank 仍可用且标记 degraded」。F6/F8 属 W3。

## 任务分解（TDD，外部服务一律 mock；每任务独立提交）

### T1 检索基元 `app/retrieval/searcher.py`
- MilvusClient.hybrid_search(emb_dense COSINE + emb_sparse IP, WeightedRanker(0.8, 0.2)) 文本通道
- CLIP 通道 `search(emb_clip IVF_SQ8)`（查询图可选，缺省关闭）
- 两通道 RRF(k=60) 融合 → norm_score 归一（DocMind 配方）
- Milvus 异常→抛给上层（连接类错误由 T3 转 503 中文提示）；CLIP 失败→纯文本通道 + degraded 标志
- 测试：fake client 验证权重参数/RRF 排序公式/归一化区间 [0,1]

### T2 精排客户端 `app/infra/reranker.py`
- HTTP POST `{RERANK_BASE_URL}/rerank`（query + documents[] → scores[]）；超时 5s
- 任何失败返回 None（=跳过精排），绝不抛出；`health()` 供展馆状态栏
- 测试：mock httpx/openai——成功/超时/500/未配置 四态
- 注：qwen3-rerank 本地服务于 W3 全量素材阶段再起（RERANK_BASE_URL 空 = 直通降级路径）

### T3 检索门面 `app/retrieval/pipeline.py`
- `search(query, top_k=8, image_path=None) -> SearchResult{hits[], degraded:set}`
- 流程：T1 融合 → T2 精排（可跳过，记 degraded）→ 归一 → **断崖截断**：
  分数 < max_score×0.35 或累计 ≥12 条即断（动态 top-k）
- hits 元素：photo_id/title/year/location/caption/score/degraded
- 测试：断崖边界/精排重排生效/rerank=None 时顺序不变且 degraded 含 "rerank"

### T4 LLM 基座扩展 `app/infra/llm_client.py`
- `chat(messages, json_mode=False)` 与 `stream_chat(messages)`（生成器）；复用 DashScope OpenAI 兼容端点
- JSON 防御解析抽到 `app/utils/json_utils.py`（extract_json 从 caption_op 上移共用）
- 测试：fake openai client；json_mode 解析容错

### T5 讲解员 Agent F4 `app/agents/docent.py`
- LangGraph StateGraph：retrieve(T3) → answer(LLM, 强制引用 photo_id) ；无证据/超范围 → 拒答模板节点
- 输出 `Answer{answer, photo_ids[], refused}`；`stream_answer()` 供 SSE
- 测试：有证据带引用；检索空→refused；LLM 编造无证据 photo_id→过滤为 refused

### T6 策展人 F3 + 文创 F5 `app/agents/{curator,creator}.py`
- curator：主题词→T3 取池→LLM 输出展览 JSON `{sections:[{title,narrative,photo_ids[]}]}`
- creator：photo_id+type(明信片/slogan/朋友圈)→文案 JSON；photo_id 不存在→404 语义
- 测试：JSON 防御/空池降级/非法 type 校验

### T7 Web 展馆 F7 `app/web/`
- FastAPI + Jinja2 服务端渲染；页面：首页照片墙 / 详情(原图↔上色对比滑块+OCR/caption) /
  搜索结果 / 问答(SSE fetch 流式渲染) / 专题展览
- `/api/health`：Milvus 未启动 → 中文提示 + 启动命令（spec 边界案例），不挂死
- 静态资源原生 JS/CSS，不上前端框架（spec Out-of-scope 红线）
- 测试：TestAsyncClient 页面 200/health 降级分支/SSE content-type

### T8 W2 e2e 冒烟
- 起 uvicorn → curl 验证：搜"骑楼"命中 sample_a（当前馆藏仅 3 张，验证机制而非排序质量）
- 问"西关大屋特点"带证据路径；问"2025 广州地铁"走拒答
- PROGRESS 更新 + 收尾

## 新增依赖
langgraph、jinja2、uvicorn[standard]、httpx（测试与 reranker 共用）

## 明确不做（本周期）
- qwen3-rerank 服务真实部署（W3）、口播 F6、RAGAS F8、前端框架化
