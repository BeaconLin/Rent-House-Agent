import json
import httpx
import os
import asyncio
from typing import List, Tuple, Optional, Dict, Any
from agent.tools import TOOLS, search_houses, get_house_detail, get_houses_nearby, search_landmark, get_house_listings, \
    get_nearby_landmarks, get_landmarks, get_landmark_by_name, get_landmark_by_id, get_landmark_stats, \
    get_houses_by_community, get_house_stats, rent_house, terminate_rental, take_offline
from agent.prompts import SYSTEM_PROMPT

# 对话历史最大保留轮数（每轮包含user和assistant两条消息）
MAX_HISTORY_ROUNDS = 10

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


def compress_tool_result(tool_name: str, result: Dict[str, Any]) -> str:
    """
    压缩工具调用结果，只保留关键字段以减少token消耗
    
    Args:
        tool_name: 工具名称
        result: 工具返回的完整结果
    
    Returns:
        压缩后的JSON字符串
    """
    if not isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    
    compressed = {}
    
    # 处理API返回的标准格式：{"code": 0, "message": "success", "data": {...}}
    # 如果存在data字段，则从data中提取实际数据
    actual_data = result.get("data", result) if "data" in result else result
    
    if tool_name == "search_houses":
        # 只保留关键字段：总数、房源列表（每个房源只保留ID、价格、区域、tags等关键信息）
        # API返回格式：{"code": 0, "data": {"total": 6, "items": [...]}}
        if "total" in actual_data:
            compressed["total"] = actual_data["total"]
        # 房源列表可能在 "items" 或 "houses" 字段中
        houses_list = actual_data.get("items") or actual_data.get("houses")
        if houses_list and isinstance(houses_list, list):
            compressed["houses"] = []
            for house in houses_list[:10]:  # 最多保留10个房源
                # 只添加有有效house_id的房源
                house_id = house.get("house_id")
                if house_id:  # 确保house_id不为None或空字符串
                    house_compressed = {
                        "house_id": house_id,
                        "price": house.get("price"),
                        "district": house.get("district"),
                        "area": house.get("area"),
                        "community": house.get("community"),
                        "bedrooms": house.get("bedrooms"),
                        "tags": house.get("tags", [])
                    }
                    compressed["houses"].append(house_compressed)
    
    elif tool_name == "get_house_detail":
        # 只保留关键字段
        # API返回格式：{"code": 0, "data": {...}}
        compressed = {
            "house_id": actual_data.get("house_id"),
            "price": actual_data.get("price"),
            "district": actual_data.get("district"),
            "area": actual_data.get("area"),
            "community": actual_data.get("community"),
            "bedrooms": actual_data.get("bedrooms"),
            "tags": actual_data.get("tags", []),
            "available": actual_data.get("available")
        }
    
    elif tool_name in ["get_houses_nearby", "get_houses_by_community"]:
        # 类似search_houses的压缩策略
        # API返回格式：{"code": 0, "data": {"total": 6, "items": [...]}}
        if "total" in actual_data:
            compressed["total"] = actual_data["total"]
        # 房源列表可能在 "items" 或 "houses" 字段中
        houses_list = actual_data.get("items") or actual_data.get("houses")
        if houses_list and isinstance(houses_list, list):
            compressed["houses"] = []
            for house in houses_list[:10]:
                # 只添加有有效house_id的房源
                house_id = house.get("house_id")
                if house_id:  # 确保house_id不为None或空字符串
                    house_compressed = {
                        "house_id": house_id,
                        "price": house.get("price"),
                        "district": house.get("district"),
                        "area": house.get("area"),
                        "community": house.get("community"),
                        "bedrooms": house.get("bedrooms")
                    }
                    compressed["houses"].append(house_compressed)
    
    elif tool_name == "search_landmark":
        # 只保留地标列表的关键信息
        # API返回格式：{"code": 0, "data": {"landmarks": [...]}}
        landmarks_list = actual_data.get("landmarks")
        if landmarks_list and isinstance(landmarks_list, list):
            compressed["landmarks"] = []
            for landmark in landmarks_list[:5]:  # 最多保留5个地标
                compressed["landmarks"].append({
                    "landmark_id": landmark.get("landmark_id"),
                    "name": landmark.get("name"),
                    "category": landmark.get("category")
                })
    
    elif tool_name == "get_house_listings":
        # 只保留各平台价格信息
        # API返回格式：{"code": 0, "data": {"listings": [...]}}
        listings_list = actual_data.get("listings")
        if listings_list and isinstance(listings_list, list):
            compressed["listings"] = []
            for listing in listings_list:
                compressed["listings"].append({
                    "platform": listing.get("listing_platform"),
                    "price": listing.get("price")
                })
    
    else:
        # 其他工具保留完整结果，但限制大小
        compressed = result
    
    return json.dumps(compressed, ensure_ascii=False)


def compress_history(history: List[dict]) -> List[dict]:
    """
    压缩对话历史，只保留最近的N轮对话
    
    Args:
        history: 完整的对话历史
    
    Returns:
        压缩后的对话历史
    """
    if not history:
        return []
    
    # 计算轮数（每轮包含user和assistant两条消息）
    rounds = []
    current_round = []
    
    for msg in history:
        if msg.get("role") == "user":
            if current_round:
                rounds.append(current_round)
            current_round = [msg]
        elif msg.get("role") in ["assistant", "tool"]:
            current_round.append(msg)
    
    if current_round:
        rounds.append(current_round)
    
    # 只保留最近的N轮
    if len(rounds) > MAX_HISTORY_ROUNDS:
        rounds = rounds[-MAX_HISTORY_ROUNDS:]
    
    # 展平列表
    compressed = []
    for round_msgs in rounds:
        compressed.extend(round_msgs)
    
    return compressed


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


def _is_retryable_error(error: Exception) -> bool:
    """
    判断错误是否可重试
    
    Args:
        error: 异常对象
    
    Returns:
        bool: 是否可重试
    """
    # 可重试的错误类型
    retryable_errors = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.NetworkError,
        httpx.ReadError,
        httpx.WriteError,
        httpx.PoolTimeout,
        ConnectionError,
        TimeoutError,
        OSError,  # 网络相关的OS错误
    )
    
    # 检查是否是这些错误类型
    if isinstance(error, retryable_errors):
        return True
    
    # 检查错误消息中是否包含可重试的关键词
    error_str = str(error).lower()
    retryable_keywords = [
        "timeout",
        "connection",
        "network",
        "temporary",
        "retry",
        "503",  # Service Unavailable
        "502",  # Bad Gateway
        "504",  # Gateway Timeout
    ]
    
    return any(keyword in error_str for keyword in retryable_keywords)


async def build_llm_client(
    model_ip: Optional[str] = None, 
    session_id: Optional[str] = None, 
    messages: [] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0
):
    """
    构建OpenAI客户端并调用模型，带重试机制

    Args:
        model_ip: 模型服务器IP地址，如果为None则从环境变量获取
                  如果为"deepseek"，则使用DeepSeek API
        session_id: 会话ID，如果提供则添加到请求头中
        messages: 消息列表
        max_retries: 最大重试次数，默认3次
        retry_delay: 初始重试延迟（秒），默认1秒，会指数退避

    Returns:
        OpenAI响应对象

    Raises:
        Exception: 如果所有重试都失败，抛出最后一次的异常
    """
    from openai import AsyncOpenAI
    from openai import APIError, APIConnectionError, APITimeoutError

    # 如果提供了Session-ID，则添加到默认请求头
    default_headers = {}
    if session_id:
        default_headers["Session-ID"] = session_id

    # 默认使用本地模型服务器
    base_url = f"http://{model_ip}:8888/v1"

    last_error = None
    current_delay = retry_delay
    
    # 重试循环
    for attempt in range(max_retries + 1):  # 0到max_retries，共max_retries+1次尝试
        http_client = None
        try:
            # 每次重试都创建新的客户端，避免连接问题
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

            response = await client.chat.completions.create(
                model="qwen3-32b",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.1,  # 降低温度以获得更确定性的输出
                stream=False,
                top_p=0.9  # 添加top_p参数进一步限制输出范围
            )
            
            # 成功则关闭客户端并返回
            if http_client:
                await http_client.aclose()
            
            if attempt > 0:
                print(f"模型调用成功（第{attempt + 1}次尝试）")
            return response
            
        except (APIError, APIConnectionError, APITimeoutError) as e:
            # OpenAI SDK 特定的错误，通常是可重试的
            last_error = e
            error_type = type(e).__name__
            error_msg = str(e)
            
            # 关闭客户端
            if http_client:
                try:
                    await http_client.aclose()
                except:
                    pass
            
            # 判断是否可重试
            is_retryable = _is_retryable_error(e)
            
            # 如果是最后一次尝试或错误不可重试，则不再重试
            if attempt >= max_retries or not is_retryable:
                if not is_retryable:
                    print(f"模型调用失败（不可重试的错误）: {error_type} - {error_msg}")
                else:
                    print(f"模型调用失败（已重试{max_retries}次）: {error_type} - {error_msg}")
                import traceback
                traceback.print_exc()
                raise
            
            # 可重试的错误，等待后重试
            print(f"模型调用失败（第{attempt + 1}次尝试）: {error_type} - {error_msg}")
            print(f"等待 {current_delay:.2f} 秒后重试...")
            
            await asyncio.sleep(current_delay)
            
            # 指数退避：每次重试延迟时间翻倍，但最多不超过10秒
            current_delay = min(current_delay * 2, 10.0)
            
        except Exception as e:
            # 其他类型的错误
            last_error = e
            error_type = type(e).__name__
            error_msg = str(e)
            
            # 关闭客户端
            if http_client:
                try:
                    await http_client.aclose()
                except:
                    pass
            
            # 判断是否可重试
            is_retryable = _is_retryable_error(e)
            
            # 如果是最后一次尝试或错误不可重试，则不再重试
            if attempt >= max_retries or not is_retryable:
                if not is_retryable:
                    print(f"模型调用失败（不可重试的错误）: {error_type} - {error_msg}")
                else:
                    print(f"模型调用失败（已重试{max_retries}次）: {error_type} - {error_msg}")
                import traceback
                traceback.print_exc()
                raise
            
            # 可重试的错误，等待后重试
            print(f"模型调用失败（第{attempt + 1}次尝试）: {error_type} - {error_msg}")
            print(f"等待 {current_delay:.2f} 秒后重试...")
            
            await asyncio.sleep(current_delay)
            
            # 指数退避：每次重试延迟时间翻倍，但最多不超过10秒
            current_delay = min(current_delay * 2, 10.0)
    
    # 如果所有重试都失败，抛出最后一次的异常
    if last_error:
        raise last_error


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

    # 如果没有提供history，则使用空列表
    if history is None:
        history = []

    # 压缩对话历史
    history = compress_history(history)

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
            
            # 压缩工具调用结果以减少token消耗
            compressed_result = compress_tool_result(func_name, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": compressed_result
            })

    return "处理超时，请重试", tool_results