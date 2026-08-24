# ADR-0007：粤语 TTS = Provider 接口 + 三路试听定稿（DashScope 复用优先）
状态：已接受（具体供应商 W3 前按试听结果在配置中定稿）
背景：口播环节需要粤语语音合成；用户已拍板云端 TTS 路线。云端各家粤音质量宣传不可信（2026 方言 TTS 选型共识：文档不算数，试听才算数）。
方案：定义 `TTSProvider` 接口（synthesize(text, voice) -> wav），三个实现候选：
1. DashScope cosyvoice —— 复用已有账号，**先实测是否支持粤语发音人/方言参数**
2. Azure Speech zh-HK（HiuMaanNeural 等）—— 稳定便宜，DashScope 不支持时注册兜底
3. 本地开源 ASLP-lab/Cosyvoice2-Yue 微调权重 —— 零 API 成本，仅作答辩彩蛋与最终保险，不进主链路
理由：接口 seam 化让"试听拍板"变成纯配置切换；复用现有账号是人工准备成本最低路径。
代价：多写一层薄接口（约半天）；试听需人参与 30 分钟。
人工资源依赖：人提供/认可一段 200 字粤语试听稿；对候选各生成一段样音盲选；若 DashScope 不支持则注册 Azure 取 key 写入 `.env`。验证命令：选定 provider 对试听稿产出可播放 wav。
