# 🧭 START-HERE —— 解压后按这个顺序看

> 你拿到的是「湾区记忆·岭南非遗 AI 策展人」的完整交付包：
> 把 26 张公有领域广州老照片（1840s~1940s）经 **AI 修复上色 → OCR → 多模态检索 → 三 Agent** 做成的 Web 展馆。
> 本文件按"零门槛 → 进阶 → 深度验证"三步带你走完全部看点。

---

## 第〇步：出发前的准备清单（按你要当的角色选一种）

### 🖼 角色 A｜只想看图听音频读文档（最省事，零安装）
- 任意电脑均可（Windows/macOS/翻看 HTML 用浏览器）
- 能解压 630MB 压缩包的磁盘空间约 **2 GB**
- 若要点开 meta.csv 里的 Wikimedia 链接溯源，需要能访问外网的浏览器
- **就这些，直接看下面"第一步"**

### ⚙️ 角色 B｜完整体验 Web 展馆（跑检索问答文创口播）
| 项目 | 要求 |
|---|---|
| 显卡 | **NVIDIA GPU 显存 ≥8GB**（RTX 3060 及以上级别） |
| 系统 | Windows 10/11 x64 |
| 磁盘 | 空闲 ≥ **40GB**（venv≈7GB + 模型权重≈10GB + 数据/Milvus 卷若干） |
| NVIDIA 驱动 | 更新到最新 Game Ready / Studio 版（CUDA 运行时由 torch cu126 自带，**无需装 CUDA Toolkit**） |
| uv 包管理器 | PowerShell 执行：`irm https://astral.sh/uv/install.ps1 \| iex`（Python 3.12 它会自动装） |
| Docker Desktop | docker.com 下载装好后启动一次（用于 Milvus 容器） |
| **DashScope API Key** | 自己到 阿里云百炼 bailian.aliyun.com 开通并创建——**发布包不含密钥，不能共用别人的**。开条目 billed 极低：本次开发全程 LLM+VLM+TTS 总花费约 ¥30 以内，单人测试预计 <¥5 |
| 网络 | HuggingFace 权重走国内镜像免代理自动下载（首次约 8~10GB，建议挂机一晚）；Wikimedia/Openverse 抓取直连可用 |

⚠️ 已知边界：本包为体积原因未携带本地视觉 vendor 环境（CodeFormer/DDColor 仓库与独立 venv）。入库时修复步骤会**优雅跳过并标记 degraded**，上色自动回退从 HF 镜像下载模型——馆照常建得起来，只是修复质量略逊于作者原机。

### 🧪 角色 C｜只验证代码质量（无 GPU 无密钥，5 分钟）
- 安装 uv（命令同上）、磁盘 5GB（拉 torch cu126 轮子）
- 然后：`uv sync` → `uv run pytest tests -q` 应输出 **245 passed**

## 📝 测试反馈怎么给

发现问题请附上三样：
1. 做了什么操作 / 访问了哪个页面；
2. 终端或浏览器报错截图；
3. `data/logs/` 下对应日志文件（上传/抓取产生的入库日志按 pid 命名）。

---

## 第一步：什么都不装，5 分钟看完核心成果

### ① 双击根目录的 `预览.html`
零环境离线展馆：26 张卡片点开即得「**修复↔上色对比滑块 + 粤语讲解播放器 + AI 叙事与文创链接**」，
照片墙→详情页的核心交互不装任何东西就能体验。
先看顶部 ⭐ 推荐的三张，各自代表一个技术故事：

| 照片 | 看点 |
|---|---|
| **1919年广东省运动会** | 修复→上色全链路的标杆样张，且带启用的增强上色版 |
| **广州沙面码头船居生活** | "唯一直用原版 DDColor 更自然"的案例——比稿评审机制保下的照片 |
| **谢扶雅与孙中山** | 人物肖像上色的分寸感（防脸变形是本项目红线） |

### ② 同一张照片的"前后对比"
用看图软件打开 `data/processed/gz_file1919jpg_006/`：
- `restored.jpg` = 洗去划痕褶皱后的灰度原片
- `colorized.jpg` = DDColor 自动上色
- `enhanced.jpg` = 启用的 AI 增强上色（质量更高）

两图并排看就是详情页滑块的原理。

### ③ 比稿评审机制的证据
打开同目录 `enhanced-archive/`：这里是所有落选候选图 + 每张自己的定制提示词 txt。
你能直观看到「AI 批量产出、人工审美一票决定」的设计——没有翻牌的候选永远不上线。

### ④ 听一段粤语讲解
播放器打开 `data/processed/gz_file1919jpg_006/narration.wav`，
对照 `narration.json` 里的讲解词文本。粤语 TTS（CosyVoice）产物。

### ⑤ 看文创产物
`postcard-front.png` / `postcard-back.png`（明信片正反面）、`slogan.png`（海报图）。
渲染逻辑见 `app/infra/artifact.py`。

### ⑥ 查账与查分
- 藏品总账：`data/raw/meta.csv`——每张图的标题/年代/地点/**原始出处链接/许可协议**，可溯源可审计
- RAGAS 评测报告：`eval/reports/*.json`——faithfulness **0.888** / answer_relevancy **0.858** / 拒答准确率 **1.0**

✅ 到这里你已看完项目 80% 的价值。想亲自玩交互，继续往下。

---

## 第二步：跑起来体验完整功能（需要 NVIDIA GPU ≥8GB + Docker + API Key）

```bash
uv sync                                  # 装 Python 3.12 依赖(torch cu126)
copy .env.example .env                   # 填 DASHSCOPE_API_KEY（DashScope 控制台申请）
docker compose up -d milvus              # 打开 Docker Desktop 后执行
uv run python -m app.cli ingest --src data/raw    # 入库建索引(首次约30分钟,GPU)
uv run uvicorn app.web.main:app --port 8300       # 开 http://127.0.0.1:8300
```

起来之后建议依次试：

| 页面 | 试什么 |
|---|---|
| `/` | 照片墙与缩略图（自动展示启用中的增强图） |
| `/search?q=骑楼` | 混合检索结果页 |
| 任一详情页 | 修复↔上色对比滑块拖动；换音色生成口播；生成明信片 |
| `/exhibit` | 输入或点击示例主题，看策展人 Agent 秒出三章节展览 |
| `/ask` | 点示例问题提问；故意问"2025 广州地铁几条线"看它拒答不编造 |
| `/upload` | 上传任意 jpg 并填许可协议，看后台管线入库到自动跳转 |
| `/crawl` | 抓取公版图（默认 Wikimedia Commons）→ 一键排队入库 |
| `/review` | 上色比稿评审台 |

> 说明：模型权重首次运行会从 hf-mirror 自动下载约 8GB；
> 精排服务(rerank)不开也能跑，仅标记 degraded。

## 第三步：只验代码质量（无 GPU 无密钥，2 分钟）

```bash
uv sync
uv run pytest tests -q        # 245 个测试全绿；外部服务全 mock
```

## 目录速查

```
预览.html                ← 你应该已经双击过了
START-HERE.md            ← 本文件
README.md                ← 完整文档(三种模式详解/FAQ)
data/raw/meta.csv        ← 26 张照片总账(来源+许可)
data/processed/<id>/     ← 每张照片的全部产物
eval/reports/            ← RAGAS 报告
docs/adr/                ← 12 条架构决策记录(含范围修订 ADR-0012)
docs/superpowers/specs/  ← 完整设计文档
app/                     ← 全部源码(FastAPI+LangGraph+Milvus)
tests/                   ← 245 个单测
```

## 版权说明

素材均为 Public Domain / CC0（逐张登记在 meta.csv，source_url 指向原始出处）。
管线任何环节拒绝接收缺 license 的图片——这是项目红线，不是 bug。

## 出问题看哪里

报错日志在 `data/logs/`；Milvus 连不上页面顶部有黄色引导条；
更多 FAQ 见 README.md 底部。
