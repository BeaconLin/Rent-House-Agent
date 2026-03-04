import time
import json
import logging
import sys
import traceback
from datetime import datetime
from threading import Lock
from fastapi import FastAPI, HTTPException
from models.schemas import ChatRequest, ChatResponse, V2ChatRequest, V2ChatResponse
from session.manager import session_manager
from agent.core import run_agent

# ======================== 常量定义 ========================
# 日志配置
LOG_FILE = 'logs/yxy.log'
# 房源相关工具名称
HOUSE_TOOLS = {
    'search_houses', 'get_houses_nearby', 'get_houses_by_community',
    'get_house_detail', 'rent_house', 'terminate_rental', 'take_offline'
}
# 会话清理阈值（可根据实际情况调整）
SESSION_CLEANUP_THRESHOLD = 10000

# ======================== 日志配置 ========================
# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 重定向print到日志
class PrintToLogger:
    def __init__(self, logger):
        self.logger = logger

    def write(self, message):
        if message.strip():  # 只记录非空消息
            self.logger.info(message.strip())

    def flush(self):
        pass

# 先重定向再打印初始化信息
sys.stdout = PrintToLogger(logger)
print("=== 日志系统初始化完成 ===")
print(f"日志文件路径: {LOG_FILE}")

# ======================== 应用初始化 ========================
app = FastAPI(title="租房AI Agent", version="1.0.0")

# 线程安全的任务计数器和会话ID集合
task_counter = 0
processed_session_ids = set()
counter_lock = Lock()

# ======================== 工具函数 ========================
def is_house_tool_called(tool_results: list) -> bool:
    """
    检查是否调用了房源相关工具
    
    Args:
        tool_results: 工具调用结果列表
    
    Returns:
        bool: 是否调用了房源工具
    """
    return any(
        tool_result.get('tool') in HOUSE_TOOLS
        for tool_result in tool_results
    )

def parse_agent_response(response_text: str, has_house_tool_call: bool) -> tuple:
    """
    解析Agent返回的响应文本
    
    Args:
        response_text: Agent返回的文本
        has_house_tool_call: 是否调用了房源工具
    
    Returns:
        tuple: (message, houses)
    """
    message = None
    houses = None
    
    if not response_text:
        return message, houses
    
    try:
        # 尝试解析为JSON
        parsed_response = json.loads(response_text)
        if isinstance(parsed_response, dict):
            message = parsed_response.get("message")
            houses = parsed_response.get("houses")
            
            # 检查JSON格式是否符合要求
            if has_house_tool_call and (message is None or houses is None):
                logger.warning(f"⚠️ 调用了房源工具但返回的JSON格式不符合要求")
                logger.warning(f"原始响应: {response_text}")
    except (json.JSONDecodeError, TypeError) as e:
        # 不是JSON格式
        if has_house_tool_call:
            logger.warning(f"⚠️ 调用了房源工具但返回的不是JSON格式")
            logger.warning(f"原始响应: {response_text}")
            logger.warning(f"解析错误: {str(e)}")
        else:
            logger.info("response_text为普通文本，不进行JSON解析")
    
    return message, houses

def cleanup_old_sessions():
    """清理过期的会话ID，防止内存泄漏"""
    global processed_session_ids
    with counter_lock:
        if len(processed_session_ids) > SESSION_CLEANUP_THRESHOLD:
            # 可以根据实际需求实现更智能的清理策略
            # 这里简单保留最新的10000个会话ID
            processed_session_ids = set(list(processed_session_ids)[-SESSION_CLEANUP_THRESHOLD:])
            logger.info(f"清理了过期会话，当前会话数: {len(processed_session_ids)}")

# ======================== API接口 ========================
@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    处理聊天请求
    
    Args:
        req: 聊天请求对象，包含session_id、message、model_ip等
    
    Returns:
        ChatResponse: 结构化的聊天响应
    """
    global task_counter, processed_session_ids
    
    # 记录请求开始时间
    start_time = time.time()
    start_ms = int(start_time * 1000)
    
    try:
        # 线程安全地更新任务计数器
        with counter_lock:
            if req.session_id not in processed_session_ids:
                task_counter += 1
                processed_session_ids.add(req.session_id)
                print(f"=== 第{task_counter}个任务 ===")
                
                # 定期清理过期会话
                cleanup_old_sessions()
        
        # 日志记录请求信息
        logger.info(f"=== 接收到请求 ===")
        logger.info(f'session_id:{req.session_id}')
        logger.info(f'！！！ask message:{req.message}')

        # 获取会话历史
        history = session_manager.get_history(req.session_id)
        logger.info(f'history:{history}')
        
        # 运行Agent处理请求
        response_text, tool_results = await run_agent(req.model_ip, history, req.message, req.session_id)
        logger.info(f"！！！response_text------{response_text}")

        # 解析Agent响应
        has_house_tool_call = is_house_tool_called(tool_results)
        message, houses = parse_agent_response(response_text, has_house_tool_call)

        # 保存会话上下文
        session_manager.add_message(req.session_id, "user", req.message)
        session_manager.add_message(req.session_id, "assistant", response_text or "")

        # 计算耗时
        end_ms = int(time.time() * 1000)
        duration_ms = end_ms - start_ms

        # 构建成功响应
        return ChatResponse(
            session_id=req.session_id,
            response=response_text or "",
            status="success",
            tool_results=tool_results,
            timestamp=int(start_time),  # 使用请求开始时间作为时间戳
            duration_ms=duration_ms,
            message=message,
            houses=houses
        )

    except HTTPException as e:
        # 处理HTTP异常（FastAPI标准异常）
        logger.error(f"HTTP异常: {str(e)}")
        end_ms = int(time.time() * 1000)
        return ChatResponse(
            session_id=req.session_id,
            response=f"请求错误：{str(e.detail)}",
            status="error",
            tool_results=[],
            timestamp=int(start_time),
            duration_ms=end_ms - start_ms,
            message=None,
            houses=None
        )
    except Exception as e:
        # 处理其他异常
        error_trace = traceback.format_exc()
        logger.error(f"服务异常: {str(e)}\n{error_trace}")
        
        end_ms = int(time.time() * 1000)
        return ChatResponse(
            session_id=req.session_id,
            response=f"服务异常：{str(e)}",
            status="error",
            tool_results=[],
            timestamp=int(start_time),
            duration_ms=end_ms - start_ms,
            message=None,
            houses=None
        )

# ======================== 启动服务 ========================
if __name__ == "__main__":
    import uvicorn
    import asyncio

    async def main():
        """启动FastAPI服务"""
        config = uvicorn.Config(
            app, 
            host="0.0.0.0", 
            port=8080,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

    print("=== 启动FastAPI应用 ===")
    print("访问地址: http://localhost:8080")
    print("API文档: http://localhost:8080/docs")
    asyncio.run(main())