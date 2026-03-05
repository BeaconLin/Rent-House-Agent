import json
import httpx
import os
from typing import List, Tuple, Optional
from agent.tools import TOOLS, search_houses, get_house_detail, get_houses_nearby, search_landmark, get_house_listings, \
    get_nearby_landmarks, get_landmarks, get_landmark_by_name, get_landmark_by_id, get_landmark_stats, \
    get_houses_by_community, get_house_stats, rent_house, terminate_rental, take_offline
from agent.prompts import SYSTEM_PROMPT

TOOL_MAP = {
    "search_houses": search_houses,
    "get_house_detail": get_house_detail,
    "get_houses_nearby": get_houses_nearby,
    "search_landmark": search_landmark,
    "get_house_listings": get_house_listings,
    "get_nearby_landmarks": get_nearby_landmarks,
    "get_landmarks": get_landmarks,
    "get_landmark_by_name": get_landmark_by_name,
    "get_landmark_by_id": get_landmark_by_id,
    "get_landmark_stats": get_landmark_stats,
    "get_houses_by_community": get_houses_by_community,
    "get_house_stats": get_house_stats,
    "rent_house": rent_house,
    "terminate_rental": terminate_rental,
    "take_offline": take_offline,
}

# 定义搜索房源相关的工具名称
HOUSE_SEARCH_TOOLS = {"search_houses", "get_houses_nearby", "get_houses_by_community"}

# 全局字典：跟踪每个session_id是否已标记为"无房源"状态
# key: session_id, value: True表示该session已标记为无房源
_session_no_houses_status: dict[str, bool] = {}


def get_model_ip() -> str:
    """
    获取模型服务器IP地址

    优先级：
    1. 环境变量 MODEL_IP
    2. 否则使用默认值 "localhost"

    Returns:
        模型服务器IP地址
    """
    return os.getenv("MODEL_IP", "localhost")


def _is_house_search_result_empty(result: dict) -> bool:
    """
    判断房源搜索结果是否为空

    Args:
        result: 工具返回的结果字典

    Returns:
        True表示结果为空，False表示有结果
    """
    if not isinstance(result, dict):
        return False
    
    # 检查常见的空结果格式
    # 格式1: {"data": [], "total": 0}
    # 格式2: {"houses": [], "total": 0}
    # 格式3: {"data": []} 或 {"houses": []}
    # 格式4: {"total": 0} 且没有data或houses字段，或data/houses为空
    
    # 检查total字段
    if "total" in result:
        if result.get("total", 0) == 0:
            return True
    
    # 检查data字段
    if "data" in result:
        data = result.get("data", [])
        if isinstance(data, list) and len(data) == 0:
            return True
    
    # 检查houses字段
    if "houses" in result:
        houses = result.get("houses", [])
        if isinstance(houses, list) and len(houses) == 0:
            return True
    
    return False


def _reset_session_status(session_id: str) -> None:
    """
    重置session的状态（当开始新任务时调用）

    Args:
        session_id: 会话ID
    """
    if session_id in _session_no_houses_status:
        del _session_no_houses_status[session_id]
        print(f"Session {session_id} 状态已重置（新任务开始）")


def _is_session_no_houses(session_id: str) -> bool:
    """
    检查session是否已标记为"无房源"状态

    Args:
        session_id: 会话ID

    Returns:
        True表示该session已标记为无房源
    """
    return _session_no_houses_status.get(session_id, False)


def _mark_session_no_houses(session_id: str) -> None:
    """
    标记session为"无房源"状态

    Args:
        session_id: 会话ID
    """
    if session_id:
        _session_no_houses_status[session_id] = True
        print(f"Session {session_id} 已标记为无房源状态，后续对话将直接返回无房源")


def _extract_house_ids_from_result(result: dict, max_count: int = 5) -> List[str]:
    """
    从工具返回结果中提取房源ID列表

    Args:
        result: 工具返回的结果字典
        max_count: 最多提取的房源数量，默认5个

    Returns:
        房源ID列表
    """
    house_ids = []
    
    if not isinstance(result, dict):
        return house_ids
    
    # 尝试从houses字段提取
    if "houses" in result:
        houses = result.get("houses", [])
        if isinstance(houses, list):
            for house in houses[:max_count]:
                if isinstance(house, dict) and "house_id" in house:
                    house_id = house.get("house_id")
                    if house_id:
                        house_ids.append(house_id)
    
    # 尝试从data字段提取
    if not house_ids and "data" in result:
        data = result.get("data", [])
        if isinstance(data, list):
            for item in data[:max_count]:
                if isinstance(item, dict) and "house_id" in item:
                    house_id = item.get("house_id")
                    if house_id:
                        house_ids.append(house_id)
    
    return house_ids[:max_count]


def _generate_house_search_response(result: dict) -> Optional[str]:
    """
    从搜索房源工具的结果中直接生成JSON响应，避免再次调用模型

    Args:
        result: 工具返回的结果字典

    Returns:
        如果可以直接生成响应，返回JSON字符串；否则返回None
    """
    # 检查结果是否为空
    if _is_house_search_result_empty(result):
        return json.dumps({"message": "没有找到符合条件的房源", "houses": []}, ensure_ascii=False)
    
    # 提取房源ID
    house_ids = _extract_house_ids_from_result(result, max_count=5)
    
    if house_ids:
        # 有房源，生成成功响应
        message = f"为您找到{len(house_ids)}套符合条件的房源"
        return json.dumps({"message": message, "houses": house_ids}, ensure_ascii=False)
    else:
        # 无法提取房源ID，返回None，让模型处理
        return None


async def build_llm_client(model_ip: Optional[str] = None, session_id: Optional[str] = None, messages: [] = None):
    """
    构建OpenAI客户端

    Args:
        model_ip: 模型服务器IP地址，如果为None则从环境变量获取
                  如果为"deepseek"，则使用DeepSeek API
        session_id: 会话ID，如果提供则添加到请求头中

    Returns:
        OpenAI客户端实例
    """
    import os
    import httpx
    from openai import AsyncOpenAI
    import asyncio

    # 如果提供了Session-ID，则添加到默认请求头
    default_headers = {}
    if session_id:
        default_headers["Session-ID"] = session_id

    # 默认使用本地模型服务器
    base_url = f"http://{model_ip}:8888/v1"

    # 创建免代理的httpx客户端
    http_client = httpx.AsyncClient(
        timeout=60.0,  # 设置超时时间为60秒
        proxy=None,  # 显式禁用代理
        trust_env=False
    )

    client = AsyncOpenAI(
        base_url=base_url,
        default_headers=default_headers,
        api_key="dummy-key",  # 本地模型服务器不需要真实的API密钥
        http_client=http_client  # 使用免代理的httpx客户端
    )

    # 异步调用
    try:
        chat_template_kwargs = {
            "enable_thinking": False
        }

        response = await client.chat.completions.create(
            model="qwen3-32b",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,  # 降低温度以获得更确定性的输出
            stream=False,
            top_p=0.9,  # 添加top_p参数进一步限制输出范围
            extra_body={
                "chat_template_kwargs": chat_template_kwargs
            }
        )
        return response
    except Exception as e:
        print(f"模型调用失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


async def run_agent(model_ip: Optional[str] = None, history: List[dict] = None, user_message: str = "",
                    session_id: str = "") -> Tuple[
    str, List[dict]]:
    """
    运行Agent，返回 (response_text, tool_results)
    v2接口，支持多轮工具调用

    Args:
        model_ip: 模型服务器IP地址，如果为None则从环境变量获取
                  如果为"deepseek"，则使用模型网关接口
        history: 对话历史记录，如果为None则使用空列表
        user_message: 用户消息
        session_id: 会话ID

    Returns:
        Tuple[str, List[dict]]: (回复文本, 工具调用结果列表)
    """
    print("Run Agent!!!")

    # 任务放行逻辑：如果该session已标记为"无房源"，直接返回，不调用模型和工具
    if _is_session_no_houses(session_id):
        print(f"Session {session_id} 已标记为无房源，直接返回无房源消息，跳过模型和工具调用")
        return "抱歉，根据之前的搜索结果，没有找到符合条件的房源。", []

    # 如果没有提供history，则使用空列表
    if history is None:
        history = []
    
    # 如果history为空，说明是新任务开始，重置session状态
    if len(history) == 0 and session_id:
        _reset_session_status(session_id)

    tool_results = []

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_message}]

    # 最多迭代5轮工具调用
    for _ in range(5):
        # 使用原有的OpenAI客户端
        print(f"iteration times:{_}")
        try:
            response = await build_llm_client(model_ip, session_id, messages)
            # 根据接口版本设置模型参数
        except Exception as e:
            print(f"Error calling model: {str(e)}")
            print(f"Error type: {type(e).__name__}")

            # 尝试获取更详细的错误信息
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status_code}")
                try:
                    print(f"Response content: {e.response.text}")
                except:
                    print("Could not read response content")

            import traceback
            traceback.print_exc()
            return f"模型调用失败: {str(e)}", tool_results

        # 安全地提取模型响应消息
        try:
            if hasattr(response, 'choices') and len(response.choices) > 0:
                msg = response.choices[0].message
            else:
                print(f"Invalid response format - no choices found")
                return "模型响应格式错误", tool_results
        except Exception as e:
            print(f"Error extracting message from response: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"响应解析失败: {str(e)}", tool_results

        # 检查是否有工具调用
        tool_calls = getattr(msg, 'tool_calls', None)
        print(f"Tool calls detected: {tool_calls is not None and len(tool_calls) > 0}")

        # 无工具调用，直接返回
        if not tool_calls or len(tool_calls) == 0:
            content = getattr(msg, 'content', '')
            print(f"No tool calls, returning content: {content[:100] if content else 'No content'}...")
            return content, tool_results

        # 处理工具调用
        print(f"Processing {len(tool_calls)} tool call(s)")
        tool_calls_data = []
        for tc in tool_calls:
            try:
                tool_call_data = {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                tool_calls_data.append(tool_call_data)
            except Exception as e:
                print(f"Error processing tool call data: {str(e)}")

        messages.append({
            "role": "assistant",
            "content": getattr(msg, 'content', ''),
            "tool_calls": tool_calls_data
        })

        # 执行工具调用
        for tc in tool_calls:
            func_name = tc.function.name
            func_args_str = tc.function.arguments

            try:
                func_args = json.loads(func_args_str)
                print(f"Executing tool！！！Tool func_name: {func_name}，Tool arguments: {func_args}")

                # 检查工具是否存在于映射中
                if func_name in TOOL_MAP:
                    result = TOOL_MAP[func_name](**func_args)
                    print(f"Tool execution result: {str(result)[:200]}...")
                else:
                    result = {"error": f"Unknown tool: {func_name}"}
                    print(f"Tool not found: {func_name}")
            except json.JSONDecodeError as e:
                result = {"error": f"Invalid JSON arguments: {str(e)}"}
                print(f"JSON decode error: {str(e)}")
            except Exception as e:
                result = {"error": str(e)}
                print(f"Tool execution error: {str(e)}")
                import traceback
                traceback.print_exc()

            tool_results.append({"tool": func_name, "args": func_args_str, "result": result})
            
            # 任务放行逻辑：如果调用的是搜索房源工具且结果为空，标记该session为"无房源"
            if func_name in HOUSE_SEARCH_TOOLS:
                if _is_house_search_result_empty(result):
                    _mark_session_no_houses(session_id)
                    print(f"检测到搜索房源工具 {func_name} 返回空结果，已标记session {session_id} 为无房源状态")
                
                # 优化：如果搜索房源工具返回了结果，直接生成JSON响应，避免再次调用模型
                direct_response = _generate_house_search_response(result)
                if direct_response:
                    print(f"搜索房源工具 {func_name} 返回结果，直接生成响应，跳过模型调用以节省token")
                    return direct_response, tool_results
            
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False)
            })

    return "处理超时，请重试", tool_results