"""tests/infra 测试包。

加 __init__.py 使本目录成为包：避免与 tests/test_llm_client.py
同 basename 触发 pytest prepend 导入模式的 import file mismatch。
"""