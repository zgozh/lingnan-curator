# spec.md —— 湾区记忆·岭南非遗 AI 策展人（lingnan-curator）

> 庆园杯 AI 创新应用大赛·主题三（开放创新探索）。单人参赛，工期约 1 个月。
> 提交物：申报书 PDF + 演示视频 + 可运行源码程序。

## 业务目标
把一批公开版权的岭南（广府）老照片，通过「修复上色 → OCR 数字化 → 多模态混合检索 → 三 Agent 生成」流水线，变成观众**可逛、可问、可听**的 Web AI 展馆，替代"静态图片展 + 人工撰写解说词"的低效方式。

## 背景
- **给谁用**：大赛评委与普通观众（展馆访客）；运营者即参赛者本人。
- **痛点**：老照片模糊难辨认；地方史料数字化成本高；静态展览缺乏互动、请不起讲解人力。
- **差异化武器**：①RAGAS 量化评测报告进答辩 PPT；②降级设计保证 RAG 主链路永远可用（本身就是工程亮点）。
- **技术基线**：复用本人 DocMind 项目已验证配方（FastAPI / LangGraph / Milvus / BGE-M3 / qwen3-rerank / uv）。

## 输入 / 输出
### 输入
- 原始老照片 jpg/png（首批 15~30 张，公有领域或开放许可）→ `data/raw/{photo_id}.{jpg,png}`
- 每张照片最小元数据（`data/raw/meta.csv`）：`photo_id,title,year,location,source_url,license`
- 观众操作：关键词搜索 / 自然语言提问 / 点选照片请求讲解与文创文案
### 输出
- 每张照片衍生资产 `data/processed/{photo_id}/`：`restored.jpg`（修复）、`colorized.jpg`（上色）、`ocr.txt`（招牌/题字）、`caption.json`（VLM 描述+标签）
- Milvus 中的多模态索引（文本 dense+sparse + CLIP 图像向量）
- Web 展馆：专题展览、照片墙、详情页（原图↔上色对比滑块）、导览问答（带配图引用、SSE 流式）、粤语口播视频播放、文创文案
- `eval/reports/`：RAGAS 四指标报告（JSON + Markdown，答辩用）

## 字段规格 / 功能规格
### 功能模块
| # | 模块 | 说明 |
|---|------|------|
| F1 | ingest 入库管线 | CLI 批处理：修复→上色→OCR→VLM 描述→向量化→Milvus 入库（先删后插幂等）；单张某步失败自动降级继续；产出批次处理报告 JSON |
| F2 | retrieval 混合检索 | BGE-M3(dense+sparse) 文本通道 + CLIP 图像通道；RRF 融合 → qwen3-rerank 精排 → norm_score 归一化 → 动态 top-k 断崖截断 |
| F3 | curator 策展人 Agent | 输入主题词 → 检索 → 输出展览编排 JSON（章节/选图/串场词），前端渲染成专题展 |
| F4 | docent 讲解员 Agent | 观众提问 → 强制带证据检索 → 回答+照片引用；无证据走拒答话术；SSE 流式 |
| F5 | creator 文创 Agent | photo_id + 文创类型（明信片/slogan/朋友圈文案）→ 结构化文案 JSON |
| F6 | narrator 口播预生成 | 讲解词 → 云端粤语 TTS 音频 → LivePortrait 生成口型视频 mp4；CLI 触发，产物挂详情页 |
| F7 | web 展馆 | FastAPI + Jinja2 服务端渲染 + 少量原生 JS（不上重型前端框架）；页面：首页/照片墙/详情(对比滑块)/问答/口播播放 |
| F8 | eval RAGAS 评测 | 固定评测集 ≥20 条问答（含 ≥3 条超范围拒答样本），输出 faithfulness / answer_relevancy / context_precision / context_recall |

### 核心数据对象 PhotoRecord
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| photo_id | string | 是 | 全局唯一，取自文件名 |
| title | string | 是 | 照片标题 |
| year / location | string | 否 | 年代 / 地点，可空 |
| source_url | string | 是 | 素材来源链接 |
| license | string | 是 | 许可证（公有领域/CC0/CC-BY 等）；缺失则拒绝入库 |
| ocr_text | string | 管线产物 | 可为空串 |
| caption / tags | string / list[str] | 管线产物 | VLM 生成，可为空 |
| vectors | object | 管线产物 | {text_dense, text_sparse, image_clip}，主键=photo_id |

## 边界案例
- 缺 license / source_url 的照片：**拒绝入库**并在批次报告列出
- 纯人像照 OCR 为空：`ocr_text=""`，检索退化到 title+caption+元数据
- VLM/DashScope 不可用：caption 降级为"标题+元数据拼接"，管线不中断
- rerank 服务不可用：跳过精排，RRF 排序直出，日志与响应标记 degraded
- CLIP 加载失败：图像通道关闭，纯文本检索兜底
- Milvus 未启动：健康检查失败给中文提示 + 启动命令，不允许挂死
- 重复导入同一 photo_id：先删后插，实体数不增
- 损坏图片 / 非图片文件：跳过并记录，不中断整批
- 超范围/敏感提问：统一拒答话术模板，不编造

## 非功能需求
- **性能**：问答首 token ≤ 8s；单张照片全管线 ≤ 3min；单条口播生成 ≤ 5min（RTX 4060 8GB，模型分步加载）
- **可靠性**：任何外部依赖故障不得使 RAG 主链路不可用（降级链见边界案例）
- **环境**：Windows 11 + Python 3.12 + uv；Docker Desktop 仅承载 Milvus（按需启动）
- **合规**：素材仅公有领域/开放许可并逐张登记来源；密钥走 `.env` 不入 git
- **编码**：全部 IO 显式 UTF-8

## Out-of-scope（明确不做）
- 实时流式数字人驱动（只做预生成视频）
- 移动端 / 小程序
- 用户注册登录、多租户、评论系统
- 自训练或微调任何模型
- 申报书 PDF 自动生成（人工撰写，AI 只供素材）
- 批量爬虫抓网（素材人工筛选，AI 只辅助整理候选清单）

## 真实验收场景（项目早期写死 3 个）
- **场景 1（数字化+检索）**：Given 首批素材中一张 1920~30 年代广州骑楼街景照已完成入库，When 在展馆搜索"骑楼"，Then 该照片排在前 3，且详情页可见原图↔上色对比滑块和 OCR 提取的招牌文字片段。
- **场景 2（讲解问答+防幻觉）**：Given 展馆问答页可用，When 问"西关大屋有什么特点？"且馆藏存在相关照片，Then 回答附至少 1 张馆藏配图，且结论能在所引照片的 caption/元数据中找到依据；When 问"2025 年广州地铁有多少条线路"，Then 系统明确答复超出馆藏范围，不编造。
- **场景 3（口播+评测差异化）**：Given 任一已入库照片，When 点击"生成粤语讲解"，Then 5 分钟内产出可播放的口播视频；并对评测集跑 RAGAS，faithfulness ≥ 0.80 且 answer_relevancy ≥ 0.75，报告落盘 `eval/reports/`。

判定：以上场景是 AI 反复修改后的事实标准，不接受用"测试通过"替代真实业务结果。

## 其他验收标准（Given/When/Then）
- Given 停掉 qwen3-rerank，When 正常提问，Then 仍返回结果且标记 degraded=true
- Given 同一批素材执行两次 ingest，When 查询 Milvus 实体统计，Then 数量不变
- Given 全新环境按 README 操作，When 一键启动，Then 展馆首页可访问（首次允许手动下载模型权重）

## 里程碑概览（细化留给实现计划）
- W1：环境 + F1 入库管线，3 张真实样张端到端跑通
- W2：F2 检索 + F3/F4/F5 三 Agent + F7 展馆最小闭环
- W3：F6 口播 + F8 RAGAS + 首批 15~30 张全量入库
- W4：打磨、申报书/演示视频素材、打包冒烟交付

## 阶段 2 待锁定的选型（ADR 承载，均先调研现成方案再定）
- 人脸修复：GFPGAN vs CodeFormer（本地实测老照片效果后二选一）
- 上色：DeOldify（artistic 权重）
- OCR：PaddleOCR（备选 RapidOCR）
- VLM 图片描述：DashScope qwen-vl 系列（复用 DocMind 账号）
- 向量库：Milvus standalone（docker compose）
- 粤语 TTS：火山引擎 vs Azure zh-HK（试听比价后定）
- 口型合成：LivePortrait（HF 权重，必要时走 hf-mirror）
