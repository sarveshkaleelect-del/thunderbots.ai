"""
Execution Context — tracks state during workflow execution.
Serializable to/from dict for WebSocket session persistence.
"""
from __future__ import annotations
from typing import Optional


class ExecutionContext:
    def __init__(
        self,
        current_node_id: Optional[str] = None,
        variables: Optional[dict] = None,
        message_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        turn_count: int = 0,
        completed: bool = False,
    ):
        self.current_node_id = current_node_id
        self.variables: dict = variables or {}
        self._message_history: list[dict] = message_history or []
        self.session_id = session_id
        self.workflow_id = workflow_id
        self.turn_count = turn_count
        # ROOT CAUSE FIX: explicit terminal marker for the session. Previously
        # "workflow finished" was inferred solely from current_node_id pointing
        # at a node of type "end" — which meant a dead-end at any OTHER node
        # type (Start/Text/Multiple Choice/AI Agent/Transition with no outgoing
        # edge) had no way to record that the workflow was over. The runner
        # would leave current_node_id as None, which is indistinguishable from
        # "session never started", so the very next incoming message silently
        # re-initialized the workflow from the Start node — the "restarts /
        # jumps to unrelated nodes" bug. `completed` is the single authoritative
        # flag every termination path (End node OR any dead-end) sets, and the
        # only thing the runner checks before allowing any further execution.
        self.completed = completed

    def add_message(self, role: str, content: str, node_id: str = None) -> None:
        """
        ROOT CAUSE FIX: previously any call — including one with an empty
        string content — was appended to history verbatim. An empty entry
        doesn't fail on the turn it's created (most providers tolerate an
        empty string in isolation), only later, once get_message_history()
        replays it as part of a LATER turn's message list alongside real
        content — which is exactly what produces Anthropic's "'content'
        argument must not be empty" rejection on the second (or any
        subsequent) AI Agent turn. Refusing to persist an empty-content
        entry closes this at the source for every node type and every
        provider, not just Claude. `turn_count` still increments — a turn
        genuinely happened — only the empty message itself is dropped.
        """
        if content:
            self._message_history.append({
                "role": role,
                "content": content,
                "node_id": node_id,
            })
        self.turn_count += 1

    def get_message_history(self, limit: int = 10) -> list[dict]:
        """Return last N messages in OpenAI format (no node_id)."""
        msgs = self._message_history[-limit:]
        return [{"role": m["role"], "content": m["content"]} for m in msgs]

    def get_full_history(self) -> list[dict]:
        return list(self._message_history)

    def set_variable(self, key: str, value) -> None:
        self.variables[key] = value

    def get_variable(self, key: str, default=None):
        return self.variables.get(key, default)

    def to_dict(self) -> dict:
        return {
            "current_node_id": self.current_node_id,
            "variables": self.variables,
            "message_history": self._message_history,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "turn_count": self.turn_count,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionContext":
        return cls(
            current_node_id=data.get("current_node_id"),
            variables=data.get("variables", {}),
            message_history=data.get("message_history", []),
            session_id=data.get("session_id"),
            workflow_id=data.get("workflow_id"),
            turn_count=data.get("turn_count", 0),
            # Sessions persisted before this fix won't have this key — default
            # False preserves old behavior for them (falls back to the
            # type=="end" guard in the runner) rather than erroring.
            completed=data.get("completed", False),
        )

    def reset(self) -> None:
        self.current_node_id = None
        self.variables = {}
        self._message_history = []
        self.turn_count = 0
        self.completed = False

    def apply_from(self, other: "ExecutionContext") -> None:
        """
        Copy all state from `other` into self, in place.

        Needed by WorkflowRunner.stream_run(): as an async generator it has no
        return value, only yielded chunks, so the only way to hand its final
        execution state back to the caller is by mutating the SAME object the
        caller passed in. Previously, code paths inside stream_run did
        `context = ExecutionContext.from_dict(result["context"])`, which only
        rebinds stream_run's local variable to a brand-new object — the
        caller's original `context` reference (held by chat_ws.py across the
        whole WebSocket connection and persisted to Redis after each turn)
        was never updated. This silently discarded every state change inside
        a turn, including current_node_id, leaving sessions stuck on whatever
        node they were on before the turn began.
        """
        self.current_node_id = other.current_node_id
        self.variables = other.variables
        self._message_history = other._message_history
        self.session_id = other.session_id
        self.workflow_id = other.workflow_id
        self.turn_count = other.turn_count
        self.completed = other.completed
