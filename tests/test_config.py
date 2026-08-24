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
