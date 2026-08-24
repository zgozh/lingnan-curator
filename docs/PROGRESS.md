# PROGRESS —— lingnan-curator

## 当前阶段
**阶段 3（拆任务）完成**：W1 实现计划已落盘 `docs/superpowers/plans/2026-08-24-w1-ingest-pipeline.md`（10 个任务，TDD 步进）。等待用户选定执行方式后进入阶段 4。

## 已完成
- [2026-08-24] （上一会话）参赛方案拍板：「湾区记忆·岭南非遗 AI 策展人」；创建目录并 git init
- [2026-08-24] 三条技术路线补拍板：①修复上色=本地开源；②粤语口播=云TTS+本地口型；③素材=小批先行 ✅ 门禁 1 通过
- [2026-08-24] 开工三件套落盘：`AGENTS.md`、`docs/PROGRESS.md`、spec 设计稿；补 `.gitignore` 与 `.env.example`（提交 578494d）
- [2026-08-24] **阶段 2 完成**：市场调研（口型/TTS/修复上色/OCR 四个决策点实查）→ `docs/architecture.md`（分层/模块边界/依赖规则/选型表/数据模型/风险表/人工准备清单）+ `docs/adr/ADR-0001~0009` 全部落盘
- [2026-08-24] 调研关键修正：口型主选 **SadTalker**（EchoMimicV2 官方 ≥16GB 显存出局；LivePortrait 是视频驱动不匹配）；粤语 TTS 改为 Provider 接口+三路试听定稿

## 环境状态（2026-08-24 实测）
- GPU：RTX 4060 Laptop 8GB ✅（模型分步加载，避免同时驻留显存）
- 工具链：uv 0.11.28 + Python 3.12.4 ✅
- Docker Desktop：未运行 ⚠️（跑 Milvus 前需手动启动）
- DASHSCOPE_API_KEY：未注入系统环境变量 → 项目统一走 `.env`（沿用 DocMind 习惯）

## 待办
### 人（按优先级）
- [ ] **评审阶段 2 产物**（`docs/architecture.md` + 9 条 ADR），确认后放行阶段 3 拆任务
- [ ] 准备 DashScope API key（DocMind 账号可复用）、收集首批 15~30 张公开版权岭南老照片 + 补全 `data/raw/meta.csv`
- [ ] W3 前：粤语 TTS 三路试听盲选（AI 会先备好样音与试听稿）、安装 ffmpeg
- [ ] 用时启动 Docker Desktop（Milvus）
### AI
- [ ] 阶段 3：加载 writing-plans，产出 W1 实现计划（入库管线 + 3 张样张 spike 排雷 vendor 环境）
- [ ] 阶段 4：TDD 逐任务实现

## 决策记录索引
- ADR-0001 技术基座沿用 DocMind 配方
- ADR-0002 修复上色 = CodeFormer + DDColor(主)/DeOldify(兜底)，vendor 子进程
- ADR-0003 OCR = RapidOCR（PaddleOCR 升级备选）
- ADR-0004 LLM/VLM = DashScope qwen-plus / qwen-vl-plus
- ADR-0005 检索 = Milvus + BGE-M3(dense+sparse) + CLIP 双通道 RRF
- ADR-0006 Agent 编排 = LangGraph 三图
- ADR-0007 粤语 TTS = TTSProvider 接口 + DashScope/Azure/本地Yue 三路试听定稿
- ADR-0008 口型 = SadTalker（EchoMimicV2 出局/LivePortrait 排除）
- ADR-0009 评测 = ragas + DashScope judge

## 验证命令 / 冒烟记录
- 暂无代码，冒烟未开始。首次冒烟目标：W1 末——3 张真实样张端到端入库。
