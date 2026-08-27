# lingnan-curator · 湾区记忆·岭南非遗 AI 策展人

把公开版权（Public Domain / CC0 / CC BY / CC BY-SA）的岭南老照片，经「修复上色 → OCR → 多模态混合检索 → 三 Agent」，变成**可逛、可问、可听**的 Web 展馆。
（广州大学第二届「庆园杯」AI 创新应用大赛 · 主题三参赛项目，单人开发）

> 设计文档 `docs/superpowers/specs/2026-08-24-lingnan-curator-design.md` · 架构 `docs/architecture.md` · 决策记录 `docs/adr/`（范围修订见 ADR-0012）· 进度 `docs/PROGRESS.md`
>
> 👉 **测试者请从根目录 `START-HERE.md` 开始**——按顺序看完五个站点只需 5 分钟；零配置可视化画廊请双击根目录 **`预览.html`**。

## 核心亮点

- **真实语料 26 张**：Wikimedia Commons 公有领域广州历史老照片（1840s~1940s），meta.csv 六列著录齐全、均可溯源
- **RAGAS 评测进答辩**：faithfulness **0.888** / answer_relevancy **0.858** / 拒答准确率 **1.0**（qwen-max 判卷），报告落盘可复现
- **全 GPU 链路**：BGE-M3 + Chinese-CLIP 双塔嵌入、qwen3-rerank 精排均跑在本地 RTX 4060
- **三 Agent**：策展人（主题→展览）、讲解员（检索增强回答，防幻觉三道闸+SSE 流式）、文创（明信片/海报/伴手礼）
- **粤语口播**：CosyVoice 粤语三音色于详情页自选试听（数字人视频按用户决策裁撤，见 ADR-0012）
- **数据输入闭环**：Web 上传 + 多来源公版图批量抓取 + AI 上色比稿评审页，一条龙走完「进来→入库→人工审美翻牌→上线」
- **降级铁律**：rerank/CLIP/VLM/TTS 任一外部依赖失败，主链路照常可用（只标记 degraded）

## 准备环境（按角色自查）

| 你是谁 | 必备 | 得到的体验 |
|---|---|---|
| 🖼 只想浏览 | 浏览器 | 双击 `预览.html`：卡片墙→详情弹窗→滑块对比→粤语讲解播放器 |
| ⚙️ 完整部署 | NVIDIA GPU ≥8GB 显存 · Windows 10/11 · ≥40GB 磁盘 · 最新 N 卡驱动 · uv · Docker Desktop · 自备 DashScope API Key（bailian.aliyun.com，测试成本 <¥5） | 全部八页面交互：混合检索/AI 策展/问答防幻觉/上传/抓取/比稿评审/口播合成 |
| 🧪 仅验代码 | uv · 网络 | `uv sync` → `uv run pytest tests -q` = 245 passed |

> 没有 GPU 也能跑完整部署：修复步骤自动跳过（标记 degraded）、上色走 HF 镜像回退、嵌入 CPU 较慢——馆建得起来，质量打折。

## 功能一览（Web 展馆）

| 入口 | 说明 |
|---|---|
| `/` | 照片墙（馆藏总览） |
| `/search?q=…` | 多模态混合检索（文本/图像双通道 → RRF → rerank 精排） |
| `/photo/{id}` | 详情页：修复上色对比滑块、OCR 文本、粤语口播音色自选、文创按钮 |
| `/exhibit` | 专题展（策展人 Agent 生成主题章节+配图，附示例主题一键生成） |
| `/ask` | 问展馆：讲解员问答（SSE 流式渲染，超范围自动拒答并引导换问） |
| `/upload` | 上传新馆藏（版权红线校验 → 自动 pid → 后台管线 → 完成自动跳详情页） |
| `/crawl` | 批量抓取公版图（Commons 默认/Openverse 可切换 → 结果表 → 一键排队入库） |
| `/review` | AI 上色比稿评审：三方对比、逐张启用/撤下，旧版本永久保留在存档区 |

## 技术架构

```
data输入三通道(上传/抓取/手工) → meta.csv 六列著录 → ingest: 修复(CodeFormer)→上色(DDColor)→OCR(RapidOCR)
  →caption(qwen-vl-plus)→嵌入(BGE-M3 dense+sparse / CLIP)→ Milvus(lingnan_photos)
                                                        ↓
检索: WeightedRanker(0.8/0.2)+CLIP → RRF(k=60) → qwen3-rerank 精排 → 断崖截断
                                                        ↓
Web: 照片墙/搜索/详情/专题展/比稿评审 ← 三 Agent(docent/curator/creator) ← DashScope LLM
                                                        ↓
上色增强: tailor_prompt 定制色彩提示 → 云端重绘 → YCbCr 保脸合成 → /review 人工翻牌
                                                        ↓
口播: narrator(粤语讲解词) → CosyVoice TTS 音频(narration.wav)
```

模块依赖只能自上而下（`web/agents/narrator → retrieval → infra`），禁止反向。

## 三种测试模式（按你的环境挑一种）

### 模式 A · 只看成果（零配置，推荐给没装环境的测试者）

发布包内已包含全部图片与成果数据，无需安装任何东西即可直接浏览：

```
data/processed/<照片id>/
  restored.jpg        # 修复原图（去划痕去褶皱后的灰度）
  colorized.jpg       # DDColor 自动上色
  enhanced.jpg        # 经你翻牌启用的 AI 增强上色（仅部分照片有）
  enhanced-archive/   # 全部候选版本 + 定制提示词 txt（比稿存档）
  repaired.jpg        # CodeFormer 面部修复中间产物
  postcard-front.png / postcard-back.png   # 文创明信片正反面
  slogan.png          # 海报文案图
  story.json          # AI 叙事故事
  narration.wav       # 粤语口播音频
data/raw/meta.csv     # 26 张照片的完整著录（标题/年代/地点/来源链接/许可协议）
eval/reports/*.json   # RAGAS 评测报告全文
docs/superpowers/specs/design.md    # 完整设计文档
```

用任意看图软件逐文件夹浏览即可；每张图的原始出处与许可协议查 `meta.csv`。

### 模式 B · 完整体验（需要 NVIDIA GPU ≥8GB + Docker + DashScope API Key）

```bash
# 1) 安装依赖（torch 为 cu126 GPU 构建）
uv sync

# 2) 配置密钥：复制 .env.example 为 .env，至少填 DASHSCOPE_API_KEY
copy .env.example .env

# 3) 启动 Milvus（先打开 Docker Desktop）
docker compose up -d milvus        # 健康检查：127.0.0.1:19530

# 4) （可选）启动精排服务（不开则检索自动降级，仅标记 degraded）
uv run uvicorn scripts.rerank_server:app --port 8303

# 5) 入库（包内已带 data/raw 素材；重复执行幂等。首次约 30 分钟跑完全部 GPU 步骤）
uv run python -m app.cli ingest --src data/raw

# 6) 起 Web 展馆，浏览器打开 http://127.0.0.1:8300
uv run uvicorn app.web.main:app --port 8300
```

> 模型权重说明：BGE-M3/CLIP/rerank 首次运行自动从 hf-mirror 下载到本地缓存（约 8GB）；CodeFormer/DDColor 权重已随包放 `models/` 下（若缺失见常见问题）。无 GPU 的机器无法完成第 5 步的本地推理链路。

### 模式 C · 仅验证代码质量（无 GPU、无密钥也能跑）

```bash
uv sync
uv run pytest tests -q    # 245 个单测，外部服务全 mock，不需要任何在线服务
```

## 数据输入三通道（新增功能详解）

### ① Web 上传（导航栏「上传」）

填写标题 + **许可协议 + 来源链接**（版权红线必填，缺者拒绝入库）→ 提交后自动生成 `user_` 前缀 pid → 后台跑单张管线 → 页面轮询完成后跳转详情页。日志落 `data/logs/ingest-{pid}.log`。

### ② 批量抓取（导航栏「抓取」或 CLI）

```bash
# CLI 方式：默认 Wikimedia Commons；--source openverse 可切聚合图库
uv run python -m app.cli crawl --query "Canton Guangzhou 1930" \
    --limit 10 --location 广州 [--source commons|openverse]
```

- 许可不是 Public domain / CC0 的图**自动跳过**（红线内置于爬虫）；UA 已按 Wikimedia 机器人政策合规化，不会触发 403
- 抓到的图落 `data/raw/` 并追加 meta.csv，随后逐张或批量入库：

```bash
uv run python -m app.cli ingest --src data/raw --pid commons_xxx,commons_yyy
```

### ③ 手工放置

把图片放进 `data/raw/` 并在 meta.csv 追加一行六列著录后执行 ingest。

## 比稿评审流（AI 上色的正确打开方式）

`/review` 页面 = **机器批量产出候选 → 人眼审美一票决定权**：
1. CLI/Web 触发候选生成（定制提示词：按每张照片自己的著录生成专属色彩指导 → 云端重绘 → YCbCr 合成保证人脸结构数学保真）：
   ```bash
   uv run python -m app.cli tailor --all          # 或 --pid 单张；产物进 enhanced-archive/
   ```
2. 到 `/review` 逐张三方对比（原版 / 线上 / 候选），点「启用此版」即时生效，「撤下」随时回退
3. 所有历史版本与提示词永久保留在 `enhanced-archive/`，可追溯

## 评测（RAGAS）

```bash
LLM_MODEL=qwen-max uv run python -m app.cli eval   # PowerShell 写法: $env:LLM_MODEL='qwen-max'; uv run python -m app.cli eval
```

- 输入 `eval/questions.jsonl`（20 题：15 应答 + 5 拒答，均按真实语料 caption 重写）
- 输出 `eval/reports/YYYYMMDD-HHMMSS.json`
- 最近结果（2026-08-26，精排在线）：**0.888 / 0.858 / 1.0 / meets=true**
- 语料快照：`eval/corpus.jsonl`（pid/标题/年份/caption，`scripts/corpus_dump.py` 重新导出）

## 口播音频

```bash
uv run python -m app.cli narrate --pid gz_xxx      # 讲解词 + 粤语 TTS 音频
# 结果：data/processed/{pid}/narration.wav + narration.json（讲解词文本）
```

可用音色（CosyVoice v2）：`longjiayi_v2` 知性女 / `longtao_v2` 积极女 / `longanyue` 男，Web 详情页可直接试听切换。

## 开发

```bash
uv run pytest tests -q      # 245 个单测（外部服务全 mock，无需任何服务在线）
# 工程约束 8 条见 AGENTS.md（版权红线/密钥治理/降级铁律/TDD/依赖方向…）
```

目录速览：`app/cli.py` 统一命令入口 · `app/ingest/` 入库管线+爬虫适配器 · `app/retrieval/` 检索 · `app/agents/` 三 Agent · `app/narrator/` 口播 · `app/web/` 展馆 · `app/infra/` Milvus/嵌入/模型客户端 · `scripts/` 工具脚本 · `eval/` 评测 · `tests/` 单测

## 常见问题

- **HF 下载慢/失败**：默认走 hf-mirror；关键模型可本地化到 `models/hub-local/`
- **torch 是 CPU 版？** 不会。主 venv 已是 `torch==2.13.0+cu126`（RTX 4060 可用 `torch.cuda.is_available()` 自检）
- **显存不足**：管线分阶段加载模型并阶段末释放；上传通道的批量入库是单子进程顺序执行，避免多任务挤爆 GPU
- **Milvus 连不上**：Docker Desktop 是否在运行；`docker compose ps` 看容器；页面顶部会出现黄色警告条引导启动
- **rerank 超时/降级**：不启动精排服务也照常可用（degraded 标记）；客户端超时 15s
- **抓取报 403？** 项目内置合规 UA（Wikimedia 要求 UA 含项目描述+联系方式），若代理环境请确认 UA 头未被网关改写
- **GBK 控制台乱码**：PowerShell 先 `[Console]::OutputEncoding=utf8`
- **Milvus 里已有旧数据会重复吗**：ingest 幂等（先删后插同 photo_id），重复执行安全

## 路线图

- W1 ✅ 入库管线（修复/上色/OCR/caption/双塔嵌入/Milvus，e2e 全通）
- W2 ✅ 混合检索 + 三 Agent + Web 展馆最小闭环
- W3 ✅ 粤语口播 + RAGAS 评测（meets）+ 24 张真实语料 + GPU 化
- 近期 ✅ 数据输入闭环（上传/双来源抓取/比稿评审，ADR-0012）+ 缩略图与问答流式修复
- W4 ✅ 打包冒烟（zip+仓库双轨）· 离线展馆页 · START-HERE 导览 · 全馆藏口播补齐
- W4 🚧 申报书 PDF + 演示视频
