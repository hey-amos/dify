# 本地模型配置与实测记录

初始记录日期：2026-11-14；Embedding 状态更新：2026-11-17。当前本地部署为 Dify `v1.19.0`、`langgenius/openai_api_compatible` 原版插件 `0.0.84`（插件 SDK `0.10.2`），连接现有的三套机房推理服务。

本文区分已保存在 Dify 的供应商参数、创建应用时需要选择的生成参数、以及尚未解决的机房服务问题。模型参数保存在 Dify 数据库中，不在 `docker/.env` 中；本文不保存登录密码或 API Key。三个模型原有的凭据名称、服务地址、API Key 和 endpoint 模型名称均保留。

## 当前结论

| 模型 | 已保存的主要调整 | 实测结论 |
| --- | --- | --- |
| Qwen3.8-27B | 上下文 262144、输出上限 16384；启用思考切换、工具调用、流式工具、视觉和结构化输出 | 两种思考模式及上述能力均通过；保存后关键能力复测通过 |
| Qwen3-Embedding-4B | 上下文 32768、每批 1 条（默认值）、float 编码、查询指令前缀 | 保存值与实际运行时均为每批 1 条；输出 2560 维，中英文检索正常 |
| Qwen3-Reranker-4B | 上下文改为服务端实际开放的 8192 | 接口可用，但正常请求的排序质量未通过；机房评分模板问题按用户要求暂缓处理 |

不能将三个模型统一设置为同一个上下文长度。真实接口的 `/v1/models` 返回值如下：

| Dify 模型名 | endpoint 模型名 | 服务公布的 `max_model_len` | Dify 配置值 |
| --- | --- | --- | --- |
| Qwen3.8-27B | `qwen3.8-27b` | 262144 | 262144 |
| Qwen3-Embedding-4B | `Qwen3-Embedding-4B` | 40960 | 32768 |
| Qwen3-Reranker-4B | `qwen3-reranker-4b` | 8192 | 8192 |

LLM 的值与 [Qwen3.8-27B 官方模型卡](https://huggingface.co/Qwen/Qwen3.8-27B#best-practices)的原生上下文一致。Embedding 按 [官方模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-4B#model-overview)的 32K 范围配置，不因端点接受更长输入就宣称超出该范围的效果已验证。Reranker 虽然模型本身支持 32K，当前端点只开放 8K。

## Qwen3.8-27B：供应商参数

在“集成 → 模型供应商 → OpenAI-API-compatible → 管理凭据”中已保存以下值：

| 配置 | 字段 | 当前值 |
| --- | --- | --- |
| 对话类型 | `mode` | `chat` |
| API 类型 | `api_type` | `chat_completions` |
| 模型上下文长度 | `context_size` | `262144` |
| 最大 token 上限 | `max_tokens_to_sample` | `16384` |
| 思考模式支持 | `agent_thought_support` | `supported`，支持思考与非思考两种模式 |
| 兼容模式 | `compatibility_mode` | `extended` |
| token 参数名 | `token_param_name` | `max_tokens` |
| 函数调用类型 | `function_calling_type` | `tool_call` |
| 流式函数调用 | `stream_function_calling` | `supported` |
| 视觉支持 | `vision_support` | `support` |
| 结构化输出 | `structured_output_support` | `supported` |
| 流式中包含用量 | `stream_include_usage` | `enabled`，保留原值 |

`extended` 是思考开关生效的必要条件：本版本插件在严格模式下不发送 vLLM 使用的 `chat_template_kwargs.enable_thinking`。实测关闭时没有思考内容，开启时有思考内容，两种模式都输出正确答案。

本版本“流式函数调用”的 `supported` 选项显示为“提示词模式（兼容）”；插件 SDK 用此值声明流式工具能力。本次已实际收到流式 `tool_calls`。不要因同一字段里出现“原生 JSON Schema”文案就改成 `native`。

本版本结构化输出的 `supported` 使用 JSON mode 加 schema 提示词约束；实测返回内容符合样例 schema，但不等同于服务端原生、严格的 JSON Schema 保证。音频、视频、原生文档及内置联网搜索继续关闭；本次仅验证了图片输入，没有验证这些额外能力。

页面已确认显示 `262K` 和 `VISION`；`262K` 是界面的缩写，实际保存的上下文值为 `262144`。

## 两套应用生成参数

这些值应在聊天应用、工作流 LLM 节点或 Agent 的模型参数中选择。供应商的输出上限只决定允许设置的最大值，并不把所有应用的 `max_tokens` 自动改为 16384；本次没有创建或修改用户应用。

| 参数 | 通用问答／知识库 | 复杂推理／Agent |
| --- | --- | --- |
| `enable_thinking` | `false` | `true` |
| `temperature` | `0.7` | `1.0` |
| `top_p` | `0.80` | `0.95` |
| `presence_penalty` | `1.5` | `0.0` |
| `frequency_penalty` | `0.0` | `0.0` |
| `reasoning_effort` | 不设置 | `medium` 起步；更复杂任务可单独评估 `xhigh` |
| `max_tokens` | `4096` 起步；简短回答可降到 `1024–2048` | `8192` 起步；长推理或复杂工具任务可增至 `16384` |
| `response_format` | 普通回答用 `text`；按应用需要开启 JSON | 普通回答用 `text`；按应用需要开启 JSON |

采样参数来自 [Qwen 官方最佳实践](https://huggingface.co/Qwen/Qwen3.8-27B#best-practices)；输出预算是本地使用的起始建议，不是模型的理论上限。`medium` 已实测，`xhigh` 本次未测。开启思考后，输出预算还要容纳推理内容。

官方另建议两种模式都使用 `top_k=20`、`min_p=0.0`、`repetition_penalty=1.0`。当前插件没有提供这三个应用参数的表单入口，本次未将其保存为 Dify 参数，也未核实机房服务的默认采样值；需在推理服务侧单独核对。

## Qwen3-Embedding-4B：供应商参数

| 配置 | 字段 | 当前值 |
| --- | --- | --- |
| 模型上下文长度 | `context_size` | `32768` |
| 每次请求的最大文本数量 | `max_chunks` | `1`（原版默认值） |
| 编码格式 | `encoding_format` | `float` |
| 视觉支持 | `vision_support` | `no_support` |
| 文档前缀 | `document_prefix` | 留空；服务端可能省略此可选字段 |
| 查询前缀 | `query_prefix` | 下面的两行内容，包含真实换行 |

```text
Instruct: Retrieve the passage that best answers the question.
Query:
```

查询加任务指令、文档保持原文，依据 [Qwen Embedding 的用法和说明](https://huggingface.co/Qwen/Qwen3-Embedding-4B#usage)。插件在查询模式下添加前缀，在文档模式下使用独立的文档前缀，不要把指令重复添加到所有知识库段落。

实测输出为 **2560 维**，样例向量的 L2 范数约为 1。当前插件没有维度设置字段，因此没有在 Dify 中额外配置 `dimensions`；保持端点现有输出即可。以后若改变维度，需要同步处理已有知识库向量索引。

批量使用原版默认值 `1`，已保存的 `max_chunks` 与实际运行时一致，不使用本地批量补丁。每次请求处理一段文本；多个输入会分批处理并返回全部向量。

## Qwen3-Reranker-4B：配置与待处理问题

已将 `context_size` 从 `4096` 改为 `8192`，保留文本模式 `vision_support=no_support`。原有 `/v1` 地址、endpoint 模型名及密钥不变。这里的长度要容纳查询、文档和评分模板，不能全部当作单段正文预算。

**当前不建议把该服务作为知识库的可靠重排环节，待机房评分模板修复并复测后再使用。** 模型本身未被删除或停用，已有默认模型选择未改动。用户暂时没有机房启动配置，已明确要求先记录问题。

### 已观察到的异常

实测通过 Dify 插件调用和直接调用模型 `/v1/rerank` 都能返回 HTTP 200；问题在评分结果，而非图标、连通性或 Dify 展示。

使用 6 段合成文档、3 个中英文查询时，普通输入有 1 个查询的首位结果错误。例如查询“安装插件需要什么目录权限”的英文版本：

| 文档 | 普通输入得分 | 按官方评分格式构造输入后的对照得分 |
| --- | --- | --- |
| 正确：插件目录需要用户／组 1001 的写权限 | 0.886736，排名第 2 | 0.999728，排名第 1 |
| 无关：介绍 reranker 的用途 | 0.963666，排名第 1 | 0.000060 |

对照请求按 [vLLM 0.17.1 官方评分模板](https://github.com/vllm-project/vllm/blob/v0.17.1/examples/pooling/score/template/qwen3_reranker.jinja)构造测试文本后，三个查询均将正确段落排在首位。这是诊断实验，不是已经部署到 Dify 或机房的修复。

该端点 `/version` 返回 **vLLM 0.17.1**；其公开 `RerankRequest` schema 不包含 `chat_template` 参数。现象强烈指向评分模板缺失或未生效，但尚未读取机房启动命令，不能断言具体哪个启动参数缺失。上游也记录过[未启用 Qwen3 评分模板导致无关文本得分过高的问题](https://github.com/vllm-project/vllm/issues/55501)。

### 后续处理

拿到机房配置后，对照 [vLLM 0.17.1 的 Qwen3 Reranker 示例](https://docs.vllm.ai/en/v0.17.1/examples/pooling/score/#qwen3-reranker-online)核查：

- 启用与该版本匹配的 `qwen3_reranker.jinja`，通过 `--chat-template` 指向机房实际可读的文件。
- 对原始 Qwen3 Reranker 权重，核对 `--hf-overrides` 中的 `architectures=["Qwen3ForSequenceClassification"]`、`classifier_from_token=["no","yes"]` 和 `is_original_qwen3_reranker=true`。
- 保留既有模型目录、端口、鉴权和资源参数；本次没有远程修改、重启或升级该服务。
- 修复后用普通 query/doc 输入重测上述中英文样例，再用业务标注样例评估。不要将诊断用的完整评分提示词手工塞进正式知识库文本。

复测通过后，可先用 `top_n=3–5`、关闭分数阈值作为业务调试起点，再按实际召回样例调整。这两个参数属于知识库／检索调用，不是供应商凭据中的配置项。当前异常分数不适合用来选择统一阈值。

## 测试范围与结果

测试使用合成内容。能力与兼容性检查经运行中的 Dify API → 插件 → 已有模型端点调用；Reranker 异常另通过直接调用端点复现，并进行评分格式对照。没有创建测试应用或知识库，也没有使用用户业务文档。

2026-11-17 的[原始复测记录](../artifacts/model-validation-2026-11-17/summary.json)保留了当时 Embedding“保存值 16、运行值 1”的结果，属于恢复默认配置前的快照。后续已将保存值调整为原版默认的 `1`；当前配置以前文为准，历史测试结果不改写为通过。

| 检查 | 结果 |
| --- | --- |
| 非思考模式算术 | 回答 `126`，没有思考内容 |
| 思考模式，`reasoning_effort=medium` | 回答 `126`，有思考内容 |
| 流式文本和 usage | 收到完整文本和用量信息 |
| 普通及流式工具调用 | 均返回 `add_numbers`，参数为 `17` 和 `25`；没有执行外部工具 |
| JSON 结构化样例 | 返回符合样例 schema 的对象 |
| 图片输入 | 正确识别合成红色图片 |
| 超过旧 4K 限制的输入 | 实际 prompt 7537 tokens，正确提取末尾校验码 |
| Embedding 中英文检索 | 6 段文档、3 个查询，正确段落均排第 1 |
| Embedding 批量 | 保存值与原版实际行为均为每批 1 条；17 条输入检查全部返回 2560 维向量 |
| Reranker 普通输入 | 3 个查询中 1 个首位排序错误；保留为待解决问题 |
| Reranker 评分格式对照 | 3 个查询的正确段落均排第 1，未部署该诊断方式 |
| 保存后复测 | 直接读取数据库中的配置，再次通过两种思考模式、流式工具、JSON 和向量检索检查 |

这些是小规模能力及兼容性检查，不代表业务准确率、满上下文性能或并发容量已经验证。没有发送 262K 的 LLM 输入或 32K 的 Embedding 输入来做极限测试。

## 维护与回退

后续变更前先读 [AGENTS.md](AGENTS.md) 和 [LOCAL_CHANGES.md](LOCAL_CHANGES.md)。插件升级或更换机房模型端点后，重新核对字段含义、服务端上限以及真实调用结果。

本次调整前，三个模型的上下文均为 `4096`；LLM 输出上限为 `4096`、兼容模式为 `strict`、token 参数名为 `auto`，思考／工具／流式工具／视觉／结构化输出能力均未启用；Embedding 每批 `1` 条、编码格式 `not_set`、查询和文档均无前缀。需要回退时可在同一凭据中恢复这些非敏感字段，保留原有地址与 API Key。
