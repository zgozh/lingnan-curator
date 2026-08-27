# architecture.md —— lingnan-curator

> 阶段 2 产出。门禁 2 通过前不得拆任务。配套决策记录见 `docs/adr/`。

## 总体分层

```
入口层    CLI(python -m app.cli)                    Web 展馆(FastAPI :8300, Jinja2+SSE)
             │                                          │
业务层    ingest 入库管线          agents(LangGraph:策展/讲解/文创)      narrator 口播预生成
             └────────────────┬──────────────────────┘                    │
检索层              retrieval(混合检索+RRF+精排+降级链)                      │
                         │                                                │
基础设施   milvus│bge-m3│clip│qwen3-rerank│dashscope(llm/vlm/tts)│本地视觉模型(修复/上色/OCR/口型,子进程)
```

## 模块边界

| 模块 | 职责 | 不做什么 |
|------|------|---------|
| `app.cli` | 统一入口：ingest / serve / narrate / eval 子命令 | 不含业务逻辑 |
| `app.config` | dataclass 配置 + `.env` 加载 + 路径常量 | 不读业务数据、不发网络请求 |
| `app.infra` | milvus / embedder(BGE-M3+CLIP) / reranker / llm(vlm) / tts 客户端封装与健康检查 | 不做业务判断；不含降级策略（降级归上层编排） |
| `app.ingest` | F1 管线编排：修复→上色→OCR→描述→向量化→入库，逐步降级，产出批次报告 | 不被 Web 在线路径调用（离线批处理） |
| `app.retrieval` | F2 混合检索：RRF 融合→精排→归一化→断崖截断 | 不知道调用者是 Web 还是 Agent |
| `app.agents` | F3/F4/F5 三个 LangGraph 图 + prompt | 不直接触 Milvus/模型客户端（一律经 retrieval 与 infra 接口） |
| `app.narrator` | F6：讲解词→TTS 音频→SadTalker 子进程→mp4 | 不进入在线请求链路；失败只影响口播功能 |
| `app.web` | F7 页面渲染 + SSE + 静态资产 | 不 import 模型客户端；只调 retrieval/agents |
| `app.eval` | F8：RAGAS 评测执行与报告落盘 | 只读评测集，不改库 |

### narrator 分层（叙事链，重构后）

`app/narrator` 把口播从"元数据拼讲解词"升级为一条 4-Agent 叙-链（ADR-0010）：
`VLM 洞察 → qwen-max 故事 → qwen-plus 旁白 → qwen-plus 审稿 →（score<85 回炉，≤1 次）→ CosyVoice TTS 按句合成`。
各 Agent 是纯函数单元，提示词集中于 `app/narrator/prompts.py`，"AI 味"拦截做成不依赖 LLM 的
确定性硬闸（`app/narrator/detox.py`：禁用词扫描 + 结构校验）。CLI（`cmd_narrate`）与 Web
（`photo_page` 调 `run_story_chain(photo_id)`）共用同一编排器；编排器幂等（产物缓存），任何一环
失败只降级（`degraded`/`audio` 标记）、绝不上抛异常。

## 依赖规则
- 上层可依赖下层，禁止反向：`web/cli → agents/narrator/eval → retrieval → infra → config`
- `retrieval` 不得 import `agents`/`web`（保证检索可独立测试）
- 一切外部网络调用（DashScope/TTS 云）只出现在 `app.infra` 客户端内；本地重型模型（CodeFormer/DDColor/RapidOCR/SadTalker）以 **vendor 仓库 + 独立环境 + 子进程** 方式只在 `infra` 或 `narrator` 出现
- 所有昂贵资源（嵌入模型、Milvus 连接、客户端）单例化，进程内复用

## 技术选型决策表

> 已做过市场调研（2026-08-24，web_search/GitHub/HF 实查）；每行含"现成方案 vs 自研"对照。详细候选见下表之后。

| 决策点 | 选项（现成 vs 自研） | 选择 | 理由 | 代价 | 人工资源依赖 |
|--------|---------------------|------|------|------|-------------|
| 人脸修复 | 现成 GFPGAN / 现成 CodeFormer / 自研 | **CodeFormer** | 老照片破损重，保真度权重 w 可调，效果上限更高 | BasicSR 依赖在 Windows 有坑→vendor+子进程 | 首次下载权重约 380MB（hf-mirror 加速） |
| 上色 | 现成 DeOldify / 现成 DDColor / 云 API 付费 / 自研 | **DDColor 主选，DeOldify 兜底** | DDColor 更新且色彩更自然、纯 torch 栈；DeOldify 作环境失败备胎 | vendor repo + 独立环境 | 首次下载权重约 2GB |
| OCR | 现成 PaddleOCR / 现成 RapidOCR / 云 OCR | **RapidOCR（PaddleOCR 为升级备选）** | pip 即装、onnxruntime、CPU 可用；OCR 属可降级信号，接入成本优先 | 繁体艺术招牌识别率有限（预期管理：caption 主要靠 VLM） | 无 |
| LLM/VLM | DashScope qwen / OpenAI / Ollama 本地 / 自研 | **DashScope qwen-plus + qwen-vl-plus** | DocMind 已验证配方，key 已有 | 云端按量费用（低） | `DASHSCOPE_API_KEY` 写入 `.env` |
| 向量检索 | Milvus+BGE-M3+Chinese-CLIP+qwen3-rerank（DocMind 配方）/ Chroma / Qdrant | **沿用 DocMind 配方，图像编码器定为 Chinese-CLIP ViT-B/16** | 四件套全部已在本人项目验证，权重本机已有缓存；查询词是中文故弃 OpenAI CLIP（中文文本塔弱） | Docker Desktop 依赖 | 用时启动 Docker Desktop；W1 核对 DocMind 权重缓存路径 |
| Agent 编排 | LangGraph / 手写状态机 / 自研 | **LangGraph** | 条件路由/fan-out 已验证，复用学习成本 | 无新增 | 无 |
| 粤语 TTS | DashScope cosyvoice（复用账号）/ Azure zh-HK / 火山引擎 / 本地 Cosyvoice2-Yue 开源权重 / 自研 | **TTSProvider seam，试听定稿；先实测 DashScope 粤语能力** | 复用现有账号最省；三家云端+一家本地都保留候选 | 半小时试听工作 | 同一段 200 字粤语稿试听对比；DashScope 不支持则注册 Azure |
| 口型视频 | SadTalker / EchoMimicV2·V3 / LivePortrait / 云端数字人 / 自研 | **SadTalker** | 输入=照片+音频恰好匹配；约 4~6GB 显存适配 4060；Windows 教程成熟。EchoMimicV2 官方实测 ≥16GB 显存出局，LivePortrait 视频驱动不匹配 | 画质一般（够用）；需独立 py3.10 环境 | vendor repo + ffmpeg；权重约 4GB |
| RAGAS 评测 | ragas 库 / 手写 LLM 评分 | **ragas + DashScope OpenAI 兼容端点做 judge** | 竞赛差异化武器，库现成 | 版本兼容需钉死 | 无新增（key 复用） |

### 候选清单明细（调研快照 2026-08-24）
- **口型类**：SadTalker（成熟/免费/Windows 指南多/约 5GB）；[EchoMimicV2](https://github.com/antgroup/echomimic_v2)（CVPR2025/质量好/官方 GPU=A100·4090·V100≥16G/Linux 向）；[EchoMimicV3](https://raw.githubusercontent.com/antgroup/echomimic_v3/main/README.md#1)（1.3B 新发布/生态尚嫩）；LivePortrait 及 [FasterLivePortrait](https://raw.githubusercontent.com/warmshao/FasterLivePortrait/master/README.md#1)（**视频驱动**，与"照片+音频"输入不匹配，排除）；腾讯智影/HeyGen（付费云端，仅最后保险）
- **粤语 TTS 类**：DashScope cosyvoice（复用账号/粤语发音人待实测）；Azure Speech `zh-HK-HiuMaanNeural` 等（稳定/约 $15/百万字符）；火山引擎豆包语音（粤语音色多/需新注册）；[ASLP-lab Cosyvoice2-Yue-ZoengJyutGaai](https://huggingface.co/ASLP-lab/Cosyvoice2-Yue-ZoengJyutGaai)（开源粤音微调权重/零 API 成本/本地环境重，作答辩彩蛋非主链路）
- **修复上色类**：CodeFormer / GFPGAN（人脸修复双雄）；DDColor vs DeOldify 有社区实战对比（DDColor 色彩更佳）；微软 Bringing-Old-Photos-Back-to-Life（划痕修复强但环境老旧，列为划痕严重时的可选第三步，默认不做）
- **OCR 类**：[RapidOCR](https://rapidai.github.io/RapidOCRDocs/v2.1.0/model_list/)（轻量跨平台 CPU 可用）；PaddleOCR 官方（繁体 zh_CHT 模型全但 paddlepaddle 重）；讯飞/百度云 OCR（按量付费，不必要）

## 数据模型
- `data/raw/meta.csv`：`photo_id,title,year,location,source_url,license`（license/source_url 必填，缺失拒收）
- `data/processed/{photo_id}/`：`restored.jpg`、`colorized.jpg`、`ocr.txt`、`caption.json{description,tags[],model}`
- Milvus collection `lingnan_photos`：
  - `photo_id`(VARCHAR, 主键)、`title/year/location`(VARCHAR)、`caption`(VARCHAR)、`ocr_text`(VARCHAR)、`has_colorized`(Bool)
  - `emb_dense`(FLOAT_VECTOR, 1024, BGE-M3 dense)、`emb_sparse`(SPARSE_FLOAT_VECTOR, BGE-M3 sparse)、`emb_clip`(FLOAT_VECTOR, 512)
  - 索引：dense=HNSW(COSINE)、sparse=SPARSE_INVERTED_INDEX(IP)、clip=IVF_SQ8(COSINE)；混合打分沿用 DocMind：COSINE 0.8 + IP 0.2 → norm_score 归一 → RRF 与 CLIP 通道融合
- 口播产物：`data/processed/{photo_id}/narration.wav + narration.mp4`

## 风险点
| 风险 | 影响 | 解法 |
|------|------|------|
| 8GB 显存多模型并存 OOM | 管线中断 | 分阶段串行加载+单例管理器，每阶段用完释放（W1 首个 spike 验证） |
| CodeFormer/DDColor/SadTalker 独立环境在 Windows 装不上 | 对应功能缺失 | vendor 固定 commit+独立 venv+子进程隔离；上色失败→只交修复图（spec 边界案例已定义）；W1 做 3 张样张 spike 提前排雷 |
| DashScope cosyvoice 无粤语发音人 | TTS 主选失效 | Azure 兜底，TTSProvider seam 半天切换；本地 Yue 权重作最终保险 |
| RAGAS 与 langchain/dashscope 版本兼容 | 评测延期 | requirements 钉死版本，W3 第一天先跑通 3 条样本冒烟 |
| HF 权重下载慢/被墙 | 环境就绪延迟 | `HF_ENDPOINT=https://hf-mirror.com` 写进 README；下载脚本断点续传 |
| 繁体艺术字 OCR 率低 | 检索召回下降 | 期望定位=锦上添花信号；caption(VLM)+title+元数据承担主要文本召回 |
| 素材版权瑕疵 | 参赛合规风险 | 入库硬校验 license+source_url；来源登记表随申报书提交 |

## 《人工准备清单》（各 ADR 依赖汇总）
| # | 事项 | 何时需要 | 验证方式 |
|---|------|---------|---------|
| 1 | DashScope API key 填入 `.env` | W1 起 | 一次真实 qwen-vl 调用成功 |
| 2 | 首批 15~30 张公开版权照片 + 补全 `meta.csv` 六列 | W1 末 | 目录文件数 = CSV 行数 |
| 3 | 用时启动 Docker Desktop | W1（Milvus） | `docker ps` 正常返回 |
| 4 | 同一粤语稿对 DashScope/Azure(/火山) 各生成一段试听并拍板 | W3 前 | 三段音频人耳盲选 |
| 5 | （仅当 DashScope 无粤语）注册 Azure Speech 取 key | W3 前 | `.env` 有 AZURE_SPEECH_KEY |
| 6 | 安装 ffmpeg（SadTalker 合成需要） | W3 前 | `ffmpeg -version` |
| 7 | 模型权重批量下载（AI 提供脚本，首次约 6~7GB 流量） | W1 后台并行 | 各 vendor 权重目录非空 |
