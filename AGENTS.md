# AGENTS.md —— lingnan-curator（湾区记忆·岭南非遗 AI 策展人）

## 定位
庆园杯 AI 创新应用大赛·主题三参赛项目：把公开版权岭南老照片经「修复上色→OCR→多模态混合检索→三 Agent」变成可逛/可问/可听的 Web 展馆。单人开发、约 1 个月工期。设计事实标准见 `docs/superpowers/specs/2026-08-24-lingnan-curator-design.md`。

## 目录约定（随实现逐步建立）
```
app/            # 主包：cli / ingest(入库管线) / retrieval(检索) / agents(三Agent) / narrator(口播) / web(展馆)
config/         # dataclass 全局配置，读 .env
data/raw        # 人工放入的原始照片（gitignore）
data/processed  # 管线衍生资产（gitignore）
docs/superpowers/{specs,plans}/   # 设计稿与实现计划
docs/adr/       # 架构决策记录（编号递增）
eval/           # RAGAS 评测集与报告
tests/          # 单测（mock 外部服务）+ e2e（单独标记）
```

## 常用命令
```bash
uv sync                                        # 安装依赖
docker compose up -d milvus                    # 启动 Milvus（需先开 Docker Desktop）
python -m app.cli ingest --src data/raw        # 入库管线
uvicorn app.web.main:app --port 8300 --reload  # 展馆服务
pytest -q                                      # 测试（e2e 另行标记）
python -m app.cli eval                         # RAGAS 评测
```

## 硬约束（review 必查）
1. **版权红线**：缺 `license` 或 `source_url` 的照片禁止入库，宁缺毋滥。
2. **密钥治理**：密钥只进 `.env`（不入 git）；新增配置必须同步更新 `.env.example`。
3. **编码**：所有文件读写显式 UTF-8（本项目大量中文）。
4. **降级铁律**：外部依赖失败不得打垮 RAG 主链路——rerank 挂→跳过精排；CLIP 挂→纯文本通道；VLM 挂→标题+元数据拼接；TTS/LivePortrait 挂→隐藏口播入口。
5. **TDD**：新功能先写失败测试再看实现；单测一律 mock 外部服务，真实链路只留一条 e2e。
6. **依赖方向**：web/agents/narrator → retrieval → 基础设施（Milvus/嵌入/模型客户端）；禁止反向 import。
7. **YAGNI**：Out-of-scope 清单（spec 内）里的东西不做；未经拍板不引入新框架。
8. **留痕**：完成一块工作就更新 `docs/PROGRESS.md`；技术决策落 ADR，不留在聊天里。

> 本文件是短版手册；详细规格以 spec 与 ADR 为准，冲突时 spec/ADR 优先。
