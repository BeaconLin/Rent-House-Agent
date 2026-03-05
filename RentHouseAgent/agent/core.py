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
    # 格式1: {"data": {"total": 0, "items": []}} 或 {"data": {"total": 0}}
    # 格式2: {"data": [], "total": 0}
    # 格式3: {"houses": [], "total": 0}
    # 格式4: {"data": []} 或 {"houses": []}
    
    # 检查data字段
    if "data" in result:
        data = result.get("data", {})
        # 处理data是字典的情况（包含total和items字段）
        if isinstance(data, dict):
            # 检查data.total字段
            if "total" in data and data.get("total", 0) == 0:
                return True
            # 检查data.items字段
            if "items" in data:
                items = data.get("items", [])
                if isinstance(items, list) and len(items) == 0:
                    return True
        # 处理data是列表的情况（向后兼容）
        elif isinstance(data, list) and len(data) == 0:
            return True
    
    # 检查顶层total字段（向后兼容）
    if "total" in result:
        if result.get("total", 0) == 0:
            return True
    
    # 检查houses字段
    if "houses" in result:
        houses = result.get("houses", [])
        if isinstance(houses, list) and len(houses) == 0:
            return True
    
    return False


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
        data = result.get("data", {})
        # 处理data是字典的情况（包含items字段）
        if isinstance(data, dict) and "items" in data:
            items = data.get("items", [])
            if isinstance(items, list):
                for item in items[:max_count]:
                    if isinstance(item, dict) and "house_id" in item:
                        house_id = item.get("house_id")
                        if house_id:
                            house_ids.append(house_id)
        # 处理data是列表的情况（向后兼容）
        elif isinstance(data, list):
            for item in data[:max_count]:
                if isinstance(item, dict) and "house_id" in item:
                    house_id = item.get("house_id")
                    if house_id:
                        house_ids.append(house_id)
    
    return house_ids[:max_count]


def _has_special_requirements(user_message: str, history: List[dict]) -> bool:
    """
    检测用户消息或历史对话中是否包含特殊需求
    
    特殊需求包括：养宠物、附近有公园、VR看房、付款方式、费用包含等
    这些需求需要通过tags字段进行过滤，不能直接返回搜索结果
    
    Args:
        user_message: 当前用户消息
        history: 对话历史记录
        
    Returns:
        True表示包含特殊需求，False表示不包含
    """
    # 合并所有对话内容
    all_text = user_message.lower() if user_message else ""
    for msg in history:
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                all_text += " " + content.lower()
    
    # 特殊需求关键词
    special_keywords = [
        # 养宠物相关
        "养狗", "养猫", "养宠物", "能养狗", "能养猫", "允许养", "可养",
        "金毛", "宠物", "小型犬", "大型犬",
        # 公园相关
        "公园", "遛狗", "遛猫", "附近有公园", "近公园",
        # VR看房相关
        "vr", "vr看房", "线上看房", "不用跑现场", "远程看房", "视频看房",
        # 付款方式相关
        "月付", "季付", "半年付", "年付", "押一付", "付款方式",
        # 费用包含相关
        "包宽带", "包物业", "包网费", "费用包含", "宽带包含",
        # 其他特殊需求
        "可短租", "短租", "24小时保安", "地下车库", "车库", "停车",
        "免中介", "免押", "房东直租"
    ]
    
    # 检查是否包含特殊需求关键词
    for keyword in special_keywords:
        if keyword in all_text:
            print(f"检测到特殊需求关键词: {keyword}")
            return True
    
    return False


def _filter_houses_by_tags(result: dict, special_requirements: List[str]) -> List[str]:
    """
    根据特殊需求和tags字段过滤房源
    
    Args:
        result: 工具返回的结果字典
        special_requirements: 特殊需求列表，如["养狗", "公园", "VR看房"]
        
    Returns:
        符合条件的房源ID列表
    """
    house_ids = []
    
    if not isinstance(result, dict):
        return house_ids
    
    # 获取房源列表
    items = []
    if "data" in result and isinstance(result["data"], dict):
        items = result["data"].get("items", [])
    elif "data" in result and isinstance(result["data"], list):
        items = result["data"]
    elif "houses" in result:
        items = result["houses"]
    
    # 特殊需求与tags关键词的映射
    requirement_to_tags = {
        "养狗": ["允许养宠物", "可养宠物", "允许养狗", "仅限小型犬", "可养狗", "养狗"],
        "养猫": ["允许养宠物", "可养宠物", "允许养猫", "可养猫", "养猫"],
        "公园": ["近公园", "公园", "附近有公园"],
        "vr看房": ["vr", "vr看房", "线上看房", "远程看房", "视频看房"],
        "月付": ["月付", "押一付一"],
        "季付": ["季付", "押一付三"],
        "半年付": ["半年付", "押一付六"],
        "年付": ["年付", "押一付十二"],
        "包宽带": ["包宽带", "宽带", "网费"],
        "包物业": ["包物业", "物业费"],
        "可短租": ["可短租", "短租"],
        "24小时保安": ["24小时保安", "保安"],
        "地下车库": ["地下车库", "车库", "停车"],
    }
    
    # 为每个房源检查tags
    for item in items:
        if not isinstance(item, dict):
            continue
        
        house_id = item.get("house_id")
        if not house_id:
            continue
        
        tags = item.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        
        # 检查是否满足所有特殊需求
        meets_all_requirements = True
        for req in special_requirements:
            req_lower = req.lower()
            # 查找对应的tags关键词
            tag_keywords = []
            for key, keywords in requirement_to_tags.items():
                if key in req_lower:
                    tag_keywords.extend(keywords)
            
            # 如果没有找到映射，直接使用需求本身作为关键词
            if not tag_keywords:
                tag_keywords = [req]
            
            # 检查tags中是否包含任一关键词
            found = False
            for tag in tags:
                if not isinstance(tag, str):
                    continue
                tag_lower = tag.lower()
                for keyword in tag_keywords:
                    if keyword.lower() in tag_lower or tag_lower in keyword.lower():
                        found = True
                        break
                if found:
                    break
            
            if not found:
                meets_all_requirements = False
                break
        
        if meets_all_requirements:
            house_ids.append(house_id)
            if len(house_ids) >= 5:
                break
    
    return house_ids


def _generate_house_search_response(result: dict, user_message: str = "", history: List[dict] = None) -> Optional[str]:
    """
    从搜索房源工具的结果中直接生成JSON响应，避免再次调用模型
    
    如果用户提出了特殊需求（需要通过tags过滤），则返回None让模型处理

    Args:
        result: 工具返回的结果字典
        user_message: 当前用户消息（用于检测特殊需求）
        history: 对话历史记录（用于检测特殊需求）

    Returns:
        如果可以直接生成响应，返回JSON字符串；否则返回None（让模型处理tags过滤）
    """
    # 检查结果是否为空
    if _is_house_search_result_empty(result):
        return json.dumps({"message": "没有找到符合条件的房源", "houses": []}, ensure_ascii=False)
    
    # 检查是否有特殊需求
    if history is None:
        history = []
    
    if _has_special_requirements(user_message, history):
        print("检测到特殊需求，需要根据tags字段过滤，返回None让模型处理")
        return None
    
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

    # 如果没有提供history，则使用空列表
    if history is None:
        history = []

    tool_results = []

    # 构建系统提示，如果有特殊需求则添加额外提示
    system_prompt = SYSTEM_PROMPT
    if _has_special_requirements(user_message, history if history else []):
        system_prompt += "\n\n⚠️ **当前对话包含特殊需求（需要通过tags字段过滤）**\n"
        system_prompt += "**重要提示**：调用search_houses时，建议使用较大的page_size（如20-30），以确保tags过滤后有足够的房源可选。\n"
        system_prompt += "如果只搜索10个房源，经过tags过滤后可能符合条件的房源很少。\n"
        print("检测到特殊需求，已在系统提示中添加page_size建议")

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]

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
            
            # 优化：如果搜索房源工具返回了结果，检查是否有特殊需求
            # 如果有特殊需求，需要让模型根据tags字段过滤，不能直接返回
            if func_name in HOUSE_SEARCH_TOOLS:
                direct_response = _generate_house_search_response(result, user_message, history)
                if direct_response:
                    print(f"搜索房源工具 {func_name} 返回结果，直接生成响应，跳过模型调用以节省token")
                    return direct_response, tool_results
                else:
                    print(f"搜索房源工具 {func_name} 返回结果，但检测到特殊需求，需要模型根据tags字段过滤")
            
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False)
            })

    return "处理超时，请重试", tool_results