# ADR-0010：叙事生成走 4-Agent 链 + 确定性去AI味拦截 + 云端 API
状态：已接受
背景：现 narrator 仅按元数据拼讲解词，无故事力/无粤语口语/无去AI味。参考"老照片→故事→粤语旁白"叙事链。
方案：app/narrator 四 Agent（VLM洞察→qwen-max故事→qwen-plus旁白→qwen-plus审稿），
单点回炉(score<85)、deterministic detox 硬闸、DashScope 全云、CosyVoice 主路。
理由：云 API 现成(复用账号)；detox 硬闸廉价可量化；轻量编排优于 LangGraph(YAGNI)。
代价：按量费用低；提示词需迭代约数日；TTS 旁白质量是主排雷点。
人工资源依赖：无新增 key；试听定稿仍走 ADR-0007。
