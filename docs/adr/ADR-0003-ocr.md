# ADR-0003：OCR 用 RapidOCR（PaddleOCR 为升级备选）
状态：已接受
背景：老照片上的招牌/题字是检索的补充信号源；spec 已将其定义为可降级项。
方案：RapidOCR（onnxruntime 后端，CPU 可用），默认中英模型起步，繁体场景实测后再决定是否换载 PP-OCR 系列繁体模型；若识别质量不足，升级路径=PaddleOCR 官方（接受 paddlepaddle 安装重量）。
理由：pip 即装、零 GPU 占用、与"OCR 只是锦上添花"的定位匹配；避免一开始就背上 paddlepaddle Windows 环境包袱。
代价：繁体艺术字识别率有限——预期管理：文本召回主力是 VLM caption + title + 元数据。
人工资源依赖：无。验证命令：`python -c "from rapidocr_onnxruntime import RapidOCR"` 并对一张含招牌样张输出 ocr.txt。
