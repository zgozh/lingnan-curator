# W1 入库管线（F1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通 F1 入库管线——3 张真实样张从 `data/raw` 进，经修复→上色→OCR→VLM 描述→向量化→Milvus 出索引，批次报告落盘。

**Architecture:** CLI 批处理编排 `app/ingest/pipeline.py`，各步骤为独立 op 函数；重型视觉模型 vendor 子进程隔离（ADR-0002/0008），LLM/VLM 走 DashScope 客户端（ADR-0004），向量写入 Milvus 先删后插幂等（ADR-0005）。任何一步失败按 spec 边界案例降级继续，不中断整批。

**Tech Stack:** Python 3.12 + uv / pymilvus(MilvusClient) / FlagEmbedding BGE-M3 / Chinese-CLIP ViT-B/16 / RapidOCR(onnxruntime) / openai sdk(DashScope 兼容端点) / pytest。vendor：CodeFormer、DDColor（独立 venv 子进程）。

**Spec:** `docs/superpowers/specs/2026-08-24-lingnan-curator-design.md`（F1 模块、PhotoRecord、边界案例）；架构见 `docs/architecture.md` + ADR-0001~0009。

## Global Constraints
- 版权红线：缺 `license` 或 `source_url` 的照片禁止入库，宁缺毋滥。
- 密钥只进 `.env`（不入 git）；新增配置必须同步 `.env.example`。
- 所有文件读写显式 UTF-8。
- 降级铁律：rerank 挂→跳过精排；图像通道挂→纯文本；VLM 挂→标题+元数据拼接；上色挂→只交修复图；单张失败跳过不中断整批。
- TDD：先写失败测试看它失败再实现；单测一律 mock 外部服务（LLM/Milvus/嵌入模型/vendor 子进程）；真实链路只留 Task 10 一条 e2e。
- 依赖方向：ingest → infra → config；禁止反向 import。
- 性能预算：单张全管线 ≤ 3min（RTX 4060 8GB，模型分步加载用完释放）。
- 提交纪律：每任务至少一个 commit；提交信息 `feat:/test:/chore: 前缀`。

---

## File Structure（本计划锁定）

```
pyproject.toml                  # uv 工程与依赖钉版
docker-compose.yml              # milvus standalone 单容器
app/__init__.py  app/config.py  app/models.py  app/cli.py
app/infra/{__init__,milvus_store,embedder,llm_client}.py
app/ingest/{__init__,meta,vision_ops,ocr_op,caption_op,vectorize_op,store_op,pipeline}.py
scripts/setup_vendors.ps1       # vendor 环境一键搭建（Task 7 产出）
models/vendor/COMMITS.md        # vendor 仓库 pinned commit 记录
tests/test_config.py tests/test_meta.py tests/test_caption_op.py
tests/test_milvus_store.py tests/test_embedder.py tests/test_vision_ops.py
tests/test_pipeline.py
tests/e2e/test_ingest_e2e.py    # 唯一真实链路测试(e2e 标记)
data/raw/meta.csv               # 人工素材清单(样例3行)
```

---

### Task 1: 工程骨架 + 配置加载 + 数据模型

**Files:**
- Create: `pyproject.toml`, `app/__init__.py`, `app/config.py`, `app/models.py`, `.gitignore`(已有), `tests/test_config.py`
- Modify: `.env.example`（追加 `BGE_M3_MODEL_PATH`、`CLIP_MODEL_PATH`）

**Interfaces:**
- Produces: `app.config.Settings`（dataclass 字段见下）、`get_settings() -> Settings`（lru_cache 单例）；`app.models.PhotoRecord`、`StepStatus(IntEnum: OK=1,DEGRADED=2,FAILED=3)`、`StepResult(step:str,status:StepStatus,detail:str)`、`IngestReport(items:list[StepResult], started_at:str, finished_at:str)`、`IngestReport.to_json() -> str`

- [ ] **Step 1: 初始化工程**

```bash
uv init --python 3.12 --no-readme .
uv add pymilvus "flagembedding" rapidocr-onnxruntime openai pillow python-dotenv pytest
```
注：FlagEmbedding 包名以 `uv add FlagEmbedding` 实际为准；若解析冲突改 `uv pip install` 后锁回 pyproject。`pyproject.toml` 确认含：

```toml
[project]
requires-python = ">=3.12"
dependencies = ["pymilvus>=2.4", "rapidocr-onnxruntime>=1.3", "openai>=1.40", "pillow>=10", "python-dotenv>=1.0"]
[dependency-groups]
dev = ["pytest>=8"]
[tool.pytest.ini_options]
markers = ["e2e: 真实链路集成测试"]
```

- [ ] **Step 2: 写失败测试** `tests/test_config.py`

```python
from pathlib import Path
def test_settings_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MILVUS_URI", "http://127.0.0.1:19530")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    from app.config import Settings
    s = Settings.load(env_file=None)
    assert s.milvuri == "http://127.0.0.1:19530"
    assert s.collection == "lingnan_photos"
    assert s.dashscope_api_key == "sk-test"
```

- [ ] **Step 3: 运行确认失败** — Run: `uv run pytest tests/test_config.py -v`，Expected: FAIL (`ModuleNotFoundError: app`)
- [ ] **Step 4: 最小实现** `app/config.py`

```python
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

@dataclass(frozen=True)
class Settings:
    milvuri: str = "http://127.0.0.1:19530"
    collection: str = "lingnan_photos"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"
    vlm_model: str = "qwen-vl-plus"
    bge_m3_model_path: str = "BAAI/bge-m3"
    clip_model_path: str = "OFA-Sys/chinese-clip-vit-base-p16"

    @staticmethod
    def load(env_file: str | None = ".env") -> "Settings":
        if env_file and Path(env_file).exists():
            load_dotenv(env_file, encoding="utf-8")
        return Settings(
            milvuri=os.getenv("MILVUS_URI", Settings.milvuri),
            collection=os.getenv("MILVUS_COLLECTION", Settings.collection),
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            bge_m3_model_path=os.getenv("BGE_M3_MODEL_PATH", Settings.bge_m3_model_path),
            clip_model_path=os.getenv("CLIP_MODEL_PATH", Settings.clip_model_path),
        )
```
（顶部补 `from pathlib import Path`；`app/models.py` 按 Interfaces 定义四个 dataclass/IntEnum，`to_json()` 用 `json.dumps(dataclasses.asdict(self), ensure_ascii=False)`。）
- [ ] **Step 5: 跑绿并提交** — `uv run pytest tests/test_config.py -v` PASS 后：
```bash
git add -A && git commit -m "chore: 工程骨架+配置加载+数据模型"
```

---

### Task 2: Milvus compose 与存储层（先删后插幂等）

**Files:**
- Create: `docker-compose.yml`, `app/infra/__init__.py`, `app/infra/milvus_store.py`, `tests/test_milvus_store.py`

**Interfaces:**
- Consumes: `Settings.milvuri/.collection`
- Produces: `ensure_collection(client) -> None`；`upsert_photo(client, record: PhotoRecord, dense: list[float], sparse: dict[int,float], clip: list[float]) -> None`（内部先 `delete(pks=[photo_id])` 再 insert）；`count_photos(client) -> int`；`build_schema()`（pymilvus schema：photo_id VARCHAR pk64 / title,year,location,caption,ocr_text VARCHAR / has_colorized BOOL / emb_dense FLOAT_VECTOR dim1024 / emb_sparse SPARSE_FLOAT_VECTOR / emb_clip FLOAT_VECTOR dim512；索引 dense=HNSW COSINE、sparse=SPARSE_INVERTED_INDEX IP、clip=IVF_SQ8 COSINE）

- [ ] **Step 1:** 写 `docker-compose.yml`（milvus standalone 单容器模式）：

```yaml
services:
  milvus:
    image: milvusdb/milvus:v2.4.17
    command: ["milvus", "run", "standalone"]
    environment: {ETCD_USE_EMBED: "true", COMMON_STORAGETYPE: "local"}
    ports: ["19530:19530", "9091:9091"]
    volumes: ["milvus_data:/var/lib/milvus"]
volumes: {milvus_data: {}}
```
- [ ] **Step 2: 失败测试**（mock MilvusClient，验证幂等=先 delete 再 insert）：

```python
from unittest.mock import MagicMock
from app.infra.milvus_store import upsert_photo
from app.models import PhotoRecord
def test_upsert_deletes_before_insert():
    client, rec = MagicMock(), PhotoRecord(photo_id="a", title="t", source_url="u", license="PD")
    upsert_photo(client, rec, dense=[0.0]*1024, sparse={3: 0.5}, clip=[0.0]*512)
    client.delete.assert_called_once_with(collection_name="lingnan_photos", pks=["a"])
    assert client.insert.call_count == 1
def test_sparse_keys_cast_to_int():
    client = MagicMock(); rec = PhotoRecord(photo_id="b", title="t", source_url="u", license="PD")
    upsert_photo(client, rec, dense=[0.0]*1024, sparse={"3": 0.5}, clip=[0.0]*512)
    row = client.insert.call_args.kwargs["data"][0]
    assert list(row["emb_sparse"].keys()) == [3]
```
- [ ] **Step 3:** 跑失败 → **Step 4:** 实现 `milvus_store.py`（核心逻辑：`sparse={int(k): float(v) for k,v in sparse.items()}`；row 组装含 record 全字段；`count_photos` 用 `client.query` + `output_fields=["count(*)"]`）→ **Step 5:** 跑绿 → `git commit -m "feat: milvus 存储层与 compose"`
- [ ] **Step 6（人工协作点）:** 启动 Docker Desktop 后 `docker compose up -d milvus`，跑一条 e2e 标记的真实连通脚本确认 ensure_collection 建表成功（失败则记录到 PROGRESS 待办，不阻塞后续任务）。

---

### Task 3: meta.csv 校验器

**Files:**
- Create: `app/ingest/__init__.py`, `app/ingest/meta.py`, `data/raw/meta.csv`（3 行样例）, `tests/test_meta.py`

**Interfaces:**
- Produces: `load_meta(csv_path: Path, raw_dir: Path) -> tuple[list[PhotoRecord], list[str]]`（返回 (合法记录, 错误行列表)；错误行格式 `"photo_id: 原因"`）

- [ ] **Step 1: 失败测试**

```python
from pathlib import Path
from app.ingest.meta import load_meta
CSV = "photo_id,title,year,location,source_url,license\na1,骑楼,1930,广州,http://x,PD\na2,无证,,,,\n"
def test_rejects_missing_license(tmp_path):
    d = tmp_path; (d/"meta.csv").write_text(CSV, encoding="utf-8"); (d/"a1.jpg").touch()
    ok, errors = load_meta(d/"meta.csv", d)
    assert [r.photo_id for r in ok] == ["a1"]
    assert any("a2" in e and "license" in e for e in errors)
def test_rejects_missing_file(tmp_path):
    d = tmp_path; (d/"meta.csv").write_text(CSV, encoding="utf-8")  # 无 a1.jpg
    ok, errors = load_meta(d/"meta.csv", d)
    assert ok == [] and any("a1" in e for e in errors)
```
- [ ] **Step 2:** 跑失败 → **Step 3:** 实现（csv.DictReader 读 UTF-8；逐行校验 license/source_url 非空、`(raw_dir/{photo_id}.{jpg,png,jpeg}` 任一存在)；重复 photo_id 报错）→ **Step 4:** 跑绿 → **Step 5:** `git commit -m "feat: meta.csv 版权校验器"`

---

### Task 4: OCR 节点（RapidOCR 封装）

**Files:**
- Create: `app/ingest/ocr_op.py`, `tests/test_ocr_op.py`（并入 test_meta 文件亦可，独立更清晰）

**Interfaces:**
- Produces: `run_ocr(image_path: Path) -> str`（多行文本以 `\n` 连接；引擎加载失败或零结果返回空串，绝不抛异常）

- [ ] **Step 1: 失败测试**（mock 引擎，遵守"单测禁真调 OCR"）

```python
from unittest.mock import patch, MagicMock
from app.ingest.ocr_op import run_ocr
@patch("app.ingest.ocr_op._engine")
def test_joins_lines(mock_eng):
    mock_eng.return_value = MagicMock()
    with patch("app.ingest.ocr_op.RapidOCR") as R:
        R.return_value.return_value = ([[[0,0,"招牌 A字",0.9]], None])
        ...
def test_never_raises(tmp_path):
    f = tmp_path/"x.jpg"; f.write_bytes(b"bad")
    assert run_ocr(f) == ""
```
（实现细节：模块级惰性单例 `_get_engine()`；结果取 `result[0]` 中每项 `[box, text, score]` 的 text，score≥0.5 过滤。）→ 跑绿 → `git commit -m "feat: ocr 节点"`

---

### Task 5: LLM 客户端 + caption 节点（含 JSON 防御与降级拼接）

**Files:**
- Create: `app/infra/llm_client.py`, `app/ingest/caption_op.py`, `tests/test_caption_op.py`

**Interfaces:**
- Consumes: `Settings.dashscope_*`; `PhotoRecord`
- Produces: `Caption(description: str, tags: list[str], model: str)`；`caption_photo(image_path: Path, record: PhotoRecord) -> Caption`（VLM 失败/脏 JSON → `fallback_caption(record)`）；`fallback_caption(record) -> Caption`（description=`f"{record.title}（{record.year or '年代不详'}，{record.location or '地点不详'}）"`, tags=[], model="fallback"）

- [ ] **Step 1: 失败测试**

```python
def test_fallback_on_bad_json(record):
    cap = caption_photo(img, record, _client=_fake_client(return_text="不是JSON{{{"))
    assert cap.model == "fallback"
def test_parses_clean_json(record):
    cap = caption_photo(img, record, _client=_fake_client(return_text='{"description":"骑楼街景","tags":["骑楼"]}'))
    assert cap.tags == ["骑楼"] and cap.description == "骑楼街景"
def test_fallback_fields(record):
    c = fallback_caption(record); assert "标题" not in c.description and record.title in c.description
```
- [ ] **Step 2:** 跑失败 → **Step 3:** 实现：`llm_client.py` 用 `OpenAI(api_key, base_url=Settings.dashscope_base_url)`；`caption_op` prompt 要求仅输出 JSON（system 提示词写死"你是老照片编目员，输出 JSON：description≤80字 + tags 数组≤8个"）；解析走 `json.loads(text[text.find("{"):text.rfind("}")+1])` + try/except → fallback。依赖注入 `_client` 参数便于 mock → **Step 4:** 跑绿 → **Step 5:** `git commit -m "feat: vlm caption 节点+降级拼接"`

---

### Task 6: 向量化节点（BGE-M3 + Chinese-CLIP 单例）

**Files:**
- Create: `app/infra/embedder.py`, `tests/test_embedder.py`

**Interfaces:**
- Consumes: `Settings.bge_m3_model_path/.clip_model_path`
- Produces: `class Embedder:` 单例（`__new__` 缓存），方法 `texts(s: str|list[str]) -> tuple[list[list[float]], dict[int,float]]`（dense 取 [0]，sparse 由 BGEM3 返回的 `{'sparse': {idx: val}}` 转 `{int:float}`）、`image(path: Path) -> list[float]`（Chinese-CLIP get_image_feature 归一化后 flatten 512 维）、`free() -> None`（释放两模型显存，管线阶段切换时调用）

- [ ] **Step 1: 失败测试**（monkeypatch `FlagEmbedding.BGEM3FlagModel` 与 transformers CLIP 类，断言：单例复用同一实例；sparse 键转 int；`texts` 对空串也返回 1024 维零向量占位不抛异常）
- [ ] **Step 2:** 跑失败 → **Step 3:** 实现（BGEM3FlagModel(model_path, use_fp16=True)；Chinese-CLIP 用 `transformers.OFAVisionModel`? —— 不对，正确类是 `ChineseCLIPModel.from_pretrained`（transformers ≥4.27 支持 chinese-clip 架构），processor 同名 AutoProcessor）→ **Step 4:** 跑绿 → **Step 5:** `git commit -m "feat: 双塔向量化单例"`
- [ ] **Step 6（环境核对，非代码）:** 在本机 DocMind 的 HF 缓存中查 `BAAI/bge-m3` 是否已存在（`uv run python -c "from huggingface_hub import scan_cache_dir; print([r.repo_id for r in scan_cache_dir().repos])"`），存在则把绝对路径写入 `.env` 的 `BGE_M3_MODEL_PATH` 并同步 `.env.example` 注释。

---

### Task 7: vendor spike——CodeFormer/DDColor 环境排雷 + vision_ops 封装

**Files:**
- Create: `scripts/setup_vendors.ps1`, `models/vendor/COMMITS.md`, `app/ingest/vision_ops.py`, `tests/test_vision_ops.py`
- Modify: `.gitignore`（确认 `models/` 已忽略）

**Interfaces:**
- Produces: `restore_face(src: Path, dst: Path) -> bool`、`colorize(src: Path, dst: Path) -> bool`（子进程调用 vendor venv 的 python；返回 False=该步降级，绝不抛异常）；`_build_cmd(kind: str, src, dst) -> list[str]`（纯函数，可测）

- [ ] **Step 1: 手动 spike（本任务核心是排雷，允许失败换结论）**

```powershell
# scripts/setup_vendors.ps1 骨架：克隆→记录commit→建venv→装依赖
git clone https://github.com/sczhou/CodeFormer models/vendor/CodeFormer
git -C models/vendor/CodeFormer rev-parse HEAD | Out-File models/vendor/COMMITS.md -Append utf8
# DDColor: git clone https://github.com/piddnad/DDColor
# 各自 python -m venv + pip install -r requirements（CUDA 版 torch 按 4060 装 cu121）
# 权重下载统一 $env:HF_ENDPOINT="https://hf-mirror.com"
```
验收：对 1 张样张各产出 restored.jpg / colorized.jpg；任一 vendor 装不上→记录根因到 PROGRESS「风险跟踪」，colorize 改用 DeOldify 或触发 spec 降级（只交修复图），**不许静默假装成功**（防坑 #3）。
- [ ] **Step 2: 失败测试**（monkeypatch subprocess.run 断言命令包含 vendor python 绝对路径与超时参数；run 抛 TimeoutExpired/返回码≠0 时函数返回 False）

```python
@patch("app.ingest.vision_ops.subprocess.run")
def test_timeout_returns_false(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=300)
    assert restore_face(src, dst) is False
```
- [ ] **Step 3:** 跑失败 → **Step 4:** 实现（`subprocess.run(cmd, timeout=300, capture_output=True)`；成功判定 `returncode==0 and dst.exists()`）→ **Step 5:** 跑绿 → **Step 6:** `git commit -m "feat: vendor 视觉节点(修复/上色)+spike 结论"`

---

### Task 8: pipeline 编排 + CLI ingest

**Files:**
- Create: `app/ingest/pipeline.py`, `app/ingest/store_op.py`, `app/cli.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: 前 7 个任务的全部函数
- Produces: `run_pipeline(records: list[PhotoRecord], raw_dir: Path, out_root: Path, report_path: Path) -> IngestReport`；CLI：`python -m app.cli ingest --src data/raw [--limit N]`

- [ ] **Step 1: 失败测试**（全部 op 打桩）

```python
def test_degraded_colorize_still_ingests(records, monkeypatch):
    monkeypatch.setattr(pipe, "colorize", lambda s,d: False)   # 上色挂
    monkeypatch.setattr(pipe, "restore_face", lambda s,d: True)
    ...  # 其余 op 正常桩
    report = pipe.run_pipeline(records, raw, out, rep_path)
    statuses = {(i.step): i.status for i in report.items}
    assert statuses["colorize"] == StepStatus.DEGRADED
    assert store_stub.upserted[0].has_colorized is False   # 行内标记同步
def test_failed_single_photo_skips_not_abort(records):
    monkeypatch.setattr(pipe, "run_ocr", lambda p: (_ for _ in ()).throw(RuntimeError()))
    report = pipe.run_pipeline(...)   # 该照片 OCR=FAILED 但管线完成
def test_report_written_utf8(...):
    assert "骑楼" in rep_path.read_text(encoding="utf-8")
```
- [ ] **Step 2:** 跑失败 → **Step 3:** 实现 pipeline 主循环（每张照片顺序执行 restore→colorize→ocr→caption→vectorize→upsert；每步 try/except 记 `StepResult`；阶段末 `Embedder().free()`；文本入库内容=title+year+location+caption+ocr_text 拼接）→ **Step 4:** 跑绿 → **Step 5:** CLI argparse 三子命令骨架（ingest/serve/narrate/eval 中本期只实现 ingest，其余 `raise SystemExit("W2+")`）→ **Step 6:** `git commit -m "feat: 入库管线编排+CLI"`

---

### Task 9: README 快速开始 + .env.example 对齐

**Files:**
- Create: `README.md`；Modify: `.env.example`（最终核对键齐全：MILVUS_URI/DASHSCOPE_API_KEY/BGE_M3_MODEL_PATH/CLIP_MODEL_PATH/RERANK_BASE_URL/TTS 占位）

- [ ] 步骤：README 含「前置条件(Docker Desktop/GPU)→`uv sync`→`.env` 配置→`docker compose up -d milvus`→放素材→`python -m app.cli ingest --src data/raw`」六步 + 常见问题(HF 镜像/显存提示)。自查 `.env.example` 与 `config.py` 字段一一对应后 `git commit -m "docs: README 快速开始"`。

---

### Task 10: e2e 冒烟——3 张真实样张端到端（唯一真调外部服务测试）

**Files:**
- Create: `tests/e2e/test_ingest_e2e.py`；Modify: `docs/PROGRESS.md`（冒烟记录章节）

**Interfaces:** Consumes 全部真实组件。**人工前置：用户已放 3 张真实样张进 `data/raw` 并补全 meta.csv 六列。**

- [ ] **Step 1:** `pytest -m e2e tests/e2e/test_ingest_e2e.py -v`，断言：`count_photos==3`；每张存在 `processed/{id}/restored.jpg`；report JSON 无 FAILED 级联中断；总耗时 <9min。
- [ ] **Step 2:** 结果（通过/失败+耗时+踩坑）如实写入 `docs/PROGRESS.md`「冒烟记录」。
- [ ] **Step 3:** `git commit -m "test: W1 e2e 冒烟记录"`。

---

## Self-Review 记录
- Spec 覆盖：F1 全部子步骤有对应 Task；边界案例（无 license/OCR 空/VLM 挂/上色挂/重复导入/损坏图/单张失败不断批）分别落在 T3/T4/T5/T7/T2/T10 的测试里 ✅；检索(F2)/Agent/Web 属 W2 计划不在本文件 ❌→已知切分。
- 占位符扫描：无 TBD/TODO；Task 4 测试块中的 `...` 为省略号示意处已在实现步骤补齐规则文字 ✅。
- 类型一致性：`upsert_photo(client, record, dense, sparse, clip)` 与 T6 Embedder 返回 `(dense, sparse)`、T8 store_op 调用一致；`StepStatus` 三态贯穿 T1/T8 ✅。
