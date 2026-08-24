# lingnan-curator · 湾区记忆·岭南非遗 AI 策展人

把公开版权的岭南老照片，经「修复上色 → OCR → 多模态检索 → 三 Agent」变成可逛、可问、可听的 Web 展馆。
（庆园杯 AI 创新应用大赛·主题三参赛项目）

设计文档：`docs/superpowers/specs/2026-08-24-lingnan-curator-design.md` · 架构：`docs/architecture.md` · 决策：`docs/adr/`

## 前置条件
- Windows + NVIDIA GPU（≥8GB 显存，开发机为 RTX 4060 Laptop）
- [uv](https://docs.astral.sh/uv/)、[Docker Desktop](https://www.docker.com/products/docker-desktop/)（仅用于 Milvus）
- ffmpeg（W3 口播功能需要）

## 快速开始

```bash
# 0) 本机沙箱/受限环境注意：uv 缓存重定向（普通终端可跳过）
#    PowerShell: $env:UV_CACHE_DIR="$PWD\.uv-cache"

# 1) 安装依赖
uv sync

# 2) 配置密钥：复制 .env.example 为 .env 并至少填 DASHSCOPE_API_KEY
copy .env.example .env

# 3) 启动 Milvus（需先打开 Docker Desktop）
docker compose up -d milvus

# 4) 放素材：照片丢进 data/raw/，并在 data/raw/meta.csv 补一行：
#    photo_id,title,year,location,source_url,license
#    ⚠️ license / source_url 为空的照片会被拒绝入库（版权红线）

# 5) 入库（首次运行自动经 hf-mirror 下载模型权重，约数 GB）
uv run python -m app.cli ingest --src data/raw
```

## 常见问题
- **HF 下载慢/失败**：项目已默认 `HF_ENDPOINT=https://hf-mirror.com`（vision_ops 子进程内）。
- **显存不足**：管线分阶段加载模型并在阶段末释放；若仍 OOM，关闭其他占用显存的程序。
- **Milvus 连不上**：确认 Docker Desktop 在运行且 `docker compose up -d milvus` 执行过；健康端口 `127.0.0.1:19530`。
- **torch 是 CPU 版**：当前主环境为 CPU torch（开发环）。GPU 推理在 vendor venv（venv-cf/venv-dd，cu121）。如需主环境切 cu121 见 `docs/PROGRESS.md`「沙箱环境适配」。

## 开发
```bash
uv run pytest -q          # 全量单测（外部服务全 mock）
uv run pytest -m e2e      # 真实链路集成测试
uv run python scripts/spike_vendors.py sample_b   # vendor 修复/上色单张实测
```
工程约束见 `AGENTS.md`（8 条硬约束）；进度与冒烟记录见 `docs/PROGRESS.md`。

## 路线图
- W1 ✅ 入库管线（本仓库当前阶段）
- W2 混合检索 + 三 Agent + Web 展馆最小闭环
- W3 粤语口播预生成 + RAGAS 评测 + 素材扩充
- W4 打磨、申报书/演示视频、打包交付
