"""
Agent 执行循环 (核心，参考 GenericAgent agent_loop.py)

每轮: messages → LLM chat → 解析 tool_calls → dispatch → 收集结果 → 下一轮
"""

import json
from decimal import Decimal
from handler import TextToSQLHandler, StepOutcome


def _json_serial(obj):
    """JSON序列化，处理Decimal等特殊类型"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def agent_runner_loop(client, system_prompt: str, user_input: str,
                      handler: TextToSQLHandler, tools_schema: list,
                      max_turns: int = 20, verbose: bool = True):
    """
    Agent 核心执行循环

    Args:
        client: OpenAI 客户端
        system_prompt: 系统提示词
        user_input: 用户输入
        handler: 工具分发器
        tools_schema: 工具定义列表
        max_turns: 最大轮次
        verbose: 是否输出过程信息
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]

    turn = 0
    final_answer = ""

    while turn < max_turns:
        turn += 1
        if verbose:
            yield f"\n**第 {turn} 轮...**\n"

        # 调用 LLM
        response = client.chat.completions.create(
            model=client.model,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto"
        )

        assistant_msg = response.choices[0].message

        # 没有工具调用 → LLM 给出了最终回答
        if not assistant_msg.tool_calls:
            final_answer = assistant_msg.content or ""
            yield final_answer
            break

        # 解析工具调用
        tool_calls = []
        for tc in assistant_msg.tool_calls:
            tool_calls.append({
                "tool_name": tc.function.name,
                "args": json.loads(tc.function.arguments),
                "id": tc.id
            })

        if verbose:
            for tc in tool_calls:
                yield f"🛠️ 调用工具: {tc['tool_name']}({json.dumps(tc['args'], ensure_ascii=False)})\n"

        # 执行工具
        tool_results = []
        next_prompts = []

        for tc in tool_calls:
            outcome = handler.dispatch(tc["tool_name"], tc["args"])

            if outcome.should_exit:
                yield f"\n任务结束: {outcome.data}\n"
                return

            if outcome.data is not None:
                result_str = json.dumps(outcome.data, ensure_ascii=False, default=_json_serial) \
                    if isinstance(outcome.data, (dict, list)) else str(outcome.data)
                tool_results.append({
                    "tool_call_id": tc["id"],
                    "role": "tool",
                    "content": result_str
                })

            if outcome.next_prompt:
                next_prompts.append(outcome.next_prompt)

        if verbose and tool_results:
            yield f"工具返回 {len(tool_results)} 个结果\n"

        # 构建下一轮 messages
        # 添加 assistant 消息（含 tool_calls）
        messages.append({
            "role": "assistant",
            "content": assistant_msg.content,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["tool_name"],
                        "arguments": json.dumps(tc["args"], ensure_ascii=False)
                    }
                }
                for tc in tool_calls
            ]
        })

        # 添加 tool 结果消息
        for tr in tool_results:
            messages.append(tr)

        # 如果没有工具结果可继续，退出
        if not next_prompts:
            yield "\n对话结束\n"
            break

    else:
        yield "\n达到最大轮次限制\n"
