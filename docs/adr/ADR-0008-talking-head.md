# ADR-0008：口型视频主选 SadTalker（EchoMimicV2 出局、LivePortrait 排除）
状态：已接受
背景：数字人环节的输入是"老照片 + 粤语音频"，输出口播视频；显存预算 RTX 4060 Laptop 8GB。
方案：SadTalker 以 vendor 固定 commit + 独立 Python 3.10 venv + 子进程方式接入 `app.narrator`；输入=上色后照片 + TTS wav，输出 mp4 挂详情页。
理由：2026-08-24 调研实证——EchoMimicV2 官方实测 GPU 为 A100(80G)/4090D(24G)/V100(16G)，≥16GB 门槛对本机出局（EchoMimicV3 刚发布生态尚嫩，列为观察项）；LivePortrait/FasterLivePortrait 是**视频驱动**，需要真人驱动视频，与本项目输入不匹配，排除；SadTalker 约 4~6GB 显存、Windows 部署资料最多。
代价：画质/分辨率一般（演示够用）；独立环境与 ffmpeg 是 W3 排雷点；失败时降级=详情页隐藏口播入口（spec 已定义）。
人工资源依赖：安装 ffmpeg 并入 PATH；AI 提供权重下载脚本（约 4GB）。验证命令：`ffmpeg -version` 成功 + 对一张样张+一段 wav 产出 mp4。
