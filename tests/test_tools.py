import json

import pytest
import respx
from acedatacloud import APIError, AuthenticationError, ModerationError, RateLimitError
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.llms import MockLLM
from llama_index.core.tools import FunctionTool

from llama_index.tools.seedance_acedatacloud import SeedanceToolSpec

CLASS = SeedanceToolSpec
GEN = "seedance_generate_video"
EDIT = "seedance_generate_video_from_image"
QUERY = "seedance_get_task"
ROUTE = "/seedance/videos"
EDIT_ROUTE = "/seedance/videos"
TASK = "/seedance/tasks"
KEY = "video_url"
EXT = "mp4"
KWARGS = {
    "prompt": "Camera moves through a sunrise garden",
    "model": "doubao-seedance-2-0-260128",
    "duration": 5,
    "resolution": "720p",
    "ratio": "16:9",
}
EDIT_KWARGS = {
    "prompt": "Camera moves through a sunrise garden",
    "model": "doubao-seedance-2-0-260128",
    "duration": 5,
    "resolution": "720p",
    "ratio": "16:9",
    "image_url": "https://example.org/first.png",
}
EXPECTED = {
    "async": True,
    "model": "doubao-seedance-2-0-260128",
    "content": [{"type": "text", "text": "Camera moves through a sunrise garden"}],
    "duration": 5,
    "resolution": "720p",
    "generate_audio": False,
}
REQUIRE_FINISHED = False

BASE = "https://api.acedata.cloud"


def completed():
    return {
        "id": "old-task",
        "finished_at": 123,
        "trace_id": "old-trace",
        "response": {"success": True, "data": [{KEY: "https://example.org/final." + EXT, "state": "succeeded"}]},
    }


@pytest.fixture
async def spec():
    instance = CLASS(api_token="dummy-key")
    yield instance
    await instance.aclose()


def test_native_function_agent_schema_no_key(spec):
    with respx.mock(assert_all_mocked=True) as router:
        tools = spec.to_tool_list()
        assert all(isinstance(t, FunctionTool) for t in tools)
        assert [t.metadata.name for t in tools] == [GEN, EDIT, QUERY]
        schema = tools[0].metadata.get_parameters_dict()
        assert {"prompt", "model"} <= set(schema["required"])
        assert "api_token" not in json.dumps(schema) and "dummy-key" not in str(spec)
        agent = FunctionAgent(llm=MockLLM(), tools=tools)
        assert len(agent.tools) == 3 and not router.calls


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_native_submit_then_new_instance_recovers_same_task(spec, asynchronous):
    with respx.mock(assert_all_mocked=True) as router:
        generation = router.post(BASE + ROUTE).respond(200, json={"task_id": "old-task"})
        query = router.post(BASE + TASK).respond(200, json=completed())
        tool = spec.to_tool_list()[0]
        submission = (await tool.acall(**KWARGS) if asynchronous else tool.call(**KWARGS)).raw_output
        assert submission["task_id"] == "old-task" and submission["status"] == "pending"
        assert submission["media_urls"] == [] and generation.call_count == 1
        body = json.loads(generation.calls[0].request.content)
        assert all(body.get(k) == v for k, v in EXPECTED.items())
        assert generation.calls[0].request.headers["Authorization"] == "Bearer dummy-key"
        recovered = CLASS(api_token="same-app-dummy-key")
        try:
            q = recovered.to_tool_list()[2]
            result = (await q.acall(task_id="old-task") if asynchronous else q.call(task_id="old-task")).raw_output
        finally:
            await recovered.aclose()
        assert result["status"] == "succeeded" and result["success"] is True
        assert result["media_urls"] == ["https://example.org/final." + EXT]
        assert result["trace_id"] == "old-trace"
        assert json.loads(query.calls[0].request.content) == {"id": "old-task", "action": "retrieve"}
        assert len(router.calls) == 2


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_native_edit_uses_service_action_and_input(spec, asynchronous):
    with respx.mock(assert_all_mocked=True) as router:
        route = router.post(BASE + EDIT_ROUTE).respond(200, json={"task_id": "edit-task"})
        tool = spec.to_tool_list()[1]
        result = (await tool.acall(**EDIT_KWARGS) if asynchronous else tool.call(**EDIT_KWARGS)).raw_output
        assert result["task_id"] == "edit-task" and route.call_count == 1
        body = json.loads(route.calls[0].request.content)
        assert body["async"] is True and body["model"] == EDIT_KWARGS["model"]
        assert body["content"][1] == {
            "type": "image_url",
            "image_url": {"url": "https://example.org/first.png"},
            "role": "first_frame",
        }


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "old-task", "response": None},
        {"state": "processing", "response": {"success": True, "data": [{KEY: "https://example.org/preview." + EXT}]}},
        {"response": {"success": True, "data": [{KEY: "https://example.org/preview." + EXT, "state": "running"}]}},
    ],
)
async def test_previews_and_pending_body_are_not_final(spec, payload):
    with respx.mock(assert_all_mocked=True) as router:
        router.post(BASE + TASK).respond(200, json=payload)
        result = getattr(spec, QUERY)("old-task")
        assert result["status"] == "pending" and result["success"] is None
        assert result["media_urls"] == [] and result["polling_interval_seconds"] == 15
        assert len(router.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"finished_at": 123, "response": {"success": False, "error": {"code": "failed"}}},
        {
            "finished_at": 123,
            "response": {"success": True, "data": [{KEY: "https://example.org/preview." + EXT, "state": "error"}]},
        },
        {
            "finished_at": 123,
            "state": "failed",
            "response": {"success": True, "data": [{KEY: "https://example.org/preview." + EXT}]},
        },
    ],
)
async def test_failure_wins_over_preview(spec, payload):
    with respx.mock(assert_all_mocked=True) as router:
        router.post(BASE + TASK).respond(200, json=payload)
        result = getattr(spec, QUERY)("old-task")
        assert result["status"] == "failed" and result["success"] is False
        assert result["media_urls"] == [] and result["polling_interval_seconds"] is None


@pytest.mark.parametrize(
    "status,error", [(401, AuthenticationError), (403, ModerationError), (429, RateLimitError), (500, APIError)]
)
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_submit_errors_preserved_no_retry(spec, status, error, asynchronous):
    with respx.mock(assert_all_mocked=True) as router:
        route = router.post(BASE + ROUTE).respond(status, json={"error": {"message": "rejected"}})
        with pytest.raises(error):
            if asynchronous:
                await getattr(spec, "a" + GEN)(**KWARGS)
            else:
                getattr(spec, GEN)(**KWARGS)
        assert route.call_count == 1


async def test_query_401_never_submits(spec):
    with respx.mock(assert_all_mocked=True) as router:
        router.post(BASE + TASK).respond(401, json={"error": {"message": "not authorized"}})
        with pytest.raises(AuthenticationError):
            await getattr(spec, "a" + QUERY)("old-task")
        assert len(router.calls) == 1


@pytest.mark.parametrize("token", ["", " ", "Bearer token", "platform-account-token"])
def test_bad_credentials_fail_early(token):
    with pytest.raises(ValueError):
        CLASS(api_token=token)


async def test_env_token_and_cleanup(monkeypatch):
    monkeypatch.setenv("ACEDATACLOUD_API_TOKEN", "env-dummy")
    instance = CLASS()
    instance.close()
    await instance.aclose()


@pytest.mark.parametrize("field,value", [("prompt", " "), ("model", "")])
async def test_missing_input_never_networks(spec, field, value):
    with respx.mock(assert_all_mocked=True) as router:
        with pytest.raises(ValueError):
            getattr(spec, GEN)(**{**KWARGS, field: value})
        assert not router.calls


@pytest.mark.parametrize(
    "image", ["file:///tmp/photo.png", "https://user:pass@example.org/photo.png", "data:image/png;base64,AAAA"]
)
async def test_bad_image_inputs_fail_before_network(spec, image):
    with respx.mock(assert_all_mocked=True) as router:
        inputs = {**EDIT_KWARGS}
        if "image_url" in inputs:
            inputs["image_url"] = image
        else:
            inputs["image_urls"] = [image]
        with pytest.raises(ValueError):
            getattr(spec, EDIT)(**inputs)
        assert not router.calls


@pytest.mark.parametrize("response", [{}, {"success": True}, {"id": "nested"}, {"data": {"task_id": "nested-task"}}])
async def test_submission_id_contract_and_ambiguous_missing_id(spec, response):
    with respx.mock(assert_all_mocked=True) as router:
        route = router.post(BASE + ROUTE).respond(200, json=response)
        if not response.get("id") and not response.get("data"):
            with pytest.raises(RuntimeError, match="do not automatically resubmit"):
                getattr(spec, GEN)(**KWARGS)
        else:
            result = getattr(spec, GEN)(**KWARGS)
            assert result["task_id"] in {"nested", "nested-task"}
        assert route.call_count == 1


async def test_unknown_and_mismatched_task(spec):
    with respx.mock(assert_all_mocked=True) as router:
        route = router.post(BASE + TASK).respond(200, json={})
        result = getattr(spec, QUERY)("missing-task")
        assert result["status"] == "not_found" and result["media_urls"] == []
        route.respond(200, json={"id": "different-task"})
        with pytest.raises(ValueError, match="differs"):
            getattr(spec, QUERY)("old-task")


@pytest.mark.parametrize("data", [[], [{KEY: "file:///tmp/fake"}], [{KEY: "https://user:pass@example.org/fake"}]])
async def test_no_final_url_is_not_success(spec, data):
    with respx.mock(assert_all_mocked=True) as router:
        router.post(BASE + TASK).respond(200, json={"finished_at": 123, "response": {"success": True, "data": data}})
        with pytest.raises(ValueError, match="without final"):
            getattr(spec, QUERY)("old-task")


async def test_malformed_task_and_empty_id(spec):
    with respx.mock(assert_all_mocked=True) as router:
        router.post(BASE + TASK).respond(200, json={"response": "invalid"})
        with pytest.raises(ValueError):
            getattr(spec, QUERY)("old-task")
        with pytest.raises(ValueError):
            getattr(spec, QUERY)(" ")
        assert len(router.calls) == 1


@pytest.mark.parametrize(
    "override",
    [
        {"duration": True},
        {"duration": 31},
        {"resolution": "BAD"},
        {"ratio": "BAD"},
        {"model": "doubao-seedance-2-5-260628", "resolution": "4k"},
        {"model": "doubao-seedance-2-0-fast-260128", "resolution": "1080p"},
    ],
)
async def test_invalid_service_options_never_submit(spec, override):
    with respx.mock(assert_all_mocked=True) as router:
        with pytest.raises(ValueError):
            getattr(spec, GEN)(**{**KWARGS, **override})
        assert not router.calls
