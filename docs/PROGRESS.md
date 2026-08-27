# PROGRESS —— lingnan-curator

## 当前阶段
**W3 完成（真实语料入库 + RAGAS 复认证 meets=true，全链路含精排在线）**：
- 语料 ✅：Commons 三分类爬取→人工审核剔除后 **24 张公有领域广州老照片**入库
  （meta.csv 六列齐全，license=PD/CC0/CC BY/CC BY-SA，source_url 可溯源）
- 复认证 ✅（20260826-013134.json，qwen-max 判卷+精排在线）：faithfulness **0.888**≥0.80、
  answer_relevancy **0.858**≥0.75、refused_accuracy **1.0**(5/5)；answer_rate 0.867
  （15 应答题中 2 题被过度拒答，W4 演示前用 diag 定位）
- 性能 ✅：主 venv torch 切 **cu126 GPU** 构建；rerank 服务改**批量单次前向**
  （24 候选 19s→1.0s）；检索精排全程在线不降级
- 下一步：**W4 = 申报书 PDF + 演示视频**（素材：本语料库 + eval/reports 数字进答辩 PPT）

## W4 执行记录（2026-08-26 叙事模型重构）
- **叙事链重构完成（ADR-0010）**：口播从"元数据拼讲解词"升级为 4-Agent 链——
  VLM 洞察→qwen-max 情感微故事→qwen-plus 粤语旁白→qwen-plus 一致性审稿，
  审稿 score<85 单点回炉（≤1 次）；`app/narrator/detox.py` 做确定性"AI 味"拦截硬闸
  （禁用词扫描 + 结构校验），不依赖 LLM。
- **TTS 按句合成 ✅**：旁白按句合成再拼接成正确 WAV（21386 节奏可控），CosyVoice 主路 +
  本地 Edge-TTS zh-HK 作可选 Provider（复用 ADR-0007 的 TTSProvider seam）。
- **叙事质量评测 ✅**：四维 judge（factual/taste/faithful/engaging）+ 禁用词统计；
  评测集按真实语料重写（15 应答 + 5 拒答）。
- **Web 详情页叙事展示 ✅（本任务）**：`photo_page` 调幂等的 `run_story_chain(photo_id)`，
  透传 `story` / `narration_lines` / `chain_degraded` / `chain_audio`；`detail.html` 渲染
  "故事 / 旁白" 区块（故事段落 + 逐句旁白 `<li data-emotion>`）；音频复用既有
  `id="narration-audio"` 节点。`tests/test_web.py` mock `run_story_chain` 防触发在线链。

## 指标爬坡记录（同代码下的关键修复）
| 版本动作 | faithfulness | answer_relevancy |
|---|---|---|
| 初版（contexts 空） | 0.00 | 0.24 |
| contexts 回填 caption | 0.12 | 0.26 |
| +著录元数据(year/location) | 0.71→0.78 | 0.42~0.61 |
| 判卷人 qwen-max | 0.54 | 0.61 |
| VLM 结构化 caption 增强 | 0.67 | 0.56 |
| 讲解词去元话语+丰满化+**误拒隔离出 RAGAS 样本池** | **0.92** | **0.86** |
| 真实语料 24 张复认证（精排在线） | 0.888 | 0.858 |

教训：聚合分暴跌先查**喂给判卷人的样本质量**（误拒话术污染样本池），再谈调参；
单轮波动大（±0.15），结论必须配合逐行诊断（scripts/diag_ragas_rows.py）。

## W3 执行记录（2026-08-24）
- T1 ✅ d9127c6 app/infra/tts.py：DashScopeCosyvoice + _new_synthesizer seam；配置 tts_provider/tts_voice/rerank_base_url；.env.example 同步
- T2 ✅ 05c5fd5 实测可用组合=cosyvoice-v2 × {longjiayi_v2 知性女, longtao_v2 积极女, longanyue 男}；v3 系音色需开通权限（418/AccessDenied）
- T3 ✅ 9d0c037 agents/narrator.py write_script(粤语白话讲解词 json_mode)+narrate(音频降级标记)；cli narrate --pid 真实跑通 sample_a；详情页 <audio> 入口
- T5 🔶 b75f0a4 cli eval 子命令（refused_accuracy+RAGAS 双指标+阈值判定+报告落盘 eval/reports/）+eval/questions.jsonl 20条(含5拒答)；ragas0.3.1×新langchain-community 的 vertexai 缺模块用 sys.modules shim 解决；DashScope embeddings 必须 check_embedding_ctx_length=False（否则发 token 数组报400）；评分取数兼容 EvaluationDataset.scores 均值聚合
- T4 环境就绪 scripts/setup_sadtalker.ps1（py3.10 venv-st）：坑位记录——uv venv 无 setuptools→pkg_resources 缺失(face_alignment/librosa 需要)；setuptools≥81 彻底移除 pkg_resources 须钉 75.8.0；numba 必须钉 0.57.1 兼容 numpy1.23；basicsr1.4.2 无 wheel 且 uv 构建 temp 被拒→从 .uv-cache/sdists 解包 build/lib 直拷 site-packages；functional_tensor 补丁必须用「from ... import」语句级精确匹配（宽匹配会误伤 torch 内部文件）；ps1 含中文必须 UTF-8 BOM 否则 PS5.1 GBK 解析炸引号
- T6 🔶 hf-mirror TLS 被掐（Invalid username/password 假象+连接重置），改 ModelScope Qwen/Qwen3-Reranker-0.6B 源 scripts/fetch_reranker_ms.py；服务端 scripts/rerank_server.py 已写（yes/no softmax 打分）

## W3 收尾执行记录（2026-08-26）
- **网络恢复**：直连全通（baidu/commons/upload CDN 均 OK）；v2rayN http:10809 未监听、socks:10808 可用但 urllib 不支持 socks5h → 爬虫走直连
- **爬取器三连修**（TDD，各带回归测试）：①9656491 追加 meta.csv 对齐现有表头列序（原会 license/source_url 写串列）；②e3fb0b8 429/5xx 指数退避重试+逐张落盘 meta（崩溃可凭 photo_id 幂等续跑）+礼貌间隔+合规 UA；③e649f53 单张 api 异常跳过续跑+_safe_print 防 GBK 控制台崩溃（「française」的 ç 实测炸过）
- **语料采集**：Historical_images_of_Guangzhou(30) + Historical_photographs_of_Guangzhou(18) + Historical_images_of_Shamian(3)，共 51 张落地
- **人工审核剔除 27 张**（无视觉输入，按元数据证据审）：非照片类 21（摄影术 1839 年实用化→1662/1749/1785/1800/1807/1836/1842/1843 年份者必为画作；标题明示 Drawings/oil on canvas/书版画；Conseequa 铜版画；Anson 环球航行记插图——caption 读图后补抓的漏网鱼）、弱相关/疑似异地 4（袋鼠化装照/HK 开头/江西九江相册页等）、近似重复 2（Grant Hall 三张留一张）。落选件存 `data/raw/_rejected/`（含审核前 meta 备份）
- **入库 ✅**：24 张全链路成功（restore→colorize→OCR→qwen-vl caption→BGE-M3+CLIP→Milvus），0 FAILED；10 个 OCR 空=DEGRADED 属纯画面照正常降级。报告 data/processed/_report.json
- **评测集重写**：eval/questions.jsonl 全部按新语料 caption 重写 grounded 问题（15 应答+5 拒答）；scripts/corpus_dump.py 新工具（Milvus 语料检视/导出/purge）
- **评测两轮**：①精排超时降级下 faithfulness 0.951/relevancy 0.831（报告 20260826-005050）；②修复后精排在线 0.888/0.858 + refused_accuracy 1.0（报告 20260826-013134，**以此为准**）
- **精排性能修复**：1951591 服务端批量单次前向（padding 对齐，24 候选 19s→1.0s）+客户端超时 15s；32d9a7c 主 venv torch 切 cu126 GPU 构建（cu121 最高只到 torch2.5；2.13 的 win 轮子在 cu126），嵌入/精排上 GPU，RTX 4060 实测 CUDA 可用
- SadTalker 13min/张提速：**挂起**（低优；W4 演示只需预生成少量视频，动 fp16/降采样有质量风险，待用户拍板）

## W2 执行记录（2026-08-24）
- T1 ✅ 644735e 检索基元：文本通道 WeightedRanker(0.8,0.2) + CLIP 通道 → RRF(k=60) 融合 → 归一化；CLIP 失败降级纯文本
- T2 ✅ 6f913bf rerank 客户端四态降级（成功/超时/500/未配置→None）
- T3 ✅ e4fd5d4+5247712 检索门面：精排接入 + 断崖截断（<peak×0.35 或 >12 条截断）
- T4 ✅ e9400b4 LLM 文本客户端 chat/stream_chat/json_mode；extract_json 上移 app/utils/json_utils
- T5 ✅ 77d24dd 讲解员 Agent：防幻觉三道闸（空检索拒答/提示词约束/事后校验引用）+ SSE 流式
- T6 ✅ d2a12bf 策展人（主题→展览 JSON，过滤池外 id）+ 文创（三类型，400/404 语义）
- T7 ✅ 838085d Web 展馆：照片墙/详情对比滑块/搜索/问答 SSE/专题展 + Milvus 未连中文横幅
- T8 ✅ b177506 真实冒烟 SMOKE PASS：pymilvus SearchResult[HybridHits] 容器摊平修复后，
  /search 骑楼命中 sample_a、/photo 详情含 OCR、超范围 ask refused=true；脚本 scripts/smoke_web.py

### W2 备注
- Agent 编排暂用轻量函数+seam（未上 LangGraph 图结构）：当前流程为线性两步，YAGNI；W3 若引入多步条件路由再评估迁移
- qwen3-rerank 服务本体 W3 部署；当前 RERANK_BASE_URL 空 → 全链路走 degraded={'rerank'} 直通路径，验收标准「停精排仍可用」已由测试覆盖
- 中文 Windows 控制台打印 emoji 会 UnicodeEncodeError，脚本输出用 [OK]/[NG]

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
- [2026-08-24] Task10 ✅ **e2e 冒烟全通**：OK=14/DEGRADED=1/FAILED=0，Milvus(v2.4.15) 落库 3/3；caption=qwen-vl 真模型；修复链：HF symlink 特权→本地模型目录、xet 禁用、CLIP 正确 id=patch16、transformers5.x pooler_output 解包、texts 批形状解包、幂等 ensure_collection、sparse 缺失对齐（提交至 eed1d12）

### T10 嵌入模型本地化（重要，后续会话必读）
- **不要让 transformers 走 HF 缓存**：Windows 符号链接需特权(WinError 1314)+沙箱拒建链 → 两塔模型已预下到 `models/hub-local/{bge-m3,chinese-clip}`（snapshot_download local_dir 纯复制 + HF_HUB_DISABLE_XET=1），`.env` 以 BGE_M3_MODEL_PATH/CLIP_MODEL_PATH 指向本地目录
- **Chinese-CLIP 正确 repo id 是 `OFA-Sys/chinese-clip-vit-base-patch16`**（不是 p16）；config.py 默认已改
- **transformers 5.x 坑**：ChineseCLIPModel.get_image_features 返回 vision ModelOutput，投影嵌入在 `.pooler_output`（embedder 已防御解包 image_embeds→pooler_output→tensor）
- Milvus 镜像用本机已有 v2.4.15（compose 已改）；容器偶发重启窗口会导致瞬时连接失败，重试即可

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
### W4（申报书 PDF + 演示视频）
- [ ] 申报书：技术方案/架构图/创新点（RAGAS 评测数字进 PPT）/演示截图
- [ ] 演示视频脚本+录制：照片墙→搜索→问答 SSE→专题展→详情页音色自选→口播视频
- [ ] 演示前用 diag_ragas_rows 定位 15 应答题中 2 例过度拒答并微调闸门
- [ ] 真实语料挑 3~5 张预生成口播（narrate→TTS→SadTalker；13min/张，安排过夜跑）
- [ ] （可选）SadTalker 提速实验：降采样底图 / fp16，先小样验证质量再全量
- [ ] smoke_web.py 断言仍耦合 sample_a/骑楼（已从语料剔除），改为动态取库内任一 pid
### 人（按优先级）
- [ ] W4 启动会话里确认申报书模板/大赛格式要求、视频时长上限
- [ ] 试听三音色定稿默认 voice（详情页已支持自选，不阻塞）

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
- ADR-0010 叙事生成 = 4-Agent 链 + 确定性去AI味拦截 + 云端 API（本文档对应执行记录）

## 验证命令 / 冒烟记录
- 暂无代码，冒烟未开始。首次冒烟目标：W1 末——3 张真实样张端到端入库。

## 近期单元执行记录（231-240 测试基线）
- E2 保脸上色链：YCbCr 亮度保结构合成（LRU: Y=本地/色度=云端），description_edit 永久禁用
- ADR-0011 增补：上色增强候选只落 enhanced-archive 待审区，人工 /review 启用才上线
- 比稿评审流：tailor_prompt 定制色彩提示 + /review 三列比稿页（启用=移动转正/撤下=归档回退）
- 提示词 v2：场景分类（室内禁天空水面词+暖色骨架+冷蓝绿禁忌+信息不足兜底），棺材铺内景饱和度 14.5%→45.5%
- 修复：首页/检索缩略图模板变量错位（占位图假死）、docent 流式吐 JSON 改纯文本契约、专题展示例主题 chips
- 数据输入 A：Web 上传通道 /upload（license/source_url 版权红线必填校验+PIL 真伪嗅探+20MB 上限+自动 pid 去重）→ ingest --pid 单张后台管线 → store-status 轮询跳详情
- 数据输入 B：Commons 公版图爬虫 app/ingest/commons_crawler.py（仅 PD/CC0 白名单过滤、合规 UA 过机器人政策 403、单条失败降级）；CLI crawl --query --limit --location；实测抓通 Canton 1910 两张
- 数据输入升级：多来源抓取适配器 sources.py(commons/openverse)+Web 批量抓取页 /crawl(任务轮询+一键入库批次)+ingest --pid 逗号批量；问展馆前端完善(示例问题/拒答引导样式/引用说明)；全链路实测抓取2张并排队入库(e647a20)
