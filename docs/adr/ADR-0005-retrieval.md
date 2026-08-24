# ADR-0005：向量检索沿用 Milvus + BGE-M3 + CLIP 双通道混合
状态：已接受
背景：需要"文搜图、图搜图、图文混检"三能力，且 DocMind 配方已验证。
方案：Milvus standalone（docker compose）单 collection `lingnan_photos`；BGE-M3 dense+sparse（COSINE 0.8 + IP 0.2，norm_score 归一）承担文本通道；**Chinese-CLIP ViT-B/16（OFA-Sys，512 维）承担图像通道——查询词为中文，OpenAI CLIP 中文文本塔弱，故选之**；两通道 RRF 融合后交 rerank。嵌入与 Milvus 连接全部单例化。
理由：三路召回+融合是 DocMind 已跑通的成熟模式；Chroma/Qdrant 无多模态稀疏向量对等能力，换库无收益。
代价：依赖 Docker Desktop 按需启动；CLIP 加载失败时降级纯文本通道（spec 已定义）。
人工资源依赖：用时启动 Docker Desktop；W1 核对 BGE-M3 权重本机缓存路径并写入配置。验证命令：`docker compose up -d milvus` 后 `pymilvus` 健康检查通过。
