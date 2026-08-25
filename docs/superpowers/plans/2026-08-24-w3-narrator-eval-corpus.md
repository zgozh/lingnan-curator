# W3 实现计划 —— F6 口播 + F8 RAGAS + 全量素材 + rerank 服务

对应 spec F6/F8 与验收场景 3；依赖事实：DashScope CosyVoice 有 4 个粤语发音人
（longjiaxin_v3/longjiayi_v3/longanyue_v3/longtao_v2），主选成立、Azure 仅兜底。

## 任务分解

### T1 TTS 基座 `app/infra/tts.py`
- `TTSProvider` 协议 + `DashScopeCosyvoice` 实现（dashscope SDK tts_v2）
- `synthesize(text, voice, out_wav)`；失败返回 False（降级铁律：无音频→详情页隐藏口播入口）
- 配置新增 `TTS_PROVIDER/TTS_VOICE` → 同步 `.env.example`（硬约束2）
- 测试：mock SDK 四态（成功/空文本/异常/未配 key）

### T2 粤语听测 spike（真实调用用户 key）
- sample_a 讲解词 → longjiaxin_v3 / longanyue_v3 各合成一段
- 产物 `data/processed/sample_a/tts-*.wav`；**用户试听定音色**（人工项）

### T3 讲解词生成 + narrate CLI 打通
- `app/agents/narrator.py`：photo_id → 馆藏著录 → LLM 生成 ≤200 字粤语白话讲解词（json_mode）
- `app/cli.py narrate --pid X`：讲解词 → TTS 音频 → （T4 就绪后）口播视频；产物登记进 processed 目录
- 详情页挂 `<audio>` 播放入口（无产物时隐藏）
- 测试：mock llm/tts/milvus

### T4 SadTalker vendor spike（风险最高，最早启动后台）
- clone 固定 commit + 独立 venv(cu121) + 权重下载（断点续传脚本复用）
- **前置：ffmpeg 未安装**（已探测缺失）→ 用户执行 `winget install Gyan.FFmpeg` 或授权我装
- 照片+narration.wav → mp4 冒烟一张；任何失败→口播功能整体隐藏（spec 降级）
- COMMITS.md 登记 pinned commit

### T5 RAGAS 评测 F8
- `uv add ragas datasets langchain-openai`（冲突则隔离 venv，风险表预案）
- 评测集 `eval/questions.jsonl` ≥20 条：基于现有馆藏著录的问答 + ≥3 条超范围拒答样本
- `app/cli.py eval`：批量调 /api/ask → RAGAS(faithfulness/answer_relevancy/context_precision/context_recall)
- 报告落盘 `eval/reports/*.json`；达标线 faithfulness≥0.80、answer_relevancy≥0.75
- 注：拒答样本不计 answer_relevancy 扣分，单列 refused_accuracy 指标

### T6 rerank 服务部署
- `scripts/rerank_server.py`：FastAPI `/rerank`+`/health`，加载 BAAI/Qwen3-Reranker-0.6B
  （hf-mirror 下载 ~1.2GB 到 models/hub-local/，HF_HUB_DISABLE_XET=1）
- `.env` 填 `RERANK_BASE_URL=http://127.0.0.1:8302` → 全链路精排生效
- 冒烟：rerank 后 /search 排序变化且 degraded 清空

### T7 全量素材入库流水线
- **人工项**：首批 15~30 张公开版权照片 + meta.csv 六列补全（AI 可先出 Wikimedia 候选清单）
- 分批 ingest + 报告审查；检索质量抽查（场景1 在真实池中仍前3）

### T8 W3 e2e 冒烟收官
- 场景3：narrate 任一照片 ≤5min 产出可播放 mp4；RAGAS 报告落盘且指标达标
- PROGRESS 更新 + 收官提交

## 人工准备清单（本轮需要你做的）
| # | 事项 | 说明 |
|---|------|------|
| 1 | 安装 ffmpeg | `winget install Gyan.FFmpeg`（或授权我用命令行装） |
| 2 | TTS 听选定音色 | T2 产出两段粤语音频后你试听拍板 |
| 3 | 收集首批素材 | 15~30 张公有领域岭南老照片；我可先出候选清单 |
