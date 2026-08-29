# nanobot-rebuild

一个从零实现的轻量级异步 Agent Runtime。项目不依赖 LangChain / LangGraph
替代核心执行流程，目标是让 Agent Loop、Tool Calling、Context、Memory、RAG、
MCP、安全、可观测与评测等工程边界保持可运行、可测试、可观察、可解释。

## 当前 Runtime

```text
User -> AgentLoop -> Session -> AgentRunner -> ContextBuilder
     -> LLMProvider -> ToolRegistry -> BaseTool -> ToolResult -> LLM
```

已有能力包括异步 Agent Runtime、并发 Tool Call、Pydantic 参数校验、
OpenAI-Compatible/Fake Provider、Session 持久化、Long-term Memory、
Context Token Budget、Skills 渐进加载和 commit-on-success。

## 环境与测试

要求 Python 3.11+。

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

## J1 RAG 开发进度

### 检查点 1：Document / Loader / TokenChunker（已完成）

- `Document`、`Chunk`、`RetrievedChunk` 严格数据模型
- TXT 与 Markdown 异步加载
- knowledge root 边界、目录逃逸、空文件与 UTF-8 校验
- 基于相对来源和内容生成稳定 Document ID
- 使用 `tiktoken` 的 Token 窗口切分与 overlap
- Chunk 保留 `source`、`document_id`、`chunk_id`、Token 区间

运行摄取示例：

```powershell
python examples/j1_ingestion_demo.py
```

该检查点只负责可靠摄取，不代表 J1 已经完成。

### 检查点 2：Embedding Provider（已完成）

- `EmbeddingProvider` 异步抽象
- `EmbeddingSpace(provider, model, dimension)` 兼容性约束
- 无网络、确定性的 `FakeEmbeddingProvider`
- 支持批处理的 `OpenAICompatibleEmbeddingProvider`
- API 返回数量、顺序、维度和有限数值校验
- Document 与 Query 共用同一 Embedding Space

运行 Embedding 示例：

```powershell
$env:PYTHONIOENCODING="utf-8"
python examples/j1_embedding_demo.py
```

真实 Provider 使用以下环境变量：

```text
EMBEDDING_API_KEY       # 未配置时回退到 LLM_API_KEY
EMBEDDING_BASE_URL      # 未配置时回退到 LLM_BASE_URL
EMBEDDING_MODEL
EMBEDDING_DIMENSION
EMBEDDING_BATCH_SIZE    # 默认 64
EMBEDDING_SEND_DIMENSIONS  # true 时把 dimensions 发送给兼容 API
```

`EMBEDDING_DIMENSION` 是运行时预期维度；Provider 会拒绝维度不匹配的响应。
默认不发送 `dimensions` 参数，以兼容不支持维度裁剪的 Embedding 服务。

### 检查点 3：索引生命周期与资源治理（已完成）

- brute-force cosine `InMemoryVectorIndex`
- Top-K 排名、维度校验、零向量与非法数值检查
- JSON 持久化与临时文件原子替换
- 按 source 增量更新、未变化文档跳过 Embedding、已删除文件清理
- Embedding Space / Index Schema 不兼容检测
- 显式全量重新 Embedding 迁移
- 文件大小、文档数、Chunk 数、Token 与可配置成本预算

### 检查点 4：Hybrid Retrieval 与 Citation（已完成）

```text
Query
 ├─ Query Embedding -> Vector Top-K
 └─ Tokenize -> BM25 Top-K
              ↓
       Reciprocal Rank Fusion
              ↓
          NoOpReranker
              ↓
 Structured Evidence + Citation Identity
```

BM25 保留错误码、函数名、产品型号等完整英文术语，并为中文建立按字召回路径。
Vector 与 BM25 的不同分数尺度不直接相加，而是通过 RRF 排名融合。

### 检查点 5：Agent Tool 接入（已完成）

`retrieve_knowledge` 已按普通 `BaseTool` 注册到 `ToolRegistry`。CLI 默认使用
Fake Embedding 以便离线运行；设置 `--embedding-provider openai` 可切换真实服务。

端到端离线实验：

```powershell
$env:PYTHONIOENCODING="utf-8"
python examples/j1_rag_agent_demo.py
```

真实 Embedding 冒烟实验：

```powershell
$env:EMBEDDING_API_KEY="..."
$env:EMBEDDING_BASE_URL="..."       # 官方服务可省略
$env:EMBEDDING_MODEL="..."
$env:EMBEDDING_DIMENSION="..."
python examples/j1_real_embedding_check.py
python -m pytest -m integration -q
```

没有真实凭据时，integration 测试会明确显示 skipped，不会偷偷访问网络。

### Embedding Runtime 工程能力

OpenAI-Compatible Embedding 路径已增加：

- `asyncio.timeout` 单批超时
- `Semaphore` 并发限制
- 只对连接、限流、服务端和超时等暂时性错误重试
- 指数退避与取消传播
- 不记录正文的 batch trace
- estimated/API usage tokens、latency、attempts、error type

### 当前明确边界

- Fake Embedding 是流程测试替身，不是语义模型。
- 内置向量搜索为 O(N) brute-force，适合教学、小型知识库和确定性测试；大规模数据应实现 FAISS 等 ANN Adapter。
- 内置 Reranker 当前为 NoOp 接口，没有引入 Cross-Encoder 或 LLM 调用。
- JSON 索引适合单进程运行，不提供多进程事务、分布式锁或高可用。
- 真实 API 实验需要用户提供服务地址、模型、维度与密钥；密钥不会写入代码、索引或 Trace。

## 原工程局限处理状态

| 原局限 | 当前处理 |
|---|---|
| Fake Embedding 不能替代语义模型 | 保留 Fake 作为测试替身，同时提供真实 OpenAI-Compatible Provider、冒烟脚本和 opt-in integration test |
| 无 Vector Top-K | 已实现余弦 brute-force Top-K 与确定性排序 |
| 无持久化、增量更新和删除 | 已实现 JSON 持久化、原子替换、按来源增量更新、未变化跳过和删除传播 |
| Embedding 无超时、重试、并发限制 | 已实现 timeout、可恢复错误重试、指数退避、Semaphore 和失败时同批任务取消 |
| 无真实 Provider 实验 | 已提供真实实验入口；没有用户凭据时测试明确 skipped |
| 无 Token、Latency、Batch Trace | 已实现不包含正文的 Embedding Batch Trace 与汇总 |
| 无 BM25、RRF、Reranker、Citation | 已实现两路召回、RRF、NoOpReranker 接口和结构化 Evidence |
| RAG 未接入 ToolRegistry | 已实现并注册 `retrieve_knowledge`，且有 AgentRunner 端到端测试 |
| 无模型升级迁移 | 持久化 Embedding Space；不匹配时拒绝启动或显式重新 Embedding |
| 无压力测试和成本控制 | 已增加 1000 条向量压力测试及文件、文档、Chunk、Token、批量和可配置成本预算 |
