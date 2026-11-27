import json

import httpx
import pytest

from app.llm import ChatMessage, LLMUnavailableError
from app.llm.ollama import EMBED_BATCH_SIZE, OllamaProvider


def make_provider(handler, dims=3) -> OllamaProvider:
    return OllamaProvider(
        base_url="http://ollama.test",
        chat_model="chat-model",
        embed_model="embed-model",
        embed_dimensions=dims,
        document_prefix="doc: ",
        query_prefix="query: ",
        transport=httpx.MockTransport(handler),
    )


def test_embed_adds_prefix_and_batches():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]] * len(body["input"])})

    texts = [f"text {i}" for i in range(EMBED_BATCH_SIZE + 5)]
    vectors = make_provider(handler).embed(texts, kind="document")

    assert len(vectors) == len(texts)
    assert [len(r["input"]) for r in requests] == [EMBED_BATCH_SIZE, 5]
    assert requests[0]["input"][0] == "doc: text 0"
    assert requests[0]["model"] == "embed-model"


def test_query_prefix():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["input"][0])
        return httpx.Response(200, json={"embeddings": [[1, 2, 3]]})

    make_provider(handler).embed(["hello"], kind="query")
    assert seen == ["query: hello"]


def test_embed_dimension_mismatch_raises():
    provider = make_provider(lambda r: httpx.Response(200, json={"embeddings": [[1.0, 2.0]]}))
    with pytest.raises(LLMUnavailableError, match="2 dimensions, expected 3"):
        provider.embed(["x"], kind="document")


def test_chat_sends_schema_and_returns_content():
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"a": 1}'}})

    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    reply = make_provider(handler).chat([ChatMessage("user", "hi")], json_schema=schema)

    assert reply == '{"a": 1}'
    assert sent["format"] == schema
    assert sent["stream"] is False
    assert sent["options"]["temperature"] == 0.0
    assert sent["messages"] == [{"role": "user", "content": "hi"}]


def test_unreachable_server_raises():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(LLMUnavailableError, match="not reachable"):
        make_provider(handler).chat([ChatMessage("user", "hi")])


def test_http_error_raises_with_details():
    provider = make_provider(lambda r: httpx.Response(404, text="model not found"))
    with pytest.raises(LLMUnavailableError, match="404"):
        provider.embed(["x"], kind="document")


def test_status_detects_missing_models():
    tags = {"models": [{"name": "embed-model:latest"}]}
    status = make_provider(lambda r: httpx.Response(200, json=tags)).status()
    assert status.reachable
    assert status.missing_models == ["chat-model"]
    assert not status.ok


def test_status_unreachable():
    def handler(request):
        raise httpx.ConnectError("down")

    assert make_provider(handler).status().reachable is False
