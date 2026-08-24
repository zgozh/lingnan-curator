# PROGRESS —— lingnan-curator

## 当前阶段
**阶段 4 实现中（W1）**：Task 1~9 完成（TDD 全绿 50 tests），T7 vendor spike 实测双通（restore+colorize 真实出图）。剩 T10 e2e 冒烟——仅差 Milvus 启动（用户跑 `docker compose up -d milvus`）。

## W1 执行记录
- [2026-08-24] Task1 ✅ ec80256 骨架+Settings+PhotoRecord/IngestReport
- [2026-08-24] Task2 ✅ 24e00cf Milvus compose(单容器)+存储层先删后插幂等；license/source_url 入 schema（测试驱出的补充）
- [2026-08-24] Task3 ✅ e5c32c2 meta.csv 版权校验器；自写 tmp_path fixture
- [2026-08-24] Task4 ✅ fded549 OCR 节点（RapidOCR 惰性单例，降级返回空串）
- [2026-08-24] Task5 ✅ c89dbbb DashScopeVLM 客户端+caption JSON 防御清洗+降级拼接
- [2026-08-24] Task6 ✅ 5dfd138 Embedder 双塔单例(BGE-M3+Chinese-CLIP)+free() 显存纪律；torch 2.13.0+cpu / transformers / FlagEmbedding 已入库
- [2026-08-24] Task7 ✅ **vendor spike 全通**：CF restore=True(21s) + DDColor colorize=True(17s)，样张真实出图（见下方 spike 结论）
- [2026-08-24] Task8 ✅ b48ed55/f75818e/050f599 pipeline 编排+CLI ingest 子命令；caption 无 key 构造失败也走降级
- [2026-08-24] Task9 ✅ 9f45106 README 六步快速开始 + `.env` 骨架

### T7 vendor spike 结论（重要，后续会话必读）
- **CodeFormer**：用其仓库自带 vendored basicsr（缺 `basicsr/version.py`，已手补最小版）；venv-cf 需显式装 `lpips` 等。PyPI `basicsr` sdist 在沙箱内构建被拒 → 不 pip 安装 basicsr。
- **DDColor**：推理入口是 `scripts/infer.py`（目录进/出）；huggingface_hub 1.28 与 hf-mirror 元数据校验不兼容（FileMetadataError）→ 改从 **ModelScope 直链**下载权重到 `models/vendor/DDColor/pretrain/pytorch_model.pt`，代码优先 `--model_path` 本地模式。
- **权重清单**（均已就位）：CodeFormer release v0.1.0 的 codeformer.pth(377MB)/detection_Resnet50_Final(109MB,legacy pickle 格式非 zip)/parsing_parsenet(85MB)/RealESRGAN_x2plus(67MB)；GFPGANv1.4.pth(349MB) 来自 TencentARC release v1.3.0；DDColor 912MB 来自 ModelScope。
- **下载不稳对策**：`scripts/fetch_resumable.py`（Range 断点续传循环重试）。注意：GitHub CDN 大文件常截断；facexlib/gfpgan 权重是 legacy pickle 格式，zipfile 体检会误报 BAD，以文件头 `\x80\x02` 判格式。
- vision_ops 已固化：子进程 env 注入 `HF_ENDPOINT=hf-mirror`、`HF_HOME=models/hf-cache`、`PYTHONPATH=DDColor仓库`（借 basicsr）；所有传给 vendor 的路径强制 resolve() 绝对路径（子进程 cwd 在 vendor 目录内）。

### 沙箱环境适配（重要，后续会话必读）
- uv 缓存重定向：每次调 uv 前设 `$env:UV_CACHE_DIR='<workspace>\.uv-cache'`（系统缓存目录被沙箱拒）
- pytest 禁用 cacheprovider；**内置 tmp_path/basetemp 的"整树删建"会触发沙箱拒绝并留下 ACL 损坏目录**——已用 `tests/conftest.py` 自写 tmp_path（data/test-runs/ 下唯一目录）替代，勿改回
- 根目录 `pytest-cache-files-*` 与 `.pytest-tmp` 为损坏垃圾目录（无法删除），已被 testpaths=tests 无害化，可手动删
- torch 当前为 CPU 版；Task10 e2e 前切 cu121：pyproject 加 `[[tool.uv.index]] name="pytorch-cu121" url="https://download.pytorch.org/whl/cu121" explicit=true` + `[tool.uv.sources] torch={index="pytorch-cu121"}` 后 `uv sync`
- docker CLI 被沙箱命名管道策略挡（提权被用户取消）→ Milvus 启动由用户在自己终端执行 `docker compose up -d milvus`；应用侧走 TCP 不受影响

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
