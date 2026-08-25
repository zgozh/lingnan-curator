# lingnan-curator · 湾区记忆·岭南非遗 AI 策展人

把公开版权（Public Domain / CC0 / CC BY / CC BY-SA）的岭南老照片，经「修复上色 → OCR → 多模态混合检索 → 三 Agent」，变成**可逛、可问、可听**的 Web 展馆。
（广州大学第二届「庆园杯」AI 创新应用大赛 · 主题三参赛项目，单人开发）

> 设计文档 `docs/superpowers/specs/2026-08-24-lingnan-curator-design.md` · 架构 `docs/architecture.md` · 决策记录 `docs/adr/` · 进度 `docs/PROGRESS.md`

## 核心亮点

- **真实语料 24 张**：Wikimedia Commons 公有领域广州历史老照片（1840s~1940s），meta.csv 六列著录齐全、均可溯源
- **RAGAS 评测进答辩**：faithfulness **0.888** / answer_relevancy **0.858** / 拒答准确率 **1.0**（qwen-max 判卷），报告落盘可复现
- **全 GPU 链路**：BGE-M3 + Chinese-CLIP 双塔嵌入、qwen3-rerank 精排均跑在本地 RTX 4060
- **三 Agent**：策展人（主题→展览）、讲解员（检索增强回答，防幻觉三道闸+SSE 流式）、文创（海报/明信片/伴手礼）
- **粤语口播**：CosyVoice 粤语三音色于详情页自选，SadTalker 口型视频预生成
- **降级铁律**：rerank/CLIP/VLM/TTS 任一外部依赖失败，主链路照常可用（只标记 degraded）

## 功能一览（Web 展馆）

| 入口 | 说明 |
|---|---|
| `/` | 照片墙（馆藏总览） |
| `/search?q=…` | 多模态混合检索（文本/图像双通道 → RRF → rerank 精排） |
| `/photo/{id}` | 详情页：修复上色对比滑块、OCR 文本、粤语口播、音色自选、文创按钮 |
| `/exhibit` | 专题展（策展人 Agent 生成） |
| `POST /api/ask` | 讲解员问答（SSE 流式，超范围自动拒答） |
| `POST /api/create/{id}` | 文创生成（三类型） |

## 技术架构

```
data/raw(material+meta.csv) → ingest: 修复(CodeFormer)→上色(DDColor)→OCR(RapidOCR)
  →caption(qwen-vl-plus)→嵌入(BGE-M3 dense+sparse / CLIP)→ Milvus(lingnan_photos)
                                                        ↓
检索: WeightedRanker(0.8/0.2)+CLIP → RRF(k=60) → qwen3-rerank 精排 → 断崖截断
                                                        ↓
Web: 照片墙/搜索/详情/专题展 ← 三 Agent(docent/curator/creator) ← DashScope LLM
                                                        ↓
口播: narrator(粤语讲解词) → CosyVoice TTS → SadTalker 数字人视频
```

模块依赖只能自上而下（`web/agents/narrator → retrieval → infra`），禁止反向。

## 前置条件

- Windows + NVIDIA GPU ≥8GB（开发机 RTX 4060 Laptop 8GB）
- [uv](https://docs.astral.sh/uv/)；[Docker Desktop](https://www.docker.com/products/docker-desktop/)（仅跑 Milvus）
- Python 3.12（uv 自动创建 `.venv`）；SadTalker 额外独立 venv（`venv-st`，见 `docs/PROGRESS.md`）
- 无需安装系统 ffmpeg（SadTalker 走仓库内 ffmpeg 垫片）

## 快速开始

```bash
# 0) 本机沙箱/受限终端请先设置 uv 缓存重定向（普通终端跳过）
#    PowerShell: $env:UV_CACHE_DIR="$PWD\.uv-cache"

# 1) 安装依赖（torch 为 cu126 GPU 构建）
uv sync

# 2) 配置密钥：复制 .env.example 为 .env，至少填 DASHSCOPE_API_KEY
copy .env.example .env

# 3) 启动 Milvus（先打开 Docker Desktop）
docker compose up -d milvus
#    健康检查：127.0.0.1:19530

# 4) （可选）启动精排服务（RERANK_BASE_URL 已指向 http://127.0.0.1:8303）
uv run uvicorn scripts.rerank_server:app --port 8303
#    不开也能跑：检索自动降级为「融合排序直出」，仅标记 degraded=rerank

# 5) 入库（把照片与 meta.csv 放入 data/raw/ 后执行；重复执行幂等）
uv run python -m app.cli ingest --src data/raw

# 6) 起 Web 展馆
uv run uvicorn app.web.main:app --port 8300
#    浏览器打开 http://127.0.0.1:8300
```

## 素材管线（版权红线自动化）

```bash
# 从 Wikimedia Commons 按分类爬取（自动过滤许可白名单 / 分辨率下限，
# 逐张落盘 meta.csv，429 自动退避重试，中断可续跑）
uv run python scripts/fetch_commons.py --category Historical_photographs_of_Guangzhou \
    --limit 20 --location 广州
# 可选 --proxy http://127.0.0.1:10809（urllib 不支持 socks5h，需 socks 时另想办法）
```

meta.csv 六列：`photo_id,title,year,location,source_url,license`。
**缺 license 或 source_url 的照片拒绝入库（版权红线，宁缺毋滥）**；爬下来的画作/超弱相关/近似重复件在人工审核时剔除（本仓库现状：51 张 → 24 张，落选件在 `data/raw/_rejected/`）。

## 评测（RAGAS）

```bash
# 判卷人用 qwen-max（bash）/ PowerShell: $env:LLM_MODEL='qwen-max'
LLM_MODEL=qwen-max uv run python -m app.cli eval
```

- 输入 `eval/questions.jsonl`（20 题：15 应答 + 5 拒答，均按真实语料 caption 重写）
- 输出 `eval/reports/YYYYMMDD-HHMMSS.json`，含 faithfulness / answer_relevancy / refused_accuracy / answer_rate / meets_threshold
- 验收线：faithfulness≥0.80 且 answer_relevancy≥0.75 且拒答准确率 100%
- 最近结果（2026-08-26，精排在线）：**0.888 / 0.858 / 1.0 / meets=true**
- 单轮波动 ±0.15 属正常；结论看逐行诊断 `scripts/diag_ragas_rows.py`
- 语料快照：`eval/corpus.jsonl`（pid/标题/年份/caption，`scripts/corpus_dump.py` 重新导出）

## 口播与数字人（W3）

```bash
# 简化版：讲解词 + 粤语 TTS 音频
uv run python -m app.cli narrate --pid gz_xxx
# 结果：data/processed/{pid}/narration.wav + script 文本

# 完整版：再加 SadTalker 口型视频（独立 venv-st，单张约 13 分钟）
uv run python scripts/make_talking_head.py --pid gz_xxx
# 结果：data/processed/{pid}/narration.mp4
```

可用音色（CosyVoice v2）：`longjiayi_v2` 知性女 / `longtao_v2` 积极女 / `longanyue` 男，Web 详情页可直接试听切换。

## 开发

```bash
uv run pytest -q            # 119 个单测（外部服务全 mock，无需任何服务在线）
# 工程约束 8 条见 AGENTS.md（版权红线/密钥治理/降级铁律/TDD/依赖方向…）
```

目录：`app/{cli,config,models}` · `app/ingest/` 入库管线 · `app/retrieval/` 检索 · `app/agents/` 三 Agent+口播 · `app/web/` 展馆 · `app/infra/` Milvus/嵌入/模型客户端 · `scripts/` 工具脚本 · `eval/` 评测 · `tests/` 单测

## 常见问题

- **HF 下载慢/失败**：默认走 hf-mirror；关键模型已本地化到 `models/hub-local/`
- **torch 是 CPU 版？** 不会。主 venv 已是 `torch==2.13.0+cu126`（RTX 4060，`torch.cuda.is_available()=True`）；嵌入/精排均 GPU
- **显存不足**：管线分阶段加载模型并阶段末释放；OOM 时关闭其他占用程序
- **Milvus 连不上**：Docker Desktop 是否在运行；`docker compose ps` 看容器
- **rerank 超时/降级**：全量语料候选多，先确认服务已起（`/health`）；客户端超时 15s
- **GBK 控制台**：脚本输出已做 `_safe_print` 防崩溃（部分脚本需 `[Console]::OutputEncoding=utf8` 看中文）

## 路线图

- W1 ✅ 入库管线（修复/上色/OCR/caption/双塔嵌入/Milvus，e2e 全通）
- W2 ✅ 混合检索 + 三 Agent + Web 展馆最小闭环
- W3 ✅ 粤语口播 + RAGAS 评测（meets）+ 24 张真实语料 + GPU 化
- W4 🚧 申报书 PDF + 演示视频 + 打磨打包