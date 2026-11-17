"""Run inside the existing Dify API container; emit only sanitized JSON records.

Uses saved model credentials and synthetic inputs. Does not create applications,
datasets, or change model/server configuration. Tool calls are inspected, not run.
"""

import base64
import hashlib
import json
import logging
import math
import re
import signal
import struct
import sys
import time
import zlib
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

logging.disable(logging.CRITICAL)

import httpx
from sqlalchemy import select

from app_factory import create_app
from core.entities.embedding_type import EmbeddingInputType
from core.model_manager import ModelManager
from extensions.ext_database import db
from graphon.model_runtime.entities.message_entities import (
    ImagePromptMessageContent,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from graphon.model_runtime.entities.model_entities import ModelType
from models.account import Account, TenantAccountJoin
from models.provider import ProviderModelCredential

PROVIDER = "langgenius/openai_api_compatible/openai_api_compatible"
MODEL_NAMES = ["Qwen3.8-27B", "Qwen3-Embedding-4B", "Qwen3-Reranker-4B"]
TEMPLATE_URL = "https://raw.githubusercontent.com/vllm-project/vllm/v0.17.1/examples/pooling/score/template/qwen3_reranker.jinja"
DOCS = [
    "Dify 安装插件时，插件存储目录必须允许 UID 1001、GID 1001 的进程读写。只修复 API 存储目录的权限并不能保证插件目录可写。",
    "Qwen3-Embedding-4B 将文本转换为用于知识库语义检索的向量。本测试服务输出 2560 维向量；查询可带任务指令，文档保持原文。",
    "Reranker 用于对检索出的候选文档重新评分排序，帮助把与问题相关的段落排到前面。它不是生成回答的聊天模型。",
    "Dify Web 在容器内监听 0.0.0.0:3000，经 Nginx 代理后，本机浏览器使用 http://localhost:18080 访问。",
    "SQLite 是嵌入式关系数据库，通常将数据保存在单个文件中，适用于本地应用。",
    "冲泡茶叶时可根据茶叶种类选择水温和浸泡时间，时间过长可能使茶汤苦涩。",
]
QUERIES = [
    {"id": "plugin_permissions_zh", "text": "安装 Dify 插件需要什么目录权限？", "expected": 0},
    {"id": "plugin_permissions_en", "text": "What filesystem permissions are required to install Dify plugins?", "expected": 0},
    {"id": "embedding_zh", "text": "知识库语义检索应如何把文本转成向量，向量有多少维？", "expected": 1},
]
REDACTIONS = []
RESULTS = []


def emit(record):
    RESULTS.append(record)
    print("MODEL_CHECK " + json.dumps(record, ensure_ascii=False), flush=True)


def sanitized_error(error):
    text = str(error)
    for secret in REDACTIONS:
        if secret:
            text = text.replace(secret, "[redacted]")
    return re.sub(r"https?://[^\s\"']+", "[endpoint]", text)[:1000]


def timed_out(signum, frame):
    raise TimeoutError("test exceeded 150 seconds")


def run_test(name, operation):
    start = time.monotonic()
    emit({"event": "test_started", "test": name})
    signal.alarm(150)
    try:
        evidence = operation()
        record = {"event": "test_result", "test": name, **evidence}
    except Exception as error:
        record = {"event": "test_result", "test": name, "passed": False,
                  "error_type": type(error).__name__, "error": sanitized_error(error)}
    finally:
        signal.alarm(0)
    record["seconds"] = round(time.monotonic() - start, 3)
    emit(record)
    return record


def text_content(message):
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(getattr(part, "data", "") for part in content or [])


def answer_and_reasoning(text, separate_reasoning=None):
    thinking = re.findall(r"<think>(.*?)</think>", text, flags=re.S)
    answer = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    return answer, sum(len(part.strip()) for part in thinking) + len(separate_reasoning or "")


def usage_summary(usage):
    data = usage.model_dump(mode="json") if usage else {}
    return {key: data.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


def cosine(left, right):
    assert len(left) == len(right) and left
    return sum(a * b for a, b in zip(left, right, strict=True)) / math.sqrt(
        sum(a * a for a in left) * sum(b * b for b in right)
    )


def ranked(scores):
    return [{"index": index, "score": round(float(score), 8)}
            for index, score in sorted(enumerate(scores), key=lambda item: item[1], reverse=True)]


def direct_request(model, method, path, payload=None, absolute=False):
    credentials = model.credentials
    url = path if absolute else credentials["endpoint_url"].rstrip("/") + path
    headers = {"Authorization": "Bearer " + credentials["api_key"]} if credentials.get("api_key") else {}
    with httpx.Client(timeout=60, trust_env=False, headers=headers) as client:
        response = client.request(method, url, json=payload)
        response.raise_for_status()
        return response.status_code, response.json()


def config_fingerprint(tenant_id):
    rows = db.session.execute(select(ProviderModelCredential.id, ProviderModelCredential.encrypted_config)
        .where(ProviderModelCredential.tenant_id == tenant_id,
               ProviderModelCredential.model_name.in_(MODEL_NAMES))).all()
    return hashlib.sha256(json.dumps(sorted(tuple(row) for row in rows)).encode()).hexdigest()


def simple_llm(llm, thinking=False, stream=False):
    params = {"enable_thinking": thinking, "temperature": 1.0 if thinking else 0.7,
              "top_p": 0.95 if thinking else 0.8, "presence_penalty": 0.0 if thinking else 1.5,
              "frequency_penalty": 0.0, "max_tokens": 8192 if thinking else 4096}
    if thinking:
        params["reasoning_effort"] = "medium"
    result = llm.invoke_llm(
        [UserPromptMessage(content="计算 21 × 6，最终回答只给出结果数字。")],
        model_parameters=params, stream=stream,
    )
    if not stream:
        answer, reasoning_chars = answer_and_reasoning(text_content(result.message), result.reasoning_content)
        return {"passed": answer == "126" and (reasoning_chars > 0) == thinking,
                "answer": answer, "reasoning_chars": reasoning_chars, "usage": usage_summary(result.usage)}
    texts, chunks, usage, finish = [], 0, None, None
    for chunk in result:
        chunks += 1
        texts.append(text_content(chunk.delta.message))
        usage = chunk.delta.usage or usage
        finish = chunk.delta.finish_reason or finish
    answer, reasoning_chars = answer_and_reasoning("".join(texts))
    summary = usage_summary(usage)
    return {"passed": answer == "126" and chunks > 1 and bool(summary.get("total_tokens")),
            "answer": answer, "chunks": chunks, "finish_reason": finish,
            "reasoning_chars": reasoning_chars, "usage": summary}


def tool_test(llm, stream):
    tool = PromptMessageTool(name="add_numbers", description="Add two integers.", parameters={
        "type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"], "additionalProperties": False,
    })
    result = llm.invoke_llm(
        [SystemPromptMessage(content="You must use the add_numbers tool to perform addition. Do not calculate it yourself."),
         UserPromptMessage(content="Add 17 and 25 using add_numbers.")],
        model_parameters={"enable_thinking": False, "temperature": 0.7, "max_tokens": 1024},
        tools=[tool], stream=stream,
    )
    calls, chunks, usage = [], 0, None
    if stream:
        assembled = {}
        for chunk in result:
            chunks += 1
            usage = chunk.delta.usage or usage
            for call in chunk.delta.message.tool_calls:
                data = call.model_dump(mode="json")
                key = data.get("index", 0)
                item = assembled.setdefault(key, {"name": "", "arguments": ""})
                function = data.get("function", {})
                if function.get("name") and function["name"] != item["name"]:
                    item["name"] += function["name"]
                item["arguments"] += function.get("arguments") or ""
        calls = list(assembled.values())
    else:
        usage = result.usage
        calls = [{"name": call.function.name, "arguments": call.function.arguments}
                 for call in result.message.tool_calls]
    for call in calls:
        call["arguments"] = json.loads(call["arguments"])
    return {"passed": len(calls) == 1 and calls[0] == {"name": "add_numbers", "arguments": {"a": 17, "b": 25}},
            "tool_calls": calls, "stream_chunks": chunks, "usage": usage_summary(usage), "tools_executed": False}


def json_test(llm):
    schema = {"type": "object", "properties": {"city": {"type": "string"}, "sum": {"type": "integer"}},
              "required": ["city", "sum"], "additionalProperties": False}
    result = llm.invoke_llm([UserPromptMessage(content="返回 JSON：city 字段为成都，sum 字段为 17 加 25 的结果。")],
        model_parameters={"enable_thinking": False, "temperature": 0.7, "max_tokens": 512,
                          "response_format": "json_schema", "json_schema": json.dumps(schema)}, stream=False)
    answer, _ = answer_and_reasoning(text_content(result.message))
    value = json.loads(answer)
    return {"passed": value == {"city": "成都", "sum": 42} and type(value.get("sum")) is int,
            "result": value, "transport": "supported: JSON mode plus schema prompt",
            "usage": usage_summary(result.usage)}


def red_png():
    def chunk(kind, content):
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff\x00\x00" * 64) * 64)) + chunk(b"IEND", b"")
    return base64.b64encode(png).decode()


def vision_test(llm):
    result = llm.invoke_llm([UserPromptMessage(content=[
        TextPromptMessageContent(data="这张图片的主要颜色是什么？只用中文回答颜色名称。"),
        ImagePromptMessageContent(format="png", mime_type="image/png", base64_data=red_png()),
    ])], model_parameters={"enable_thinking": False, "temperature": 0.7, "max_tokens": 256}, stream=False)
    answer, _ = answer_and_reasoning(text_content(result.message))
    return {"passed": "红" in answer, "answer": answer, "image": "synthetic 64x64 solid red PNG",
            "usage": usage_summary(result.usage)}


def long_context_test(llm):
    marker = "VERIFY-7319-END"
    filler = "This is neutral filler text for a deployment context length check.\n" * 600
    prompt = "Read the full text and return only the validation code at its end.\n" + filler + "\nValidation code: " + marker
    result = llm.invoke_llm([UserPromptMessage(content=prompt)],
        model_parameters={"enable_thinking": False, "temperature": 0.7, "max_tokens": 256}, stream=False)
    answer, _ = answer_and_reasoning(text_content(result.message))
    usage = usage_summary(result.usage)
    return {"passed": answer == marker and usage.get("prompt_tokens", 0) > 4096,
            "answer": answer, "expected": marker, "usage": usage}


def embedding_retrieval(embedding):
    documents = embedding.invoke_text_embedding(DOCS, input_type=EmbeddingInputType.DOCUMENT)
    queries = embedding.invoke_text_embedding([query["text"] for query in QUERIES], input_type=EmbeddingInputType.QUERY)
    rows = []
    for query, vector in zip(QUERIES, queries.embeddings, strict=True):
        ranking = ranked([cosine(vector, item) for item in documents.embeddings])
        rows.append({**query, "ranking": ranking, "top1_correct": ranking[0]["index"] == query["expected"]})
    vectors = documents.embeddings + queries.embeddings
    dimensions = sorted({len(vector) for vector in vectors})
    norms = [math.sqrt(sum(x * x for x in vector)) for vector in vectors]
    credentials = embedding.credentials
    status, direct = direct_request(embedding, "POST", "/embeddings", {
        "model": credentials.get("endpoint_model_name") or embedding.model_name,
        "input": [credentials["query_prefix"] + " " + query["text"] for query in QUERIES],
        "encoding_format": "float",
    })
    ordered = sorted(direct["data"], key=lambda item: item["index"])
    differences = [max(abs(a - b) for a, b in zip(vector, item["embedding"], strict=True))
                   for vector, item in zip(queries.embeddings, ordered, strict=True)]
    # Different inference batch sizes can change low-order digits; compare vector directions.
    prefix_cosines = [cosine(vector, item["embedding"])
                      for vector, item in zip(queries.embeddings, ordered, strict=True)]
    return {"passed": all(row["top1_correct"] for row in rows) and dimensions == [2560] and min(prefix_cosines) > 0.99999,
            "queries": rows, "dimensions": dimensions, "norm_range": [min(norms), max(norms)],
            "query_prefix_direct_check_http": status, "max_prefix_vector_difference": max(differences),
            "prefix_vector_cosines": prefix_cosines}


def embedding_batch(embedding):
    texts = [f"Synthetic document {index}: batch boundary validation." for index in range(17)]
    result = embedding.invoke_text_embedding(texts, input_type=EmbeddingInputType.DOCUMENT)
    dimensions = sorted({len(vector) for vector in result.embeddings})
    finite = all(math.isfinite(x) for v in result.embeddings for x in v)
    schema_max_chunks = embedding.get_model_schema().model_dump(mode="json")["model_properties"].get("max_chunks")
    complete = len(result.embeddings) == 17 and dimensions == [2560] and finite
    return {"passed": complete and schema_max_chunks == int(embedding.credentials["max_chunks"]),
            "all_inputs_returned_correct_dimensions": complete,
            "inputs": 17, "outputs": len(result.embeddings), "saved_max_chunks": embedding.credentials["max_chunks"],
            "schema_max_chunks": schema_max_chunks, "dimensions": dimensions, "finite": finite}


def rerank_test(reranker, mode, template=None):
    rows = []
    for query in QUERIES:
        if mode == "dify":
            result = reranker.invoke_rerank(query=query["text"], docs=DOCS, score_threshold=None, top_n=len(DOCS))
            ranking = [{"index": doc.index, "score": round(doc.score, 8)} for doc in result.docs]
            status = "plugin invocation succeeded"
        else:
            documents = DOCS
            query_text = query["text"]
            if mode == "formatted_control":
                documents = [template.render(messages=[{"role": "query", "content": query_text},
                                                       {"role": "document", "content": document}]) for document in DOCS]
                query_text = ""
            endpoint = reranker.credentials.get("rerank_endpoint_url") or reranker.credentials["endpoint_url"].rstrip("/") + "/rerank"
            status, result = direct_request(reranker, "POST", endpoint, {
                "model": reranker.credentials.get("endpoint_model_name") or reranker.model_name,
                "query": query_text, "documents": documents, "top_n": len(DOCS),
            }, absolute=True)
            ranking = sorted([{"index": item["index"], "score": round(item["relevance_score"], 8)}
                              for item in result["results"]], key=lambda item: item["score"], reverse=True)
        assert sorted(item["index"] for item in ranking) == list(range(len(DOCS)))
        rows.append({**query, "status": status, "ranking": ranking,
                     "top1_correct": ranking[0]["index"] == query["expected"]})
    return {"passed": all(row["top1_correct"] for row in rows), "mode": mode,
            "correct_top1": sum(row["top1_correct"] for row in rows), "total_queries": len(rows), "queries": rows}


def main():
    signal.signal(signal.SIGALRM, timed_out)
    assert answer_and_reasoning("<think>work</think>126") == ("126", 4)
    assert math.isclose(cosine([1, 0], [1, 0]), 1)
    assert base64.b64decode(red_png()).startswith(b"\x89PNG\r\n\x1a\n")
    emit({"event": "run_started", "utc": datetime.now(timezone.utc).isoformat(), "provider": PROVIDER,
          "models": MODEL_NAMES, "fixture_note": "New synthetic fixtures following documented test categories; the old document did not retain exact full fixtures.",
          "documents": DOCS, "queries": QUERIES})
    _, app = create_app()
    logging.disable(logging.CRITICAL)
    with app.app_context():
        account = db.session.execute(select(Account).where(Account.email == "dify@localhost.com")).scalar_one()
        tenant = db.session.execute(select(TenantAccountJoin).where(
            TenantAccountJoin.account_id == account.id, TenantAccountJoin.current.is_(True))).scalar_one()
        manager = ModelManager.for_tenant(tenant.tenant_id, user_id=account.id)
        models = [manager.get_model_instance(tenant.tenant_id, PROVIDER, kind, name)
                  for name, kind in zip(MODEL_NAMES, [ModelType.LLM, ModelType.TEXT_EMBEDDING, ModelType.RERANK], strict=True)]
        before = config_fingerprint(tenant.tenant_id)
        for model in models:
            for key in ("api_key", "endpoint_url", "rerank_endpoint_url"):
                if model.credentials.get(key):
                    REDACTIONS.append(model.credentials[key])
        fields = ["context_size", "max_tokens_to_sample", "mode", "api_type", "agent_thought_support",
                  "compatibility_mode", "token_param_name", "function_calling_type", "stream_function_calling",
                  "vision_support", "structured_output_support", "stream_include_usage", "max_chunks",
                  "encoding_format", "query_prefix", "document_prefix"]
        for model in models:
            schema = model.get_model_schema()
            emit({"event": "saved_configuration", "model": model.model_name,
                  "parameters": {key: model.credentials[key] for key in fields if key in model.credentials},
                  "features": [str(feature) for feature in schema.features or []],
                  "properties": schema.model_dump(mode="json")["model_properties"],
                  "max_tokens_rule": [{"min": rule.min, "max": rule.max} for rule in schema.parameter_rules if rule.name == "max_tokens"]})
            def metadata(model=model):
                status, payload = direct_request(model, "GET", "/models")
                name = model.credentials.get("endpoint_model_name") or model.model_name
                entries = [{"id": item["id"], "max_model_len": item.get("max_model_len")}
                           for item in payload.get("data", []) if item["id"].lower() == name.lower()]
                return {"passed": bool(entries), "http_status": status, "model_metadata": entries}
            run_test("metadata_" + model.model_name, metadata)
        llm, embedding, reranker = models
        run_test("llm_non_thinking", lambda: simple_llm(llm))
        run_test("llm_thinking_medium", lambda: simple_llm(llm, thinking=True))
        run_test("llm_stream_text_usage", lambda: simple_llm(llm, stream=True))
        run_test("llm_tool_call", lambda: tool_test(llm, stream=False))
        run_test("llm_stream_tool_call", lambda: tool_test(llm, stream=True))
        run_test("llm_json_schema_sample", lambda: json_test(llm))
        run_test("llm_vision", lambda: vision_test(llm))
        run_test("llm_context_over_4k", lambda: long_context_test(llm))
        run_test("embedding_retrieval_and_query_prefix", lambda: embedding_retrieval(embedding))
        run_test("embedding_batch_17", lambda: embedding_batch(embedding))
        parts = urlsplit(reranker.credentials["endpoint_url"])
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        def reranker_metadata():
            status, version = direct_request(reranker, "GET", origin + "/version", absolute=True)
            schema_status, schema = direct_request(reranker, "GET", origin + "/openapi.json", absolute=True)
            request_schema = schema.get("components", {}).get("schemas", {}).get("RerankRequest", {})
            return {"passed": status == 200, "version": version.get("version"), "openapi_status": schema_status,
                    "rerank_request_has_chat_template": "chat_template" in request_schema.get("properties", {})}
        run_test("reranker_server_metadata", reranker_metadata)
        run_test("reranker_dify_normal", lambda: rerank_test(reranker, "dify"))
        run_test("reranker_direct_normal", lambda: rerank_test(reranker, "direct"))
        def formatted_control():
            from jinja2 import Environment
            with httpx.Client(timeout=30, trust_env=False, follow_redirects=True) as client:
                response = client.get(TEMPLATE_URL)
                response.raise_for_status()
            template_text = response.text
            result = rerank_test(reranker, "formatted_control", Environment().from_string(template_text))
            result["template_source"] = TEMPLATE_URL
            result["template_sha256"] = hashlib.sha256(template_text.encode()).hexdigest()
            result["diagnostic_only"] = True
            return result
        run_test("reranker_formatted_control", formatted_control)
        db.session.expire_all()
        emit({"event": "configuration_unchanged", "unchanged": config_fingerprint(tenant.tenant_id) == before})
    tests = [item for item in RESULTS if item.get("event") == "test_result"]
    emit({"event": "run_completed", "tests": len(tests), "passed": sum(item["passed"] for item in tests),
          "failed": [item["test"] for item in tests if not item["passed"]]})


def embedding_followup():
    signal.signal(signal.SIGALRM, timed_out)
    emit({"event": "followup_started", "utc": datetime.now(timezone.utc).isoformat()})
    _, app = create_app()
    logging.disable(logging.CRITICAL)
    with app.app_context():
        account = db.session.execute(select(Account).where(Account.email == "dify@localhost.com")).scalar_one()
        tenant = db.session.execute(select(TenantAccountJoin).where(
            TenantAccountJoin.account_id == account.id, TenantAccountJoin.current.is_(True))).scalar_one()
        manager = ModelManager.for_tenant(tenant.tenant_id, user_id=account.id)
        embedding = manager.get_model_instance(tenant.tenant_id, PROVIDER, ModelType.TEXT_EMBEDDING, MODEL_NAMES[1])
        before = config_fingerprint(tenant.tenant_id)
        credentials = embedding.credentials
        REDACTIONS.extend(credentials[key] for key in ("api_key", "endpoint_url") if credentials.get(key))

        if sys.argv[1:] == ["embedding-verification"]:
            run_test("embedding_retrieval_and_query_prefix", lambda: embedding_retrieval(embedding))
            run_test("embedding_batch_17", lambda: embedding_batch(embedding))
            db.session.expire_all()
            emit({"event": "configuration_unchanged", "unchanged": config_fingerprint(tenant.tenant_id) == before})
            return

        def prefix_comparison():
            vectors = embedding.invoke_text_embedding([query["text"] for query in QUERIES],
                                                       input_type=EmbeddingInputType.QUERY).embeddings
            model_name = credentials.get("endpoint_model_name") or embedding.model_name
            prefix = credentials["query_prefix"]

            def direct_vectors(inputs):
                _, result = direct_request(embedding, "POST", "/embeddings", {
                    "model": model_name, "input": inputs, "encoding_format": "float",
                })
                return [item["embedding"] for item in sorted(result["data"], key=lambda item: item["index"])]

            batched = direct_vectors([prefix + " " + query["text"] for query in QUERIES])
            rows = []
            for index, (query, vector) in enumerate(zip(QUERIES, vectors, strict=True)):
                prefixed = direct_vectors([prefix + " " + query["text"]])[0]
                repeated = direct_vectors([prefix + " " + query["text"]])[0]
                plain = direct_vectors([query["text"]])[0]
                rows.append({
                    "query_id": query["id"],
                    "cosine_dify_vs_prefixed_single": cosine(vector, prefixed),
                    "max_abs_dify_vs_prefixed_single": max(abs(a-b) for a,b in zip(vector, prefixed, strict=True)),
                    "cosine_dify_vs_prefixed_batch": cosine(vector, batched[index]),
                    "max_abs_dify_vs_prefixed_batch": max(abs(a-b) for a,b in zip(vector, batched[index], strict=True)),
                    "cosine_dify_vs_no_prefix": cosine(vector, plain),
                    "max_abs_repeat_same_input": max(abs(a-b) for a,b in zip(prefixed, repeated, strict=True)),
                })
            return {"passed": all(row["cosine_dify_vs_prefixed_single"] > 0.99999 and
                                  row["cosine_dify_vs_prefixed_single"] > row["cosine_dify_vs_no_prefix"] + 0.001
                                  for row in rows), "queries": rows}

        run_test("embedding_prefix_controlled_comparison", prefix_comparison)
        schema = embedding.get_model_schema().model_dump(mode="json")
        saved = int(credentials["max_chunks"])
        effective = schema["model_properties"].get("max_chunks")
        emit({"event": "test_result", "test": "embedding_batch_setting_effective", "passed": effective == saved,
              "saved_max_chunks": saved, "schema_max_chunks": effective,
              "installed_sdk_source": "dify_plugin/interfaces/model/openai_compatible/text_embedding.py:241",
              "finding": "Installed SDK schema sets MAX_CHUNKS to 1; plugin _get_max_chunks reads that schema."})
        db.session.expire_all()
        emit({"event": "configuration_unchanged", "unchanged": config_fingerprint(tenant.tenant_id) == before})


if __name__ == "__main__":
    try:
        if sys.argv[1:] in (["embedding-followup"], ["embedding-verification"]):
            embedding_followup()
        else:
            main()
    except Exception as error:
        emit({"event": "fatal_error", "error_type": type(error).__name__, "error": sanitized_error(error)})
        raise SystemExit(1)
