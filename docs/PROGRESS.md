# PROGRESS —— lingnan-curator

## 当前阶段
**阶段 1（需求与 spec）**：设计稿已落盘，等待人工评审 → 门禁 1。通过后进入阶段 2（架构 + ADR，含市场调研候选清单）→ 门禁 2 → 拆任务。

## 已完成
- [2026-08-24] （上一会话）参赛方案拍板：「湾区记忆·岭南非遗 AI 策展人」；创建目录并 git init
- [2026-08-24] 三条技术路线补拍板：①老照片修复上色=本地开源（CodeFormer/GFPGAN + DeOldify）；②粤语口播=云端粤语 TTS + LivePortrait 本地口型；③素材=小批 15~30 张公开版权照片先打通再扩量
- [2026-08-24] 开工三件套落盘：`AGENTS.md`、`docs/PROGRESS.md`、spec 设计稿；补 `.gitignore` 与 `.env.example`

## 环境状态（2026-08-24 实测）
- GPU：RTX 4060 Laptop 8GB ✅（模型分步加载，避免同时驻留显存）
- 工具链：uv 0.11.28 + Python 3.12.4 ✅
- Docker Desktop：未运行 ⚠️（跑 Milvus 前需手动启动）
- DASHSCOPE_API_KEY：未注入系统环境变量 → 项目统一走 `.env`（沿用 DocMind 习惯）

## 待办
### 人（按优先级）
- [ ] **评审 spec**（`docs/superpowers/specs/2026-08-24-lingnan-curator-design.md`），确认后放行阶段 2
- [ ] 准备 DashScope API key（DocMind 账号可复用）、注册火山引擎或 Azure 取粤语 TTS key
- [ ] 收集首批 15~30 张公开版权岭南老照片 + 元数据（title/year/location/source_url/license），放入 `data/raw/`
- [ ] 用时启动 Docker Desktop（Milvus）
### AI
- [ ] 阶段 2：各选型点市场调研（现成方案候选清单）→ `architecture.md` + ADR-0001~N + 《人工准备清单》
- [ ] 阶段 3：writing-plans 拆任务（W1 先行：入库管线）

## 验证命令 / 冒烟记录
- 暂无代码，冒烟未开始。首次冒烟目标：W1 末——3 张真实样张端到端入库。
