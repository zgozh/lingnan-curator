# ADR-0002：老照片修复与上色走本地开源（CodeFormer + DDColor）
状态：已接受
背景：修复上色是展馆观感的第一印象，用户已拍板本地开源路线（零调用成本、可离线演示）。
方案：人脸修复用 CodeFormer（fidelity_weight≈0.7），上色主选 DDColor、DeOldify 兜底；两仓库以固定 commit vendor 到 `models/vendor/`，各自独立虚拟环境、以子进程调用。划痕极重的照片可选微软 Br-Photos 第三步，默认不做（YAGNI）。
理由：CodeFormer 对重度退化人脸效果上限高于 GFPGAN 且保真度可调；DDColor 较 DeOldify 色彩更自然且纯 torch 栈（DeOldify 依赖 fastai1 老栈，Windows 易翻车故只作兜底）。
代价：首次权重下载约 2.4GB；vendor 环境搭建是 W1 最大排雷点；上色环节失败时降级为"只交修复图"（spec 已定义）。
人工资源依赖：人无需操作，AI 提供下载脚本后台拉权重（HF_ENDPOINT 走 hf-mirror）。验证命令：权重目录非空 + 对 1 张样张产出 restored.jpg / colorized.jpg。
