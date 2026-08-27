# ADR-0011 老照片修复/上色的云端增强路线（万相 wanx2.1-imageedit）

日期：2026-08-26　状态：已采纳

## 背景
本地链路 CodeFormer(仅人脸修复) + DDColor(上色) 不处理划痕/折痕/霉斑，
且受限于 4060 显存的输出分辨率。考察三条升级路径：
1. 云端万相 2.1 通用图像编辑（DashScope，0.14 元/张，复用现有 key）
2. 本地 Real-ESRGAN 超分后处理
3. 微软 Bringing-Old-Photos-Back-to-Life（环境脆、老仓库）

## 决策
采用 **路线 1（P2b）** 为默认增强：`app/ingest/cloud_refine.py` 封装异步任务
（POST 下发 → /tasks/{id} 轮询 → 结果下载落盘），CLI `python -m app.cli refine`。
两条硬规则：
- **保真红线**：超分 `super_resolution` 可批量自动跑；指令修复
  `description_edit` 因扩散模型可能幻改人脸/文字细节，**只产出副产物
  repaired.jpg 供人工逐张比对采纳**，绝不覆盖 restored/colorized 主产物。
- **降级铁律**：缺 key/尺寸越界 [512,4096]px/接口失败/超时 一律返回 False，
  上层继续用本地产物；函数签名提供 http 注入 seam 供 mock 测试。

## 后果
- 正面：零新依赖（httpx/PIL 已有）、复用 DASHSCOPE_API_KEY（无 .env 变更）；
  批量 24 张 SR ≈3.4 元。
- 负面：输出依赖外网与配额；结果 URL 24h 有效须即时落盘（已实现）。
- 备选：Real-ESRGAN 保留为断网兜底方案（未引入，YAGNI）。

## 增补（2026-08-27，批量人像翻车教训）
E2 链（纯上色 + YCbCr 亮度合成）虽在数学上保证不变脸，但**色度层仍可能
让肤色/整体观感不自然**——尤其原 DDColor 效果本就不错的照片，替换后反而
变差。用户实测后叫停批量。新政策：
1. **enhance 一律按张人工审后启用，禁止 --all 批量替全站换图**；
   CLI 的 `--all` 仅作为候选生成器（产物先落 `enhanced-archive/` 待审）。
2. 展示优先级机制保留（enhanced > colorized > restored），单张想启用就是把
   文件放回 `data/processed/{pid}/enhanced.jpg`，撤下即移入 enhanced-archive。
3. 底线共识：原管线效果已可用的照片不动；增强只服务「原图明显差」的个案。
