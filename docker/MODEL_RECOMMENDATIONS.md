# Dify 1.20.0 模型推荐配置与验证记录

以下是本项目三个模型的推荐起始值，字段已按本实例的供应商插件 `0.0.84` 核对。在 Dify 控制台的「模型供应商」中选择 `OpenAI-API-compatible`。`endpoint_model_name` 按推理服务公布的模型 ID 填写，注意大小写。上下文长度和输出上限分别取建议值与端点实际支持值中的较小值。端点地址和 API Key 在供应商凭据中管理。[插件配置字段](https://github.com/langgenius/dify-official-plugins/blob/main/models/openai_api_compatible/provider/openai_api_compatible.yaml)

## Qwen3.8-27B 的供应商配置

选择语言模型（LLM），端点模型名示例为 `qwen3.8-27b`。

| 配置 | 插件字段 | 推荐值 |
| --- | --- | --- |
| 对话类型 | `mode` | `chat` |
| API 类型 | `api_type` | `chat_completions` |
| 上下文长度 | `context_size` | `262144` |
| 最大输出 token 上限 | `max_tokens_to_sample` | `16384` |
| 思考模式支持 | `agent_thought_support` | `supported` |
| 兼容模式 | `compatibility_mode` | `extended` |
| token 参数名 | `token_param_name` | `max_tokens` |
| 函数调用类型 | `function_calling_type` | `tool_call` |
| 流式函数调用 | `stream_function_calling` | `supported` |
| 视觉支持 | `vision_support` | `support` |
| 结构化输出 | `structured_output_support` | `supported` |
| 流式返回用量 | `stream_include_usage` | `enabled` |

`agent_thought_support=supported` 使应用可以切换思考模式，`compatibility_mode=extended` 允许插件向 vLLM 传递 `chat_template_kwargs.enable_thinking`。流式函数调用的 `supported` 在表单中可能显示为「提示词模式（兼容）」。应用依赖结构化输出时，按所需的 JSON schema 校验返回对象。本方案将音频、视频、原生文档输入和内置联网搜索设为关闭。[插件 LLM 实现](https://github.com/langgenius/dify-official-plugins/blob/main/models/openai_api_compatible/models/llm/llm.py)

### 两套应用生成参数

在聊天应用、工作流 LLM 节点或 Agent 中选择对应的一列。供应商的 `max_tokens_to_sample` 限定可选上限，每次调用的输出预算由应用的 `max_tokens` 决定。开启思考时，预算也要容纳推理内容。

| 参数 | 通用问答／知识库 | 复杂推理／Agent |
| --- | --- | --- |
| `enable_thinking` | `false` | `true` |
| `temperature` | `0.7` | `1.0` |
| `top_p` | `0.80` | `0.95` |
| `presence_penalty` | `1.5` | `0.0` |
| `frequency_penalty` | `0.0` | `0.0` |
| `reasoning_effort` | 留空 | 从 `medium` 起步，更复杂的任务可评估 `xhigh` |
| `max_tokens` | 从 `4096` 起步，简短回答可用 `1024–2048` | 从 `8192` 起步，长任务按需增至 `16384` |
| `response_format` | `text`，需要 JSON 对象时选 `json_object` | `text`，需要 JSON 对象时选 `json_object` |

两种模式的 `temperature`、`top_p` 和 `presence_penalty` 采用 Qwen 推荐值。两者也都推荐 `top_k=20`、`min_p=0.0`、`repetition_penalty=1.0`。若插件表单未提供这三个字段，可在推理服务侧核对。输出预算是本项目的起始建议。[Qwen3.8-27B 官方参数建议](https://huggingface.co/Qwen/Qwen3.8-27B#best-practices)

## Qwen3-Embedding-4B 的供应商配置

选择文本向量模型（Text Embedding），端点模型名示例为 `Qwen3-Embedding-4B`。

| 配置 | 插件字段 | 推荐值 |
| --- | --- | --- |
| 上下文长度 | `context_size` | `32768` |
| 每批输入文本数 | `max_chunks` | `1` |
| 编码格式 | `encoding_format` | `float` |
| 视觉支持 | `vision_support` | `no_support` |
| 文档前缀 | `document_prefix` | 留空，按原文编码 |
| 查询前缀 | `query_prefix` | 在控制台填一行 `Instruct: Retrieve the passage that best answers the question. Query:` |

Dify 1.20.0 控制台将插件的 `query_prefix` 显示为单行输入框。按上表填写时，用一个空格分隔指令和 `Query:`。插件会在前缀与实际问题之间补一个空格，输入框里的字面量 `\n` 会按原样发送。[模型配置表单](../web/app/components/header/account-setting/model-provider-page/model-modal/Form.tsx)

Qwen 模型卡在指令和 `Query:` 之间使用真实换行。通过 Dify 的模型凭据 API 配置时，可用 JSON 字符串里的 `\n` 表示换行，解码后的前缀如下。[模型凭据 API](../api/controllers/console/workspace/models.py) · [Qwen 官方查询示例](https://huggingface.co/Qwen/Qwen3-Embedding-4B#transformers-usage)

```text
Instruct: Retrieve the passage that best answers the question.
Query:
```

查询带上检索指令，文档保留原文。维度沿用端点输出，该模型最高支持 `2560` 维。连接已有知识库时，先核对实际返回维度与向量索引的维度一致。更改查询前缀后，用相同问题复查目标分段的排名。[Qwen3-Embedding-4B 模型卡与用法](https://huggingface.co/Qwen/Qwen3-Embedding-4B#model-overview)

## Qwen3-Reranker-4B 的供应商配置

选择重排模型（Rerank），端点模型名示例为 `qwen3-reranker-4b`。

| 配置 | 插件字段 | 推荐值 |
| --- | --- | --- |
| 上下文长度 | `context_size` | `8192`，按端点实际开放的上限核对 |
| 视觉支持 | `vision_support` | `no_support`，使用文本输入 |

`8192` 是本项目的配置起点。计算长度时要计入查询、候选文档和评分模板。使用 vLLM 部署时，核对服务所用的 Qwen3 重排评分模板。[Qwen3-Reranker-4B 模型卡](https://huggingface.co/Qwen/Qwen3-Reranker-4B) · [vLLM 评分模板](https://github.com/vllm-project/vllm/blob/main/examples/pooling/score/template/qwen3_reranker.jinja)

用于知识库前，先用已知相关和无关的段落核对实际排名。排序符合预期后，将检索返回数量设为 `3–5` 作为起点（重排调用的 `top_n`），先关闭分数阈值，再按业务样例调整。

## 1.20.0 实测记录

2026-11-23 在 OrbStack 的 Dify `1.20.0` 实例验证，实际供应商插件为 `langgenius/openai_api_compatible:0.0.84`。

| 实际模型 | 调用与结果 |
| --- | --- |
| `Qwen3.8-27B` | 已发布 Chatflow 的「理解问题与学部」节点使用 `temperature=0`、`max_tokens=1024`，「依据原文回答」节点使用 `temperature=0.2`、`max_tokens=2000`，两者均关闭思考。两次 LLM 调用均成功，分别使用 1956 和 1842 个 token，流式回答与知识库原文一致。 |
| `Qwen3-Embedding-4B` | 同一次提问触发一次查询向量调用，插件返回 HTTP 200。现有 Weaviate 索引的向量维度为 2560，混合检索返回 5 个分段，预期分段排第 1。 |
| `Qwen3-Reranker-4B` | 已发布流程只检索一个知识库，该库使用加权评分。另通过 Dify 的模型供应商对 3 段文本进行两次实际重排，`top_n=3`。将相关段落分别放在输入的第 2 和第 3 位，两次均排第 1，得分分别约为 0.7565 和 0.7562。 |

### 调整配置后的复查项目

| 类型 | 核对项目 | 验证方式 |
| --- | --- | --- |
| 语言模型（LLM） | 上下文长度、输出上限及应用使用的生成参数 | 发起一次对话，按应用实际使用的能力检查流式输出、工具调用或结构化输出 |
| 文本向量（Embedding） | 输入长度、批量大小、向量维度及查询前缀 | 对一组查询和文档生成向量，记录实际维度和目标文档的检索排名 |
| 重排（Reranker） | 输入长度及检索调用指定的返回数量 | 使用已知相关性的候选文档，记录预期首选文档和实际排名 |
