"""
LLM Request/Response Logger.

Captures full LLM interactions for debugging and analysis.
Each thread gets its own log file with timestamped entries.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Default log directory
LOG_DIR = Path(__file__).parent / "llm_logs"


class LLMLogger:
    """Logger for LLM requests and responses."""
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or LOG_DIR
        self.log_dir.mkdir(exist_ok=True)
        self._turn_counters: dict[str, int] = {}  # Track turn number per thread
        self._log_callbacks: dict[str, Callable[[dict], None]] = {}  # Per-thread callbacks for real-time updates
    
    def set_log_callback(self, thread_id: str, callback: Optional[Callable[[dict], None]]) -> None:
        """
        Set a callback to be called when log entries are written for a thread.
        
        Args:
            thread_id: Thread ID to set callback for
            callback: Function that receives the log entry dict, or None to clear
        """
        if callback is None:
            self._log_callbacks.pop(thread_id, None)
        else:
            self._log_callbacks[thread_id] = callback
    
    def _get_log_path(self, thread_id: str) -> Path:
        """Get log file path for a thread."""
        # Sanitize thread_id for filename
        safe_id = thread_id.replace("-", "")[:16]
        return self.log_dir / f"thread_{safe_id}.jsonl"
    
    def start_turn(self, thread_id: str) -> int:
        """Start a new turn and return the turn number."""
        if thread_id not in self._turn_counters:
            # Load existing turn count from logs
            logs = self.get_logs(thread_id, limit=1000)
            max_turn = 0
            for log in logs:
                if "turn" in log:
                    max_turn = max(max_turn, log["turn"])
            self._turn_counters[thread_id] = max_turn
        
        self._turn_counters[thread_id] += 1
        return self._turn_counters[thread_id]
    
    def get_current_turn(self, thread_id: str) -> int:
        """Get the current turn number for a thread."""
        return self._turn_counters.get(thread_id, 0)
    
    def log_request(
        self,
        thread_id: str,
        provider: str,
        model: str,
        messages: list[dict],
        tools: list[dict],
        system_prompt: Optional[str] = None,
        turn: Optional[int] = None,
    ) -> str:
        """
        Log an LLM request.
        
        Returns:
            Request ID for correlation with response
        """
        request_id = f"req_{datetime.now().strftime('%H%M%S%f')}"
        
        entry = {
            "type": "request",
            "request_id": request_id,
            "turn": turn or self.get_current_turn(thread_id),
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt[:500] + "..." if system_prompt and len(system_prompt) > 500 else system_prompt,
            "system_prompt_length": len(system_prompt) if system_prompt else 0,
            "messages": self._summarize_messages(messages),
            "message_count": len(messages),
            "tools_count": len(tools),
            "tool_names": [self._get_tool_name(t) for t in tools[:20]],  # First 20 tool names
        }
        
        self._write_entry(thread_id, entry)
        return request_id
    
    def log_response(
        self,
        thread_id: str,
        request_id: str,
        content: str,
        tool_calls: list[dict],
        stop_reason: str,
        usage: dict[str, int],
        error: Optional[str] = None,
        turn: Optional[int] = None,
    ) -> None:
        """Log an LLM response."""
        entry = {
            "type": "response",
            "request_id": request_id,
            "turn": turn or self.get_current_turn(thread_id),
            "timestamp": datetime.now().isoformat(),
            "content": content[:2000] + "..." if len(content) > 2000 else content,
            "content_length": len(content),
            "tool_calls": [
                {"id": tc.get("id", ""), "name": tc.get("name", ""), "args_preview": str(tc.get("args", {}))[:200]}
                for tc in tool_calls
            ] if tool_calls else [],
            "stop_reason": stop_reason,
            "usage": usage,
            "error": error,
        }
        
        self._write_entry(thread_id, entry)
    
    def log_tool_execution(
        self,
        thread_id: str,
        tool_name: str,
        arguments: dict,
        result: str,
        duration_ms: int,
        error: Optional[str] = None,
        turn: Optional[int] = None,
    ) -> None:
        """Log a tool execution."""
        entry = {
            "type": "tool_execution",
            "turn": turn or self.get_current_turn(thread_id),
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "arguments": self._truncate_dict(arguments, 500),
            "result_preview": result[:1000] + "..." if len(result) > 1000 else result,
            "result_length": len(result),
            "duration_ms": duration_ms,
            "error": error,
        }
        
        self._write_entry(thread_id, entry)
    
    def get_logs(self, thread_id: str, limit: int = 50) -> list[dict]:
        """
        Get recent logs for a thread.
        
        Args:
            thread_id: Thread ID
            limit: Maximum number of entries to return
            
        Returns:
            List of log entries, most recent first
        """
        log_path = self._get_log_path(thread_id)
        if not log_path.exists():
            return []
        
        entries = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Failed to read logs for {thread_id}: {e}")
            return []
        
        # Return most recent entries first
        return list(reversed(entries[-limit:]))
    
    def get_tool_usage(self, thread_id: str) -> dict:
        """
        Get tool usage statistics for a thread.
        
        Returns:
            Dict with tool counts and list of tools used
        """
        log_path = self._get_log_path(thread_id)
        if not log_path.exists():
            return {"tools": {}, "total_calls": 0}
        
        tool_counts = {}
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            if entry.get("type") == "tool_execution":
                                tool_name = entry.get("tool_name", "unknown")
                                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Failed to read tool usage for {thread_id}: {e}")
            return {"tools": {}, "total_calls": 0}
        
        return {
            "tools": tool_counts,
            "total_calls": sum(tool_counts.values()),
        }
    
    def clear_logs(self, thread_id: str) -> bool:
        """Clear logs for a thread."""
        log_path = self._get_log_path(thread_id)
        try:
            if log_path.exists():
                log_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to clear logs for {thread_id}: {e}")
            return False
    
    def _write_entry(self, thread_id: str, entry: dict) -> None:
        """Write a log entry to the thread's log file."""
        log_path = self._get_log_path(thread_id)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            
            # Call callback for real-time updates if registered
            callback = self._log_callbacks.get(thread_id)
            if callback:
                try:
                    callback(entry)
                except Exception as e:
                    logger.error(f"Log callback error: {e}")
        except Exception as e:
            logger.error(f"Failed to write log entry: {e}")
    
    def _summarize_messages(self, messages: list[dict]) -> list[dict]:
        """Create a summary of messages for logging."""
        summaries = []
        for msg in messages[-10:]:  # Last 10 messages
            summary = {
                "role": msg.get("role", "unknown"),
            }
            
            content = msg.get("content", "")
            if isinstance(content, str):
                summary["content_preview"] = content[:200] + "..." if len(content) > 200 else content
                summary["content_length"] = len(content)
            elif isinstance(content, list):
                # Anthropic format with content blocks
                summary["content_blocks"] = len(content)
                
            if msg.get("tool_calls"):
                summary["tool_calls"] = len(msg["tool_calls"])
            if msg.get("tool_call_id"):
                summary["tool_call_id"] = msg["tool_call_id"]
                
            summaries.append(summary)
        
        return summaries
    
    def _get_tool_name(self, tool: dict) -> str:
        """Extract tool name from tool definition."""
        if "function" in tool:
            return tool["function"].get("name", "unknown")
        return tool.get("name", "unknown")
    
    def _truncate_dict(self, d: dict, max_str_len: int = 200) -> dict:
        """Truncate string values in a dict for logging."""
        result = {}
        for k, v in d.items():
            if isinstance(v, str) and len(v) > max_str_len:
                result[k] = v[:max_str_len] + "..."
            elif isinstance(v, dict):
                result[k] = self._truncate_dict(v, max_str_len)
            else:
                result[k] = v
        return result


# Global logger instance
_llm_logger: Optional[LLMLogger] = None


def get_llm_logger() -> LLMLogger:
    """Get the global LLM logger instance."""
    global _llm_logger
    if _llm_logger is None:
        _llm_logger = LLMLogger()
    return _llm_logger
