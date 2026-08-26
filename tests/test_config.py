"""Task 1 RED：配置从环境变量/.env 加载。"""
from pathlib import Path


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("MILVUS_URI", "http://127.0.0.1:19530")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    from app.config import Settings

    s = Settings.load(env_file=None)
    assert s.milvus_uri == "http://127.0.0.1:19530"
    assert s.collection == "lingnan_photos"
    assert s.dashscope_api_key == "sk-test"
    assert s.vlm_model == "qwen-vl-plus"


def test_settings_defaults_without_env(monkeypatch):
    monkeypatch.delenv("MILVUS_URI", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    from app.config import Settings

    s = Settings.load(env_file=None)
    assert s.milvus_uri == "http://127.0.0.1:19530"
    assert s.dashscope_api_key == ""


def test_models_step_status_and_report_json():
    import json
    from app.models import IngestReport, StepResult, StepStatus

    r = IngestReport(items=[StepResult(step="ocr", status=StepStatus.DEGRADED, detail="空结果")])
    data = json.loads(r.to_json())
    assert data["items"][0]["status"] == 2
    assert data["items"][0]["detail"] == "空结果"


_NARRATIVE_ENV = ("STORY_MODEL", "NARRATION_MODEL", "REVIEW_MODEL",
                  "INSIGHT_MODEL", "MAX_STORY_RETRY")


def test_narrative_settings_defaults_without_env(monkeypatch):
    for name in _NARRATIVE_ENV:
        monkeypatch.delenv(name, raising=False)
    from app.config import Settings

    s = Settings.load(env_file=None)
    assert s.story_model == "qwen-max"
    assert s.narration_model == "qwen-plus"
    assert s.review_model == "qwen-plus"
    assert s.insight_model == "qwen-vl-max"
    assert s.max_story_retry == 1


def test_narrative_settings_override_from_env(monkeypatch):
    monkeypatch.setenv("STORY_MODEL", "qwen-max-longcontext")
    monkeypatch.setenv("NARRATION_MODEL", "qwen-turbo")
    monkeypatch.setenv("REVIEW_MODEL", "qwen-turbo")
    monkeypatch.setenv("INSIGHT_MODEL", "qwen-vl-max-longcontext")
    monkeypatch.setenv("MAX_STORY_RETRY", "3")
    from app.config import Settings

    s = Settings.load(env_file=None)
    assert s.story_model == "qwen-max-longcontext"
    assert s.narration_model == "qwen-turbo"
    assert s.review_model == "qwen-turbo"
    assert s.insight_model == "qwen-vl-max-longcontext"
    assert s.max_story_retry == 3
