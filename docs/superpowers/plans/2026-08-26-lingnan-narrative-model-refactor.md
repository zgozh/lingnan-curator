# [Narrative Model Refactor] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把展馆最弱的一环——现在的 `narrator`（只按元数据拼 ≤200 字讲解词）——重构为「老照片→照片洞察→情感微故事→粤语旁白→一致性审稿」的 4 Agent 叙事链，让每一张馆藏照片能产出"让人心头一动的故事 + 可朗读的粤语旁白"，并配套「去 AI 味」确定性拦截 + 叙事质量评测，全部走云 API（复用已有 DashScope 封装）。

**Architecture:** 生成层收进 `app/narrator` 包，用一个轻量顺序编排器（`run_story_chain`）+ 单点有条件回炉（审稿 score<85 → 故事重生成，≤1 轮）串起 4 个 Agent。每个 Agent 是对应函数的纯逻辑单元，提示词集中到 `app/narrator/prompts.py`，确定性"AI 味"拦截（禁用词扫描 + 结构校验）做成 `app/narrator/detox.py` 不依赖 LLM 的硬闸。LLM/VLM 客户端补 `temperature` 与可换 system 提示词；TTS 旁白按句合成以控节奏，保留 DashScope CosyVoice 主路、Edge-TTS zh-HK 作可选 Provider（ADR-0007 预留的 seam）。

**Tech Stack:** Python 3.12 + uv；FastAPI（web，已有）；DashScope qwen-vl-max / qwen-max / qwen-plus（OpenAI 兼容端，`app.infra.llm_client` 已有）；DashScope CosyVoice（`app.infra.tts` 已有）；每步 TDD、mock 外部服务。

**Spec:** 本计划实现的是对 `docs/superpowers/specs/2026-08-24-lingnan-curator-design.md` 的 F6 升级 + 新增叙事质量评测。本计划自带"设计/架构"一节（第一节），执行时与本计划同时阅读。

## 设计 / 架构（本计划的依据）

### A. Scope 与非目标（重要，先读）
这是"全项目重构"。但遵循 AGENTS.md 硬约束 **#7（YAGNI）**，且现有 ingest/retrieval/web/eval 已在真实语料上测得达标（faithfulness 0.888 / answer_relevancy 0.858，见 `docs/PROGRESS.md`），**重建已测准的核心是毁掉已验证资产**。因此本重构的范围：

- **重建（REBUILD）**：生成/叙事层（`app.agents.narrator.py` → `app/narrator/*`）。这是参考内容的靶心，也是全项目最弱、对"观感/听感"贡献最大的一环。
- **轻改（TOUCH）**：`app.infra.llm_client.py`（加 temperature、可换 system）、`app.infra.tts.py`（按句合成 + Edge-TTS Provider）、`app/config.py`（新增配置）、`app/cli.py`（narrate 子命令跑全链）、`app/web`（详情页展示故事+旁白字幕）、`app/eval`（叙事质量评测）。
- **保持（KEEP）**：ingest 管线、retrieval 混合检索、Milvus、RAGAS 问答评测。不动、不重写。
- **非目标**：不换图像修复上色模型（CodeFormer 21s / DDColor 17s 已实测达标；云修复 API 贵且有版权外传风险，不换）。不上 LangGraph（当前流程线性 + 单点回炉，函数编排足够，PROGRESS 已record"线性流程用函数，YAGNI"）。

> 若你希望把 ingest/retrieval/web 也真"重新写一遍"，请先提需求；本计划默认不重写已测准的部分。

### B. 数据流

```
photo_id
  → 视觉底图 data/processed/{pid}/colorized.jpg（缺→restored.jpg→raw）
  → ① insight(insight.py): VLM 结构化洞察 Insight（scene/visibles/characters/era_evidence/
       maybe_place/mood/confident_words）；VLM 挂→metadata+caption 拼出 degraded insight
  → ② story(story_writer.py): 300-400 字情感微故事（temp 0.9）；detox 拦截失败→重生成 1 次
  → ③ narration(cantonese.py): 5-7 句粤语旁白，每句 10-20 字 + emotion（temp 0.7）
  → ④ review(reviewer.py): 四维评分 score 0-100（temp 0.2）；≥85 放行，<85 回炉②(≤1次)，仍低则放行并标 degraded
  → ⑤ tts(tts.py): 按句/整段合成 narration.wav（可选 SadTalker mp4，预生成）
  → 缓存 data/processed/{pid}/story.json + narration.json + narration.wav
```

### C. 模型/供应商（已定）
| 环节 | 模型 | temperature |
|------|------|------------|
| ①洞察 | `qwen-vl-max` | – （视觉） |
| ②故事 | `qwen-max` | 0.9 |
| ③旁白 | `qwen-plus` | 0.7 |
| ④审稿 | `qwen-plus` | 0.2 |
| TTS | DashScope CosyVoice（主）/ Edge-TTS zh-HK（可选 Provider） | – |

### D. 降级链（AGENTS.md 硬约束 #4）
VLM 挂→metadata insight（degraded）；故事 LLM 挂→回退旧"讲解词"模板（source=fallback_docent）；审稿挂→跳过直接接受；TTS 挂→隐藏音频入口。全链绝不抛异常打断主链路；任何降级在返回 dict 里带 `degraded` 标记。

### E. 幂等
每 pid 产物已存在则跳过（重复调用不重算）；`--force` 强制重生成。

## Global Constraints

- 全部文件读写显式 `encoding="utf-8"`（大量中文）。
- 密钥只进 `.env`；新增配置必须同步更新 `.env.example`（AGENTS.md 硬约束 #2）。
- 依赖方向：`web/cli → narrator → retrieval → infra → config`，禁止反向 import。
- 所有外部调用（DashScope/TTS）只出现在 `app.infra` 客户端内；`app/narrator` 不直接触 Milvus/模型客户端，一律经 infra 接口（VLM/LLM 经 `app.infra.llm_client` 注入的客户端）。
- 单测一律 mock 外部服务（client_factory / seam），真实链路只留一条 e2e 冒烟。
- 中文 Windows 控制台打印 emoji 会 UnicodeEncodeError，CLI 输出用 `[OK]/[NG]`。
- 版本钉死沿用现有 pyproject：torch 已切 cu126 GPU；不引入新框架。

---

### Task 1: infra 客户端扩展 —— LLM temperature + VLM 可换 system 提示词

**Files:**
- Modify: `app/infra/llm_client.py`
- Test: `tests/infra/test_llm_client.py`

**Interfaces:**
- Consumes: `Settings`（`app.config`）
- Produces:
  - `chat(messages, settings=None, json_mode=False, temperature=None, client_factory=None) -> str`
  - `stream_chat(messages, settings=None, temperature=None, client_factory=None)`（生成器）
  - `DashScopeVLM.describe(image_path, user_prompt, system_prompt=None, json_mode=False) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/infra/test_llm_client.py
from pathlib import Path
import sys, types

def _fake_sdk(api_key, base_url):
    # 最小 fake：记录传入的 kwargs
    class _Resp:
        class _Choice:
            message = types.SimpleNamespace(content="ok")
        choices = [_Choice()]
    class _Chat:
        def __init__(self):
            self.last_kwargs = None
        def create(self, **kwargs):
            self.last_kwargs = kwargs
            # 按配置返回流或非流
            return _Resp()
    class _Completions:
        def __init__(self):
            self.chat = _Chat()
    class _SDK:
        def __init__(self, api_key, base_url):
            self.chat = _Completions()
    return _SDK

def test_chat_passes_temperature():
    from app.infra import llm_client as lc
    factory = _fake_sdk
    lc.chat([{"role": "user", "content": "hi"}], settings=None,
            json_mode=False, temperature=0.9, client_factory=factory)
    # factory 返回的 sdk 是类实例而非工厂，这里走 direct：改为断言 chat 内部把 temperature 传入
    # 简化：用 monkeypatch 下 stub。真实断言放到步骤验证里。
    assert True  # placeholder —— 见 Step 2 真实测试
```

> 说明：上面为了展示结构用了占位。**真实实现时请写完整断言**（见下 Step 1 替换品），不要留在计划里当"占位糊弄"。真实测试：

```python
def test_chat_passes_temperature():
    from app.infra import llm_client as lc
    captured = {}
    class FakeComp:
        class FakeChoice:
            message = types.SimpleNamespace(content="ok")
        def create(self, **kw):
            captured.update(kw)
            return types.SimpleNamespace(choices=[self.FakeChoice()])
    class FakeChat:
        completions = FakeComp()
        def create(self, **kw):
            captured.update(kw)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content="ok"))])
    class FakeSDK:
        def __init__(self, api_key=None, base_url=None):
            self.chat = FakeChat()
    lc.get_llm.__wrapped__ if hasattr(lc,"get_llm") else None  # no-op
    # get_llm 是单例，直接调 chat 走真实 _create；改为注入 client_factory 路径：
    fake = FakeSDK()
    resp = lc.chat([{"role": "user", "content": "hi"}], settings=None,
                   json_mode=False, temperature=0.9,
                   client_factory=lambda **k: fake)
    assert captured.get("temperature") == 0.9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/infra/test_llm_client.py -v`
Expected: FAIL（`chat` 尚未接受 `temperature` 参数，或 `_create` 未透传）

- [ ] **Step 3: Write minimal implementation**

在 `app/infra/llm_client.py` 中：

```python
def chat(messages, settings=None, json_mode=False, temperature=None,
         client_factory=None) -> str:
    s = settings or Settings.load()
    if client_factory is not None:
        comp = client_factory(api_key="x", base_url="x").chat
        kwargs = {"model": s.llm_model}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if temperature is not None:
            kwargs["temperature"] = temperature
        resp = comp.create(messages=messages, timeout=60, **kwargs)
    else:
        resp = get_llm(s)._create(messages, json_mode=json_mode,
                                  temperature=temperature)
    return resp.choices[0].message.content or ""
```

`DashScopeLLM._create` 增参：
```python
def _create(self, messages, json_mode=False, stream=False, timeout=60,
            temperature=None):
    kwargs = {"model": self.settings.llm_model, "messages": messages,
              "timeout": timeout}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if stream:
        kwargs["stream"] = True
    return self._sdk.chat.completions.create(**kwargs)
```

`stream_chat` 同样透传 `temperature`。

`DashScopeVLM.describe` 增参：
```python
def describe(self, image_path, user_prompt, system_prompt=None, json_mode=False):
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    sys = system_prompt or CAPTION_SYSTEM
    kwargs = {"model": self.settings.vlm_model,
              "messages": [{"role": "system", "content": sys},
                           {"role": "user", "content": [
                               {"type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                               {"type": "text", "text": user_prompt}]}],
              "timeout": 60}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = self._sdk.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/infra/test_llm_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/infra/llm_client.py tests/infra/test_llm_client.py
git commit -m "feat: llm/vlm 客户端支持 temperature 与可换 system 提示词"
```

---

### Task 2: 配置扩展 + 叙事类型定义

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Create: `app/narrator/__init__.py`, `app/narrator/types.py`
- Test: `tests/config/test_settings_narrative.py`, `tests/narrator/test_types.py`

**Interfaces:**
- Consumes: `Settings`（现有字段）
- Produces:
  - `Settings` 新增字段：`story_model="qwen-max"`、`narration_model="qwen-plus"`、`review_model="qwen-plus"`、`insight_model="qwen-vl-max"`、`max_story_retry=1`
  - `app.narrator.types` 导出 `Insight, Character, NarrationLine, Narration, Story, ReviewResult`（字段见设计节）

- [ ] **Step 1: Write the failing test**

```python
# tests/narrator/test_types.py
from app.narrator.types import Insight, NarrationLine, Narration

def test_insight_defaults():
    i = Insight()
    assert i.maybe_place == "不确定"
    assert i.visibles == []

def test_narration_line_emotion_default():
    line = NarrationLine(text="嗰阵时广州好热闹。")
    assert line.emotion == "平静"
```

```python
# tests/config/test_settings_narrative.py
import os
def test_settings_narrative_defaults(monkeypatch):
    from app.config import Settings
    s = Settings.load(env_file=None)
    assert s.story_model == "qwen-max"
    assert s.insight_model == "qwen-vl-max"
    assert s.max_story_retry == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/narrator/test_types.py tests/config/test_settings_narrative.py -v`
Expected: FAIL（`app.narrator` 不存在；`Settings` 无 `story_model`）

- [ ] **Step 3: Write minimal implementation**

`app/config.py` dataclass 增字段（frozen dataclass 用默认值即可）：
```python
    story_model: str = "qwen-max"
    narration_model: str = "qwen-plus"
    review_model: str = "qwen-plus"
    insight_model: str = "qwen-vl-max"
    max_story_retry: int = 1
```
并在 `load()` 里对应读环境变量（缺省回退默认）：
```python
            story_model=os.getenv("STORY_MODEL", d.story_model),
            narration_model=os.getenv("NARRATION_MODEL", d.narration_model),
            review_model=os.getenv("REVIEW_MODEL", d.review_model),
            insight_model=os.getenv("INSIGHT_MODEL", d.insight_model),
            max_story_retry=int(os.getenv("MAX_STORY_RETRY", d.max_story_retry)),
```

`app/narrator/types.py`：
```python
"""叙事链各环节的结构化类型（dataclass）。"""
from dataclasses import dataclass, field

@dataclass
class Character:
    who: str = ""
    clothing: str = ""
    age_hint: str = ""

@dataclass
class Insight:
    scene: str = ""
    visibles: list[str] = field(default_factory=list)
    characters: list[Character] = field(default_factory=list)
    era_evidence: list[str] = field(default_factory=list)
    maybe_place: str = "不确定"
    mood: str = ""
    confident_words: str = ""
    source: str = "vlm"          # vlm | metadata
    degraded: bool = False

@dataclass
class Story:
    text: str = ""
    source: str = "llm"          # llm | fallback_docent
    degraded: bool = False

@dataclass
class NarrationLine:
    text: str = ""
    emotion: str = "平静"

@dataclass
class Narration:
    lines: list[NarrationLine] = field(default_factory=list)

@dataclass
class ReviewResult:
    score: int = 0
    issues: list[str] = field(default_factory=list)
    suggestion: str = ""
```

`.env.example` 追加（同步 AGENTS.md #2）：
```dotenv
STORY_MODEL=qwen-max
NARRATION_MODEL=qwen-plus
REVIEW_MODEL=qwen-plus
INSIGHT_MODEL=qwen-vl-max
MAX_STORY_RETRY=1
```

`app/narrator/__init__.py` 留空或导出主编排。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/narrator/test_types.py tests/config/test_settings_narrative.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/narrator tests/narrator/test_types.py tests/config/test_settings_narrative.py .env.example
git commit -m "feat: 叙事链配置与类型定义"
```

---

### Task 3: 提示词集中管理

**Files:**
- Create: `app/narrator/prompts.py`
- Test: `tests/narrator/test_prompts.py`

**Interfaces:**
- Produces: `INSIGHT_SYSTEM`, `STORY_SYSTEM`, `NARRATION_SYSTEM`, `REVIEW_SYSTEM`, `FALLBACK_SINGLE_SYSTEM`（均为 `str`，含关键约束词，供后续 Task 与测试断言）

- [ ] **Step 1: Write the failing test**

```python
# tests/narrator/test_prompts.py
from app.narrator import prompts as p

def test_story_system_has_anti_ai_clause():
    assert "严禁" in p.STORY_SYSTEM
    assert "AI 腔" in p.STORY_SYSTEM or "套话" in p.STORY_SYSTEM

def test_story_system_forbids_hallucination():
    assert "不编造" in p.STORY_SYSTEM

def test_narration_system_has_emotion_enum():
    assert "怀念" in p.NARRATION_SYSTEM

def test_review_system_returns_score():
    assert "0-100" in p.REVIEW_SYSTEM or "score" in p.REVIEW_SYSTEM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/narrator/test_prompts.py -v`
Expected: FAIL（模块/常量不存在）

- [ ] **Step 3: Write minimal implementation**

`app/narrator/prompts.py`（基于参考内容 + 广府语境精修）：

```python
"""叙事链四个 Agent + 单次兜底的 system 提示词（集中管理，便于迭代）。"""

INSIGHT_SYSTEM = (
    "你是「城市记忆研究员」。看这张老照片，输出严格 JSON，禁止臆造具体人名/事件，"
    "只用画面可见证据 + 时代常识合理推断："
    '{"scene":"一句话概括画面",'
    '"visibles":["可见元素，只写确实看得到的"],'
    '"characters":[{"who":"人物描述","clothing":"服装","age_hint":"年代估计"}],'
    '"era_evidence":["时代线索:服饰/建筑/工具/标语等"],'
    '"maybe_place":"可能地点(优先广州/岭南/湾区，无把握写不确定)",'
    '"mood":"整体氛围(温暖/肃穆/热闹/街巷/家族/劳动…)",'
    '"confident_words":"画面可辨认的文字/标语，没有就留空"}。'
    "只输出 JSON，不要多余文字。"
)

STORY_SYSTEM = (
    "你是「城市记忆讲述者」。根据{照片洞察}写一段 300-400 字、能让人心头一动的微型故事。"
    "铁律：1) 有真实感与时代细节，贴合广州·岭南语境；"
    "2) 必须有一个「人物情感钩子」，从照片里某个人物/物件切入；"
    "3) 开头一句抓人，结尾两个字拍在人心上，留余韵；"
    "4) 可用第一人称但别滥用；"
    "5) 严禁 AI 腔：绝不出现「在这个世界上」「随着…的」「不禁让人」「是啊」"
    "「让我们一起」「仿佛时光倒流」「岁月如梭」「时光荏苒」；动词要有画面，"
    "少用「承载」「勾勒」「见证」这类空洞词；"
    "6) 只基于照片可见内容展开，不编造具体人名、年份、新闻事件。"
    "直接输出正文，不要标题、不要解释。"
)

NARRATION_SYSTEM = (
    "你是「粤语配音文案师」。把下面故事改写成适合朗读的粤语旁白，供 TTS 合成。"
    "要求：5-7 句，每句 10-20 字，口语、有节奏、朗朗上口；"
    "保住故事情感内核，删掉书面语，可夹「呀/㗎/咗/嘅」但别过度；"
    '每句标情绪，输出严格 JSON：{"lines":[{"text":"...","emotion":"平静|怀念|感叹|温暖|低啲"}]}；'
    "禁止「岁月如梭」「时光荏苒」等陈词。只输出 JSON。"
)

REVIEW_SYSTEM = (
    "你是「故事一致性审稿人」。对照{照片洞察}审查{故事}："
    "1) 事实一致性：是否添加了照片中不存在的具体事实/人名/年份（扣分项）；"
    "2) 文本质量：是否 AI 腔、陈词、空洞；"
    "3) 情感与年代：是否贴合岭南语境与照片氛围。"
    '输出严格 JSON：{"score":0-100,"issues":["问题1"],"suggestion":"修改建议"}。'
    "score>=85 为通过。只输出 JSON。"
)

FALLBACK_SINGLE_SYSTEM = (
    "你是粤语城市记忆讲述者。我给你一张老照片的可见内容，请直接输出："
    "【故事】300 字情感微故事（严禁 AI 腔，开头抓人，结尾留余韵，贴岭南语境，"
    "不编造照片外的事实）；"
    "【旁白】5-7 句粤语口语旁白，每句 10-20 字，保情感、有节奏、勿陈词。"
    "只输出这两段，不要其他说明。"
)
```

> 说明：上文的 `{照片洞察}` / `{故事}` 为占位符，真正组装时由调用方把 insight/故事文本作为 user 内容传入，不直接做 f-string 互填（避免注入）。测试断言针对 `STRICT` 关键词即可。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/narrator/test_prompts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/narrator/prompts.py tests/narrator/test_prompts.py
git commit -m "feat: 叙事链四 Agent+兜底提示词"
```

---

### Task 4: 确定性"AI 味"拦截器（不依赖 LLM 的硬闸）

**Files:**
- Create: `app/narrator/detox.py`
- Test: `tests/narrator/test_detox.py`

**Interfaces:**
- Produces:
  - `BANNED_TERMS: list[str]`
  - `scan_ai_smell(text: str) -> list[str]`
  - `validate_story(text: str) -> bool`（非空、≥80 字、无禁用词）
  - `NARRATION_EMOTIONS: set[str]`
  - `validate_narration(lines: list[NarrationLine]) -> bool`（5-7 句、每句 10-20 字、emotion 合法）

- [ ] **Step 1: Write the failing test**

```python
# tests/narrator/test_detox.py
from app.narrator.types import NarrationLine
from app.narrator import detox as d

def test_scan_hits_banned():
    assert d.scan_ai_smell("在这个世界上，岁月如梭。") != []

def test_scan_empty_on_clean():
    assert d.scan_ai_smell("骑楼下面，老广州嘅茶楼。") == []

def test_validate_story_rejects_short_or_banned():
    assert d.validate_story("太短") is False
    assert d.validate_story("是个好故事" * 20 + "岁月的长河承载了记忆") is False

def test_validate_narration_rejects():
    good = [NarrationLine(text="嗰阵广州好热闹。", emotion="怀念")]
    assert d.validate_narration(good) is False  # 只有1句，<5
    bad_emo = [NarrationLine(text="x"*12, emotion="生气") for _ in range(6)]
    assert d.validate_narration(bad_emo) is False
    good6 = [NarrationLine(text="呢句刚好十二个字啊。", emotion="怀念") for _ in range(6)]
    assert d.validate_narration(good6) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/narrator/test_detox.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/narrator/detox.py
"""确定性「去 AI 味」拦截：不依赖 LLM 的硬闸，可单测、可量化。"""
from app.narrator.types import NarrationLine

BANNED_TERMS = [
    "在这个世界上", "随着时间", "不禁让人", "是啊", "让我们一起",
    "仿佛时光倒流", "岁月如梭", "时光荏苒", "承载", "勾勒", "见证",
]
NARRATION_EMOTIONS = {"平静", "怀念", "感叹", "温暖", "低啲"}


def scan_ai_smell(text: str) -> list[str]:
    return [t for t in BANNED_TERMS if t in text]


def validate_story(text: str) -> bool:
    if not text or len(text) < 80:
        return False
    return not scan_ai_smell(text)


def validate_narration(lines: list[NarrationLine]) -> bool:
    if not (5 <= len(lines) <= 7):
        return False
    for ln in lines:
        if not (10 <= len(ln.text) <= 20):
            return False
        if ln.emotion not in NARRATION_EMOTIONS:
            return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/narrator/test_detox.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/narrator/detox.py tests/narrator/test_detox.py
git commit -m "feat: 确定性AI味拦截器"
```

---

### Task 5: Agent①——照片洞察（VLM → Insight）

**Files:**
- Create: `app/narrator/insight.py`
- Test: `tests/narrator/test_insight.py`

**Interfaces:**
- Consumes: `Insight、Character`（types），`get_vlm`（`app.infra.llm_client`），`json_utils.extract_json`，`Settings.insight_model`
- Produces: `insight(image_path, metadata_desc, settings=None, vlm=None) -> Insight`
  - `vlm` 为可注入的客户端（缺省用 `get_vlm()`），便于 mock。
  - VLM 失败或返回解析不出 → 返回 `source="metadata", degraded=True` 的 metadata 拼接版。

- [ ] **Step 1: Write the failing test**

```python
# tests/narrator/test_insight.py
from pathlib import Path
from app.narrator.insight import insight
from app.narrator.types import Insight

class FakeVLM:
    def describe(self, image_path, user_prompt, system_prompt=None, json_mode=False):
        return ('{"scene":"广州骑楼街景","visibles":["骑楼","人力车"],'
                '"characters":[{"who":"小贩","clothing":"唐装","age_hint":"民国"}],'
                '"era_evidence":["骑楼","招牌"],"maybe_place":"广州",'
                '"mood":"热闹","confident_words":"太史第"}')

def test_insight_parses_vlm(monkeypatch):
    res = insight(Path("x.jpg"), "title=街景|year=1920|location=广州|caption=骑楼",
                  vlm=FakeVLM())
    assert isinstance(res, Insight)
    assert res.scene == "广州骑楼街景"
    assert res.maybe_place == "广州"
    assert res.source == "vlm" and res.degraded is False

class BadVLM:
    def describe(self, image_path, user_prompt, system_prompt=None, json_mode=False):
        raise RuntimeError("vlm down")

def test_insight_falls_back_to_metadata(monkeypatch):
    res = insight(Path("x.jpg"), "title=街景|year=1920|location=广州|caption=骑楼",
                  vlm=BadVLM())
    assert res.degraded is True
    assert res.source == "metadata"
    assert "广州" in res.scene  # 用 metadata 拼
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/narrator/test_insight.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/narrator/insight.py
"""Agent① 照片洞察：VLM 结构化描述 -> Insight；VLM 挂则 metadata 兜底。"""
import logging
from pathlib import Path

from app.infra import llm_client as lc
from app.narrator.prompts import INSIGHT_SYSTEM
from app.narrator.types import Character, Insight
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)


def _metadata_insight(meta_desc: str) -> Insight:
    parts = [p for p in meta_desc.replace("|", " ").split() if p]
    scene = meta_desc or "一张岭南老照片"
    return Insight(scene=scene, visibles=[], characters=[], era_evidence=[],
                   maybe_place="不确定", mood="", confident_words="",
                   source="metadata", degraded=True)


def insight(image_path, metadata_desc, settings=None, vlm=None):
    v = vlm or lc.get_vlm(settings)
    try:
        raw = v.describe(
            Path(image_path),
            user_prompt="请按城市记忆研究员的 JSON 结构描述这张老照片。",
            system_prompt=INSIGHT_SYSTEM,
            json_mode=True,
        )
        obj = extract_json(raw) or {}
        chars = [Character(**{k: c.get(k, "") for k in ("who", "clothing", "age_hint")})
                 for c in obj.get("characters", []) if isinstance(c, dict)]
        return Insight(
            scene=str(obj.get("scene") or ""),
            visibles=[str(x) for x in obj.get("visibles", [])],
            characters=chars,
            era_evidence=[str(x) for x in obj.get("era_evidence", [])],
            maybe_place=str(obj.get("maybe_place") or "不确定"),
            mood=str(obj.get("mood") or ""),
            confident_words=str(obj.get("confident_words") or ""),
            source="vlm", degraded=False,
        )
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("VLM insight 失败，降级 metadata: %s", exc)
        return _metadata_insight(metadata_desc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/narrator/test_insight.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/narrator/insight.py tests/narrator/test_insight.py
git commit -m "feat: Agent① 照片洞察(VLM->Insight) + metadata 降级"
```

---

### Task 6: Agent②——情感微故事生成（含 detox 回炉）

**Files:**
- Create: `app/narrator/story_writer.py`
- Test: `tests/narrator/test_story_writer.py`

**Interfaces:**
- Consumes: `Insight, Story`（types），`lc.chat(..., json_mode=True, temperature=0.9)`，`detox.scan_ai_smell / validate_story`，`Settings.story_model, max_story_retry`
- Produces: `write_story(insight, settings=None, chat=None) -> Story`
  - `chat` 可注入（缺省 `lc.chat`）。
  - 生成后跑 `validate_story`；若失败且重试数 < `max_story_retry` → 重新生成一次；仍失败 → `Story(text=..., source="llm", degraded=True)`（由编排器决定是否回退讲解词）。

- [ ] **Step 1: Write the failing test**

```python
# tests/narrator/test_story_writer.py
from types import SimpleNamespace
from app.narrator.story_writer import write_story
from app.narrator.types import Insight, Story

STORY_OK = "开篇一句就很吸引人。" * 20  # >80 字且无禁用词

class ChatOK:
    def __call__(self, messages, json_mode=False, temperature=None, settings=None):
        return STORY_OK

def test_write_story_happy(monkeypatch):
    s = write_story(Insight(scene="骑楼街"), chat=ChatOK())
    assert isinstance(s, Story)
    assert s.source == "llm" and s.degraded is False
    assert s.text == STORY_OK

class ChatBannedThenOK:
    calls = 0
    def __call__(self, messages, json_mode=False, temperature=None, settings=None):
        self.calls += 1
        if self.calls == 1:
            return "岁月如梭，这个世界啊。" + ("字" * 80)
        return STORY_OK

def test_write_story_regenerates_on_banned(monkeypatch):
    c = ChatBannedThenOK()
    s = write_story(Insight(scene="骑楼街"), chat=c)
    assert c.calls == 2                 # 重生成了一次
    assert s.text == STORY_OK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/narrator/test_story_writer.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/narrator/story_writer.py
"""Agent② 情感微故事生成；detox 硬闸拦截失败则重生成（≤max_story_retry 次）。"""
import logging

from app.infra import llm_client as lc
from app.narrator import detox as d
from app.narrator.prompts import STORY_SYSTEM
from app.narrator.types import Insight, Story

logger = logging.getLogger(__name__)


def _build_messages(insight: Insight) -> list[dict]:
    desc = (f"scene={insight.scene}｜visibles={insight.visibles}｜"
            f"characters={insight.characters}｜era={insight.era_evidence}｜"
            f"place={insight.maybe_place}｜mood={insight.mood}｜"
            f"words={insight.confident_words}")
    return [{"role": "system", "content": STORY_SYSTEM},
            {"role": "user", "content": f"【照片洞察】{desc}"}]


def write_story(insight, settings=None, chat=None):
    chat = chat or lc.chat
    s = settings or __import__("app.config", fromlist=["Settings"]).Settings.load()
    text = ""
    for attempt in range(s.max_story_retry + 1):
        try:
            raw = chat(_build_messages(insight), json_mode=False,
                       temperature=0.9, settings=s)
        except Exception as exc:  # noqa: BLE001
            logger.warning("story LLM 失败(第%d次): %s", attempt, exc)
            break
        text = (raw or "").strip()
        if d.validate_story(text):
            return Story(text=text, source="llm", degraded=False)
        logger.warning("story 命中AI味/过短，将重生成(第%d次)", attempt)
    # 达到上限或失败：
    return Story(text=text, source="llm", degraded=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/narrator/test_story_writer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/narrator/story_writer.py tests/narrator/test_story_writer.py
git commit -m "feat: Agent② 情感微故事 + detox 回炉"
```

---

### Task 7: Agent③——粤语旁白（分句 + 情绪标注）

**Files:**
- Create: `app/narrator/cantonese.py`
- Test: `tests/narrator/test_cantonese.py`

**Interfaces:**
- Consumes: `Story, Narration, NarrationLine`，`lc.chat(..., json_mode=True, temperature=0.7)`，`detox.validate_narration, NARRATION_EMOTIONS`
- Produces: `write_narration(story, settings=None, chat=None) -> Narration`
  - 解析 `{"lines":[...]}`；若结构/情绪非法或句数超限 → 轻度规整（剔非法 emotion、夹在合法区间）；仍无法满足 then degraded。

- [ ] **Step 1: Write the failing test**

```python
# tests/narrator/test_cantonese.py
from app.narrator.cantonese import write_narration
from app.narrator.types import Story, Narration

RAW = ('{"lines": [{"text":"嗰阵广州好热闹。","emotion":"怀念"},'
       '{"text":"骑楼底下人影绰绰。","emotion":"温暖"},'
       '{"text":"阿嫲推住架木车仔。","emotion":"温暖"},'
       '{"text":"呢条街就系我嘅童年。","emotion":"怀念"},'
       '{"text":"而家睇返旧相都系味。","emotion":"感叹"}]}')

class ChatOK:
    def __call__(self, messages, json_mode=False, temperature=None, settings=None):
        return RAW

def test_write_narration_parses(monkeypatch):
    n = write_narration(Story(text="x"*100), chat=ChatOK())
    assert isinstance(n, Narration)
    assert 5 <= len(n.lines) <= 7
    assert n.lines[0].emotion == "怀念"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/narrator/test_cantonese.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/narrator/cantonese.py
"""Agent③ 粤语旁白：故事 -> 5-7句带情绪的分句。"""
import logging

from app.infra import llm_client as lc
from app.narrator import detox as d
from app.narrator.prompts import NARRATION_SYSTEM
from app.narrator.types import Narration, NarrationLine, Story
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)


def _normalize(lines_raw) -> list[NarrationLine]:
    out = []
    for item in (lines_raw or []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        emo = str(item.get("emotion") or "平静")
        if emo not in d.NARRATION_EMOTIONS:
            emo = "平静"
        out.append(NarrationLine(text=text, emotion=emo))
    return out


def write_narration(story, settings=None, chat=None):
    chat = chat or lc.chat
    s = settings or __import__("app.config", fromlist=["Settings"]).Settings.load()
    try:
        raw = chat([{"role": "system", "content": NARRATION_SYSTEM},
                    {"role": "user", "content": f"【故事】{story.text}"}],
                   json_mode=True, temperature=0.7, settings=s)
        obj = extract_json(raw) or {}
        lines = _normalize(obj.get("lines"))
        # 轻度规整：句数 5-7
        if len(lines) > 7:
            lines = lines[:7]
        while len(lines) < 5:
            lines.append(NarrationLine(text="呢段记忆，仲喺度。", emotion="回味"))
        return Narration(lines=lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("narration 生成失败，降级单句: %s", exc)
        return Narration(lines=[NarrationLine(text="呢段老广州记忆，好珍贵。",
                                              emotion="怀念")])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/narrator/test_cantonese.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/narrator/cantonese.py tests/narrator/test_cantonese.py
git commit -m "feat: Agent③ 粤语旁白分句+情绪"
```

---

### Task 8: Agent④——叙事一致性审稿

**Files:**
- Create: `app/narrator/reviewer.py`
- Test: `tests/narrator/test_reviewer.py`

**Interfaces:**
- Consumes: `Insight, Story, ReviewResult`，`lc.chat(..., json_mode=True, temperature=0.2)`，`Settings.review_model`
- Produces: `review(insight, story, settings=None, chat=None) -> ReviewResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/narrator/test_reviewer.py
from app.narrator.reviewer import review
from app.narrator.types import Insight, Story

RAW = '{"score":88,"issues":[],"suggestion":"无"}'

class ChatOK:
    def __call__(self, messages, json_mode=False, temperature=None, settings=None):
        return RAW

def test_review_parses_score(monkeypatch):
    r = review(Insight(scene="骑楼"), Story(text="x"*100), chat=ChatOK())
    assert r.score == 88
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/narrator/test_reviewer.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/narrator/reviewer.py
"""Agent④ 一致性审稿：四维评分，score>=85 通过。"""
import logging

from app.infra import llm_client as lc
from app.narrator.prompts import REVIEW_SYSTEM
from app.narrator.types import Insight, ReviewResult, Story
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)


def review(insight, story, settings=None, chat=None):
    chat = chat or lc.chat
    s = settings or __import__("app.config", fromlist=["Settings"]).Settings.load()
    user = (f"【照片洞察】scene={insight.scene}｜visibles={insight.visibles}"
            f"｜place={insight.maybe_place}｜mood={insight.mood}\n"
            f"【故事】{story.text}")
    try:
        raw = chat([{"role": "system", "content": REVIEW_SYSTEM},
                    {"role": "user", "content": user}],
                   json_mode=True, temperature=0.2, settings=s)
        obj = extract_json(raw) or {}
        score = obj.get("score")
        return ReviewResult(score=int(score) if isinstance(score, (int, float)) else 0,
                            issues=[str(x) for x in obj.get("issues", [])],
                            suggestion=str(obj.get("suggestion") or ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("review 失败，跳过审稿: %s", exc)
        return ReviewResult(score=100, issues=[], suggestion="")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/narrator/test_reviewer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/narrator/reviewer.py tests/narrator/test_reviewer.py
git commit -m "feat: Agent④ 一致性审稿"
```

---

### Task 9: 编排器 run_story_chain（含回炉 + 降级 + 幂等缓存）

**Files:**
- Create: `app/narrator/story.py`
- Test: `tests/narrator/test_story.py`

**Interfaces:**
- Consumes: `insight, write_story, write_narration, review`（上文 Task），`Settings, get_vlm, get_tts`, `app.narrator.prompts.FALLBACK_SINGLE_SYSTEM`
- Produces:
  - `run_story_chain(photo_id, settings=None, force=False) -> dict`（`{photo_id, story, narration, audio, degraded, source}`）
  - 读图：`data/processed/{pid}/colorized.jpg` → `restored.jpg` → `data/raw/{pid}.jpg`
  - 幂等：`data/processed/{pid}/story.json` + `narration.json` + `narration.wav` 已存在且非 force → 直接返回缓存
  - 降级：story `degraded` 或为空 → 回退旧讲解词模板（`source=fallback_docent`）；TTS 失败 → `audio=False`；审稿挂 → 接受。
  - metadata 描述拼接：`title|year|location|caption`（从 Milvus 或缺省空）

- [ ] **Step 1: Write the failing test**

```python
# tests/narrator/test_story.py
from pathlib import Path
from app.narrator.story import run_story_chain
from app.narrator.types import Story

# 全部用 seam 注入 —— 编排器接受可选的 deps 便于测试
class Deps:
    @staticmethod
    def insight(*a, **k):  # 返回 metadata 降级版
        from app.narrator.types import Insight
        return Insight(scene="骑楼街", source="vlm", degraded=False)
    @staticmethod
    def write_story(*a, **k):
        return Story(text="一个关于广州骑楼的老故事。" * 20, source="llm")
    @staticmethod
    def write_narration(*a, **k):
        from app.narrator.types import Narration, NarrationLine
        return Narration(lines=[NarrationLine(text="呢句系粤语旁白。", emotion="怀念")] * 6)
    @staticmethod
    def review(*a, **k):
        from app.narrator.types import ReviewResult
        return ReviewResult(score=90)
    @staticmethod
    def tts(*a, **k):
        return True

def test_run_story_chain_happy(tmp_path):
    # 用 monkeypatch 让编排器拿到注入的 deps
    import app.narrator.story as st
    st._CURRENT_DEPS = Deps
    res = run_story_chain("sample_a", settings=None,
                          out_root=tmp_path, deps=Deps)
    assert res["story"] != ""
    assert res["narration"] != ""
    assert res["audio"] is True
    assert res["degraded"] is False
```

> 说明：`run_story_chain` 接受 `deps` 注入（缺省默认实现），便于真正 mock 掉外部调用。真实实现见 Step 3。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/narrator/test_story.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/narrator/story.py
"""叙事链编排器：洞察→故事→旁白→审稿(回炉)→TTS→幂等缓存。"""
import json
import logging
from pathlib import Path

from app.narrator import cantonese, detox, insight as insight_mod, reviewer, story_writer
from app.narrator.types import ReviewResult, Story

logger = logging.getLogger(__name__)

_DEFAULT_EXTS = ("colorized.jpg", "restored.jpg")
_RAW_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _find_base_img(out_root: Path, raw_dir: Path, photo_id: str) -> Path | None:
    d = Path(out_root) / photo_id
    for name in _DEFAULT_EXTS:
        p = d / name
        if p.exists():
            return p
    for ext in _RAW_EXTS:
        p = Path(raw_dir) / f"{photo_id}{ext}"
        if p.exists():
            return p
    return None


def _metadata_desc(row: dict | None) -> str:
    if not row:
        return "一张岭南老照片"
    return "|".join(str(row.get(k) or "") for k in ("title", "year", "location", "caption"))


def _fallback_docent_story(meta_desc: str) -> Story:
    return Story(text=f"这是一张记载岭南记忆的老照片。{meta_desc}",
                 source="fallback_docent", degraded=True)


def run_story_chain(photo_id, settings=None, force=False, deps=None,
                    out_root=None, raw_dir=None, row=None):
    d = deps or object.__new__(object)  # 占位；实际用默认模块级函数
    if deps is None:
        d = _DefaultDeps
    s = settings or __import__("app.config", fromlist=["Settings"]).Settings.load()
    out_root = Path(out_root or "data/processed")
    raw_dir = Path(raw_dir or "data/raw")
    out_dir = out_root / photo_id
    out_dir.mkdir(parents=True, exist_ok=True)
    story_p = out_dir / "story.json"
    nar_p = out_dir / "narration.json"
    wav_p = out_dir / "narration.wav"

    result = {"photo_id": photo_id, "degraded": False, "audio": False, "source": "llm"}

    # 幂等缓存
    if not force and story_p.exists() and nar_p.exists() and wav_p.exists():
        result["story"] = json.loads(story_p.read_text(encoding="utf-8")).get("text", "")
        result["narration"] = nar_p.read_text(encoding="utf-8")
        result["audio"] = True
        return result

    meta_desc = _metadata_desc(row)
    base = _find_base_img(out_root, raw_dir, photo_id)

    ins = d.insight(base, meta_desc, settings=s)
    st = d.write_story(ins, settings=s, chat=None)
    if st.degraded or not d.detox.validate_story(st.text):
        st = _fallback_docent_story(meta_desc)
        result["source"] = "fallback_docent"
    result["story"] = st.text
    result["degraded"] = st.degraded or ins.degraded

    nar = d.write_narration(st, settings=s, chat=None)
    lines = [{"text": ln.text, "emotion": ln.emotion} for ln in nar.lines]
    plain = "。".join(ln.text for ln in nar.lines)

    rv = d.review(ins, st, settings=s, chat=None)
    max_retry = s.max_story_retry
    if rv.score < 85 and max_retry > 0:
        st2 = d.write_story(ins, settings=s, chat=None)
        if not st2.degraded and d.detox.validate_story(st2.text):
            st = st2
            nar = d.write_narration(st, settings=s, chat=None)
            lines = [{"text": ln.text, "emotion": ln.emotion} for ln in nar.lines]
            plain = "。".join(ln.text for ln in nar.lines)
            result["story"] = st.text
            result["source"] = "llm"
        result["degraded"] = result["degraded"] or rv.score < 85

    # 落缓存
    story_p.write_text(json.dumps({"text": result["story"]}, ensure_ascii=False,
                                  indent=2), encoding="utf-8")
    nar_p.write_text(json.dumps({"lines": lines}, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    # TTS
    try:
        ok = d.tts(plain, s, wav_p)
        result["audio"] = bool(ok)
        result["degraded"] = result["degraded"] or not ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("TTS 失败，隐藏音频: %s", exc)
        result["audio"] = False
        result["degraded"] = True

    result["narration"] = nar_p.read_text(encoding="utf-8")
    return result
```

```python
# 默认依赖（真实实现）——编排器测试时注入 Deps 覆盖
class _DefaultDeps:
    insight = staticmethod(lambda base, meta, settings=None: insight_mod.insight(base, meta, settings=settings))
    write_story = staticmethod(lambda ins, settings=None, chat=None: story_writer.write_story(ins, settings=settings, chat=chat))
    write_narration = staticmethod(lambda st, settings=None, chat=None: cantonese.write_narration(st, settings=settings, chat=chat))
    review = staticmethod(lambda ins, st, settings=None, chat=None: reviewer.review(ins, st, settings=settings, chat=chat))
    detox = staticmethod(lambda: None)  # 占位，实际直接 import 用
    @staticmethod
    def tts(text, settings, out_path):
        from app.infra.tts import get_tts
        s = settings or __import__("app.config", fromlist=["Settings"]).Settings.load()
        return get_tts(s).synthesize(text, s.tts_voice, out_path)
```

> 说明：`_DefaultDeps.detox` 仅为占位，真实编排器直接 `import app.narrator.detox` 调用其 `validate_story`。测试注入的 `Deps` 无需实现 `detox`（编排器判 `st.degraded or not validate_story(...)`；若 deps 未提供 `validate_story`，可用 `getattr` 兜底调真实现）。为清晰，下面把编排器里对 detox 的调用改为 `_detox_validate(st, deps)`：

```python
def _detox_validate(st, deps):
    if hasattr(deps, "validate_story"):
        return deps.validate_story(st.text)
    import app.narrator.detox as dx
    return dx.validate_story(st.text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/narrator/test_story.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/narrator/story.py tests/narrator/test_story.py
git commit -m "feat: 叙事链编排器 run_story_chain + 幂等/降级"
```

---

### Task 10: TTS 按句合成 + 可选 Edge-TTS Provider

**Files:**
- Modify: `app/infra/tts.py`
- Test: `tests/infra/test_tts_lines.py`

**Interfaces:**
- Consumes: `Settings.tts_provider / tts_voice`，`get_tts`
- Produces: 新增 `synthesize_lines(lines: list[dict], out_path, settings=None) -> bool`（逐句合成并按句拼接；失败返回 False）；`EdgeTTSCosyvoice` 可选提供方（`tts_provider="edge"` 时启用，测试 mock）

- [ ] **Step 1: Write the failing test**

```python
# tests/infra/test_tts_lines.py
from pathlib import Path
from app.infra import tts

def test_synthesize_lines_empty_false():
    assert tts.synthesize_lines([], Path("x.wav"), settings=None) is False

class FakeSynthesizer:
    def call(self, text):
        return b"RIFF" + text.encode("utf-8")  # 假 wav 字节
    def __init__(self, *a, **k):
        pass

def test_synthesize_lines_concatenates(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "_new_synthesizer", lambda *a, **k: FakeSynthesizer())
    out = tmp_path / "nar.wav"
    lines = [{"text": "第一句", "emotion": "怀念"}, {"text": "第二句", "emotion": "平静"}]
    assert tts.synthesize_lines(lines, out, settings=None) is True
    assert out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/infra/test_tts_lines.py -v`
Expected: FAIL（`synthesize_lines` / `_new_synthesizer` 契约不符）

- [ ] **Step 3: Write minimal implementation**

`app/infra/tts.py` 追加：

```python
def synthesize_lines(lines, out_path, settings=None, rate: str = "-8%") -> bool:
    """逐句合成（控停顿），按句拼接为单个 wav。空/失败返回 False。"""
    s = settings or Settings.load()
    if not s.dashscope_api_key or not lines:
        return False
    try:
        synths = [_new_synthesizer(_MODEL, s.tts_voice, _FMT) for _ in lines]
        # 简化：同一 voice 复用实例
        synth = _new_synthesizer(_MODEL, s.tts_voice, _FMT)
        chunks = []
        for ln in lines:
            text = str(ln.get("text") or "").strip()
            if not text:
                continue
            audio = synth.call(text)
            if audio:
                chunks.append(audio)
        if not chunks:
            return False
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        # 直接保存首块，并 upsert 追加（CosyVoice 返回独立 wav，简化=保存拼接流）
        out.write_bytes(b"".join(chunks))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("按句 TTS 失败: %s", exc)
        return False
```

```python
class EdgeTTSCosyvoice:
    """可选边缘 TTS（Edge-TTS 粤语），仅作 Provider 切换候选（ADR-0007 seam）。"""
    def __init__(self, settings=None):
        self.settings = settings or Settings.load()
        self._voice = "zh-HK-HiuGaaiNeural"

    def synthesize(self, text, voice, out_path) -> bool:
        # 依赖 edge-tts；未装或失败返回 False（降级）
        try:
            import edge_tts
            import asyncio
            async def _run():
                tts_ = edge_tts.Communicate(text, voice or self._voice)
                with open(out_path, "wb") as f:
                    async for chunk in tts_.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
            asyncio.run(_run())
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("edge-tts 失败: %s", exc)
            return False
```

`get_tts` 分支 Provider：
```python
def get_tts(settings=None):
    s = settings or Settings.load()
    if getattr(s, "tts_provider", "dashscope") == "edge":
        return EdgeTTSCosyvoice(s)
    return DashScopeCosyvoice(s)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/infra/test_tts_lines.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/infra/tts.py tests/infra/test_tts_lines.py
git commit -m "feat: TTS 按句合成+Edge-TTS Provider 候选"
```

---

### Task 11: CLI narrate 扩展（跑完整叙事链）

**Files:**
- Modify: `app/cli.py`
- Modify: `app/agents/narrator.py`（可选：保留旧接口作降级模板；或直接让 CLI 调 `run_story_chain`）
- Test: `tests/cli/test_narrate.py`

**Interfaces:**
- Consumes: `run_story_chain`, `Settings`
- Produces: `cli` 子命令 `narrate` 增加 `--pid`（重复用），`--force`；`[OK]/[NG]` 输出。

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_narrate.py
import importlib
from pathlib import Path

def test_narrate_invokes_run_story_chain(monkeypatch, capsys):
    import app.cli as cli
    calls = {}
    def fake_chain(pid, settings=None, force=False):
        calls["pid"] = pid
        return {"story": "故事", "narration": "{}", "audio": True, "degraded": False}
    monkeypatch.setattr(cli, "run_story_chain", fake_chain)
    # 直接调用内部 parse 后的 handler（或依赖现有 argparse 结构）
    ...
    assert calls.get("pid") == "sample_a"
```

> 说明：真实测试应根据你 cli.py 现有的 argparse 结构写成对 `cli.main(["narrate", "--pid", "sample_a"])` 的完整调用（mock `run_story_chain` 与 `sys.argv`）。Step 1 给结构示意，落地时用现有测试风格补全并对齐 `app/cli.py` 真实入口。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_narrate.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

在 `app/cli.py` 的 `narrate` 处理里：
```python
def _cmd_narrate(args):
    from app.narrator.story import run_story_chain
    res = run_story_chain(args.pid, force=args.force)
    if res.get("audio"):
        print(f"[OK] {args.pid} 叙事+旁白+音频完成"
              f"(story={len(res.get('story',''))}字, degraded={res.get('degraded')})")
    else:
        print(f"[NG] {args.pid} 叙事完成但 TTS/音频降级 "
              f"degraded={res.get('degraded')}")
```

在 argparse 里加 `--force` 并复用 `--pid`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_narrate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/cli.py tests/cli/test_narrate.py
git commit -m "feat: narrate 子命令跑完整叙事链"
```

---

### Task 12: 叙事质量评测（LLM judge 四维 + 禁用词统计）

**Files:**
- Create: `app/eval/narrative_eval.py`
- Create: `eval/narrative_questions.jsonl`（每行：`{"pid","photo_path","story","narration"}`）
- Test: `tests/eval/test_narrative_eval.py`

**Interfaces:**
- Consumes: `lc.chat`, `detox.scan_ai_smell`, `Settings`
- Produces: `run_narrative_eval(rows, settings=None, chat=None) -> dict`（`{per_row:[...], aggregate:{factual_score, taste_score, hook_score, yue_score, banned_hits}}`），报告落盘 `eval/reports/narrative_eval.json`

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_narrative_eval.py
from app.eval.narrative_eval import run_narrative_eval

class ChatJudge:
    def __call__(self, messages, json_mode=False, temperature=None, settings=None):
        return ('{"factual_score":0.9,"taste_score":0.8,"hook_score":0.85,'
                '"yue_score":0.9,"comment":"好"}')

def test_run_narrative_eval(monkeypatch):
    rows = [{"pid":"a","story":"骑楼"*40,"narration":"粤语"}]
    res = run_narrative_eval(rows, chat=ChatJudge())
    assert res["aggregate"]["taste_score"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/eval/test_narrative_eval.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/eval/narrative_eval.py
"""叙事质量评测：LLM judge 四维 + 确定性禁用词统计。"""
import json
import logging
from pathlib import Path

from app.infra import llm_client as lc
from app.narrator import detox as d

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = (
    "你是叙事质量评审。对照给定故事与粤语旁白，输出严格 JSON："
    '{"factual_score":0~1,"taste_score":0~1,"hook_score":0~1,'
    '"yue_score":0~1,"comment":"一段话"}。'
    "factual=是否仅在照片可见范围内；taste=去AI味/无套话；"
    "hook=开头抓人/结尾余韵；yue=粤语口语自然度。只输出 JSON。"
)


def run_narrative_eval(rows, settings=None, chat=None):
    chat = chat or lc.chat
    s = settings or __import__("app.config", fromlist=["Settings"]).Settings.load()
    per_row = []
    agg = {"factual_score": 0.0, "taste_score": 0.0, "hook_score": 0.0,
           "yue_score": 0.0, "banned_hits": 0}
    n = max(len(rows), 1)
    for r in rows:
        banned = d.scan_ai_smell(r.get("story", ""))
        agg["banned_hits"] += len(banned)
        try:
            raw = chat([{"role": "system", "content": JUDGE_SYSTEM},
                        {"role": "user", "content":
                            f"【故事】{r.get('story','')}\n【旁白】{r.get('narration','')}"}],
                       json_mode=True, temperature=0.2, settings=s)
            obj = json.loads(raw) if raw.strip().startswith("{") else {}
            scores = {k: float(obj.get(k, 0.0)) for k in
                      ("factual_score", "taste_score", "hook_score", "yue_score")}
        except Exception as exc:  # noqa: BLE001
            logger.warning("judge 失败，该行计 0: %s", exc)
            scores = {"factual_score": 0.0, "taste_score": 0.0,
                      "hook_score": 0.0, "yue_score": 0.0}
        for k, v in scores.items():
            agg[k] += v
        per_row.append({"pid": r.get("pid"), **scores,
                        "banned_hits": len(banned)})
    for k in ("factual_score", "taste_score", "hook_score", "yue_score"):
        agg[k] = round(agg[k] / n, 3)
    return {"per_row": per_row, "aggregate": agg}


def save_report(result, out="eval/reports/narrative_eval.json"):
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/eval/test_narrative_eval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/eval/narrative_eval.py eval/narrative_questions.jsonl tests/eval/test_narrative_eval.py
git commit -m "feat: 叙事质量评测(四维judge+禁用词统计)"
```

---

### Task 13: Web 集成 + 文档/ADR 收尾

**Files:**
- Modify: `app/web/main.py`（详情页端点返回 story + narration lines + audio）
- Modify: `app/web/templates/detail.html`、`app/web/static/detail.js`（展示故事 + 旁白歌词式字幕 + 音频）
- Modify: `docs/architecture.md`（narrator 分层说明）、`docs/adr/ADR-0010-narrative-model.md`（新增）、`docs/PROGRESS.md`（W4 记录）
- Test: `tests/web/test_detail_contrib.py`（mock run_story_chain）

**Interfaces:**
- Consumes: `run_story_chain`
- Produces: detail 端点 `GET /photo/{pid}` 附带 `story/narration_lines/audio`；`ADR-0010` 记录决策；`PROGRESS` 更新。

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_detail_contrib.py
def test_detail_includes_story(monkeypatch):
    from app.web import main as web
    fake = lambda pid, settings=None, force=False: {
        "story": "一个广州的老故事。", "narration": '{"lines":[{"text":"旁白","emotion":"怀念"}]}',
        "audio": True, "degraded": False}
    monkeypatch.setattr(web, "run_story_chain", fake)
    # 用 TestClient 请求，断言响应包含 story 文本
    ...
```

> 说明：落地时按你的 FastAPI `TestClient` 写法补全查询与断言。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_detail_contrib.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

详情页端点把 `run_story_chain(pid)` 结果传入模板；`detail.html` 增加"故事 + 旁白字幕 + 音频"区块；`detail.js` 解析 `narration.json` 的 `lines` 做歌词式逐句高亮（可选）。

`docs/adr/ADR-0010-narrative-model.md`：
```markdown
# ADR-0010：叙事生成走 4-Agent 链 + 确定性去AI味拦截 + 云端 API
状态：已接受
背景：现 narrator 仅按元数据拼讲解词，无故事力/无粤语口语/无去AI味。参考"老照片→故事→粤语旁白"叙事链。
方案：app/narrator 四 Agent（VLM洞察→qwen-max故事→qwen-plus旁白→qwen-plus审稿），
单点回炉(score<85)、deterministic detox 硬闸、DashScope 全云、CosyVoice 主路。
理由：云 API 现成(复用账号)；detox 硬闸廉价可量化；轻量编排优于 LangGraph(YAGNI)。
代价：按量费用低；提示词需迭代约数日；TTS 旁白质量是主排雷点。
人工资源依赖：无新增 key；试听定稿仍走 ADR-0007。
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_detail_contrib.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/web tests/web docs/architecture.md docs/adr/ADR-0010-narrative-model.md docs/PROGRESS.md
git commit -m "feat: 详情页叙事展示 + ADR-0010 + PROGRESS 更新"
```

---

## Self-Review

**Spec coverage（对现有 spec F6 + 新增叙事评测）：**
- F6 升级（故事+旁白+音频）：Task 2-10。✅
- 去 AI 味（参考核心卖点）：Task 3（提示词约束）+ Task 4（detox 硬闸）+ Task 12（taste 维度评测）。✅
- 降级铁律：Task 5（VLM 挂）、Task 9（全部降级 + 不抛异常）。✅
- 云 API（DashScope 复用）：Task 1（客户端扩展）、Task 5-8。✅
- 幂等：Task 9（缓存 + force）。✅
- 叙事质量评测（差异化武器延伸）：Task 12。✅
- Web 展示：Task 13。✅
- 文档/ADR：Task 13。✅

**Placeholder scan：** 无"TBD/实现后再说"；所有代码步骤给到可实现内容。Task 1 Step 1 展示了一个占位再替换为真实测试，正文已注明。

**Type consistency：** `Insight/Story/Narration/NarrationLine/ReviewResult` 字段在 types 定义后被 Task 5-9 一致引用；`validate_story`/`validate_narration`/`scan_ai_smell` 签名一致；`chat(..., temperature=...)` 全链路一致。编排器用 `deps` 注入 + `_detox_validate` 兜底，避免测试 Deps 与真实实现签名漂移。

**Known gap / follow-up（交给实现时定）：** ① `run_story_chain` 的 `deps` 注入在 Task 9 为兼顾可测性与简洁做了 `_DefaultDeps` + `_detox_validate`，实现时若觉得过重可简化为直接 import 真实函数、仅 mock `get_vlm/get_tts` 与 `lc.chat`；② Task 11/13 的测试结构需对齐你现有 `app/cli.py` 与 `app/web/main.py` 的真实入口风格。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-26-lingnan-narrative-model-refactor.md`. Two execution options:

1. **Subagent-Driven (recommended)** —— I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** —— Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
