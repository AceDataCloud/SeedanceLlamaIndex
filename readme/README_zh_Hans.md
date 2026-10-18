# Seedance by Ace Data Cloud：LlamaIndex 原生工具

[English](../README.md) · [当前模型和价格](https://platform.acedata.cloud/models?utm_source=llamaindex&utm_medium=referral&utm_campaign=evergreen&utm_content=seedance_llamaindex_pricing_zh)

Ace Data Cloud 独立维护的单服务集成，不是 Seedance 或 LlamaIndex 官方产品。
原生 `BaseToolSpec` 直接给出三个同步/异步工具，无需配置 MCP 地址：
`seedance_generate_video`、`seedance_generate_video_from_image`、`seedance_get_task`。

## 1. 安装

包名 `llama-index-tools-seedance-acedatacloud`，Python 3.10+。源码已合并，GitHub v0.1.0 发行入口：https://github.com/AceDataCloud/SeedanceLlamaIndex/releases/tag/v0.1.0 。PyPI受共享新项目额度限制，官方收录仍待审。

```bash
python -m pip install "https://github.com/AceDataCloud/SeedanceLlamaIndex/releases/download/v0.1.0/llama_index_tools_seedance_acedatacloud-0.1.0-py3-none-any.whl"
```

## 2. 注册、登录、General application 与 Token

[注册/登录](https://platform.acedata.cloud?utm_source=llamaindex&utm_medium=referral&utm_campaign=evergreen&utm_content=seedance_llamaindex_register_zh)后进入[Applications](https://platform.acedata.cloud/console/applications?utm_source=llamaindex&utm_medium=referral&utm_campaign=evergreen&utm_content=seedance_llamaindex_api_key_zh)。
找到 **General application**，没有时 **Initialize General Application**。
检查 Seedance 当前模型权限、余额和价格；通用 Key 仍受账户权限限制，专用应用仅限指定服务。
复制 API Key，或 **Manage Keys → Create** 创建 `LlamaIndex Seedance` 专用 Key。

![真实控制台：复制已遮挡的 Key 或管理 Key](https://raw.githubusercontent.com/AceDataCloud/SunoDify/8d3d03570e73324220f111f7fe343da0792a8071/_assets/tutorial/get-api-key-en.png)

创建时按需设置有效期、用量与 Allowed APIs，至少包含 `/seedance/videos` 与 `/seedance/tasks`。
创建后回列表复制 Token 本体，不加 Bearer/空格/引号；`platform-...` 管理令牌不能替代。

![真实控制台：创建独立凭据](https://raw.githubusercontent.com/AceDataCloud/SunoDify/8d3d03570e73324220f111f7fe343da0792a8071/_assets/tutorial/create-api-key-en.png)

2026-10-18 复用固定 SunoDify 提交的真实通用账户截图，凭据已遮挡；旧图名 `Dify tutorial`
在本集成改填 `LlamaIndex Seedance`。不是本包真实执行图，不把 Key 放进 prompt、日志或提交代码。

## 3. 在本平台实际配置位置

环境变量 **`ACEDATACLOUD_API_TOKEN`** 或应用凭据库传入 `api_token`：

```python
from llama_index.tools.seedance_acedatacloud import SeedanceToolSpec

spec = SeedanceToolSpec()
tools = spec.to_tool_list()
# FunctionAgent(llm=llm, tools=tools)
```

构造/查看 schema 不收费，也不发 API。框架入口是代码，不承诺新的聊天页面或 GUI。
Token 不作为 Agent 工具参数。

## 4. 首次使用与同 ID 恢复

英文 README 提供完整可运行异步代码。真实生成会收费，需先核当日权限/价格并获得费用授权。
明确填写当前可用 `model`、成本相关参数后才运行；不设默认模型、不加替代路由。

```python
submission = (
    await tools[0].acall(
        prompt="A quiet sunrise garden, gentle camera movement.",
        model="YOUR_AVAILABLE_MODEL",
        duration=5,
        resolution="720p",
    )
).raw_output
# 保存 task_id，至少等15秒；后续只查询，不再次生成
result = (await tools[2].acall(task_id=submission["task_id"])).raw_output
```

用完 `await spec.aclose()`。程序重启后新建同类工具实例，以同应用授权 Key 查询原 task ID，
无需重新提交生成；可单独运行 `python examples/query_existing.py 原任务ID`。
`status=succeeded`、`success=true` 且 `media_urls` 非空才是最终结果。
处理中/预览链接不进入最终输出；失败保留 failed，未知 ID 返回 not_found，不鼓励重提；
响应 ID 与请求不同直接报错。401/403/429/500 保留 SDK 含义，无自动重试。
不明超时或无任务 ID 时先查账户历史，别重新生成碰碰运气。

## 参数与本轮范围

文字 prompt 映射成 content 文本块；首帧图生视频追加 role=first_frame 的 image_url 块。明确 generate_audio=false，不隐式增加音频。时长需显式指定：1.0为2–12秒、1.5为4–12秒、2.0为4–15秒、2.5为4–30秒；4k仅2.0旗舰，2.0 fast/mini最高720p。高级多模态、编辑/延长、回调不在本包范围。

输入图片仅接受无内嵌凭据的公网HTTP(S) URL，暂不开放本地文件/data URI；
其他高级动作没有因为同服务存在就自动支持。合同固定来源见 [contracts.json](../docs/contracts.json)。

## 5. 免费验收

```bash
pip install -e ".[dev]"
python examples/offline.py
pytest
python -m build
```

真实 LlamaIndex 工具/SDK 使用模拟HTTP、假ID和媒体链接。独立wheel新环境验证提交、
新实例恢复同任务查询；不发新收费请求、不证明终态媒体/账单或营收，也不生成最终文字回答。

常见问题：PyPI找不到先用GitHub正式wheel；401重查raw Key/有效期/权限；403查余额和模型准入；
429/超时禁自动重提；pending等15秒查同ID；not_found重核ID与归属，知道别人的ID不等于有权限。

## 发版门槛

现有组织PYPI_TOKEN已确认可用，不需要新账号或另配Trusted Publisher。当前PyPI门槛为共享账号/IP新建项目额度，已知重置时间2026-10-20 03:23:23（北京时间）；发行GitHub wheel与它分开。管理员届时先读registry，再对既有v0.1.0标签手动执行publish.yml发布，不换身份/IP。官方收录单独验收；
官方发现文档草稿：https://github.com/run-llama/llama_index/pull/23574 ，投稿不是获准收录。
不自动创建身份、接受协议或扩权。
