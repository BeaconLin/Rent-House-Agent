from typing import Dict, List
from collections import defaultdict


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, List[dict]] = defaultdict(list)

    def get_history(self, session_id: str) -> List[dict]:
        return self._sessions[session_id]

    def add_message(self, session_id: str, role: str, content: str):
        self._sessions[session_id].append({"role": role, "content": content})

    def clear(self, session_id: str):
        self._sessions[session_id] = []


session_manager = SessionManager()