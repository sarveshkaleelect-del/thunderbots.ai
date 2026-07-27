"""
ThunderBots Workflow Runner v5
FIX: stream_run — context.current_node_id updated from runner state, not from
     WS chunk. This eliminates duplicate responses caused by double context writes.
FIX: Multiple-choice nodes never auto-advance — they always stop and return
     to the user, even when arrived at via auto-advance chain.
FIX: Guard against infinite loops: if runner detects same node repeated
     more than 3 times in a row, it stops.
"""
from __future__ import annotations
from typing import AsyncIterator, Optional

from app.engine.context import ExecutionContext
from app.engine.node_handlers import NODE_HANDLERS, AIAgentNodeHandler


class WorkflowRunner:
    MAX_HOPS = 25
    # Node types that pause for user input — never auto-advanced
    USER_FACING = {"multiple_choice", "ai_agent"}

    def __init__(self, workflow: dict, user_id: Optional[str] = None):
        self.workflow = workflow
        self.user_id = user_id
        self.nodes: dict[str, dict] = {
            n["id"]: n for n in workflow.get("nodes", []) if "id" in n
        }
        self.edges: list[dict] = workflow.get("edges", [])

        self.adj: dict[str, list[tuple[str, str]]] = {}
        for edge in self.edges:
            src = edge.get("source")
            if not src:
                continue
            handle = edge.get("sourceHandle") or "output_0"
            if src not in self.adj:
                self.adj[src] = []
            self.adj[src].append((edge.get("target", ""), handle))

    def _get_start_node(self) -> Optional[dict]:
        for node in self.nodes.values():
            if node.get("type") == "start":
                return node
        return None

    def _get_handler(self, node: dict):
        node_type = node.get("type", "")
        handler_cls = NODE_HANDLERS.get(node_type)
        if not handler_cls:
            raise ValueError(f"Unknown node type: '{node_type}'")
        h = handler_cls(node, self.adj, self.nodes)
        h.user_id = self.user_id
        return h

    async def run(self, user_message: str, context: ExecutionContext) -> dict:
        # ROOT CAUSE FIX: `completed` is the single authoritative terminal
        # marker, set by this runner the instant a workflow ends for ANY
        # reason (explicit End node OR a dead-end node with no outgoing edge
        # on the selected path). It is checked before anything else — before
        # even resolving a Start node — so a completed session can never be
        # silently resumed, restarted, or advanced regardless of what
        # current_node_id happens to hold.
        if context.completed:
            return {
                "response": None,
                "next_node_id": None,
                "context": context.to_dict(),
                "ended": True,
                "choices": None,
                "citations": [],
                "node_type": "completed",
            }

        current_node_id = context.current_node_id

        if not current_node_id:
            start = self._get_start_node()
            if not start:
                return {
                    "response": "This workflow has no Start node.",
                    "next_node_id": None,
                    "context": context.to_dict(),
                    "ended": True,
                    "choices": None,
                    "citations": [],
                    "node_type": "error",
                }
            current_node_id = start["id"]

        # Terminal-state guard for sessions persisted before the `completed`
        # flag existed (back-compat only — new sessions are already caught
        # by the check above). If the session already landed on an End node,
        # any further message would otherwise re-execute it and re-emit its
        # goodbye message indefinitely.
        existing_node = self.nodes.get(current_node_id)
        if existing_node and existing_node.get("type") == "end":
            context.completed = True
            return {
                "response": None,
                "next_node_id": None,
                "context": context.to_dict(),
                "ended": True,
                "choices": None,
                "citations": [],
                "node_type": "end",
            }

        responses = []
        choices = None
        image = None
        citations = []
        hops = 0
        last_node_repeat = 0
        last_seen_node = None

        while hops < self.MAX_HOPS:
            hops += 1
            node = self.nodes.get(current_node_id)
            if not node:
                break

            # Infinite loop guard
            if current_node_id == last_seen_node:
                last_node_repeat += 1
                if last_node_repeat > 3:
                    break
            else:
                last_node_repeat = 0
                last_seen_node = current_node_id

            handler = self._get_handler(node)
            result = await handler.execute(user_message, context)
            context = ExecutionContext.from_dict(result["context"])

            if result.get("response"):
                responses.append(result["response"])
            if result.get("choices"):
                choices = result["choices"]
            if result.get("image"):
                image = result["image"]
            if result.get("citations"):
                citations = result["citations"]

            if result.get("ended"):
                context.completed = True
                return {
                    "response": "\n\n".join(responses),
                    "next_node_id": None,
                    "context": context.to_dict(),
                    "ended": True,
                    "choices": choices,
                    "image": image,
                    "citations": citations,
                    "node_type": result.get("node_type"),
                }

            next_id = result.get("next_node_id")
            node_type = result.get("node_type")

            # ROOT CAUSE FIX: the single choke point every handler's result
            # passes through. A node (or the specific output/handle selected
            # on it — a choice, a transition branch, an AI Agent configured
            # not to stay) with NO outgoing edge must terminate the workflow
            # immediately: never search for another node, never fall through
            # to auto-advance, and never leave current_node_id as None (which
            # is indistinguishable from "session never started" and would
            # silently restart from Start on the next message). This applies
            # uniformly to every node type, including any future custom node,
            # because it runs before any node-type-specific branching below.
            if next_id is None:
                context.current_node_id = current_node_id
                context.completed = True
                return {
                    "response": "\n\n".join(responses) if responses else "",
                    "next_node_id": None,
                    "context": context.to_dict(),
                    "ended": True,
                    "choices": choices,
                    "image": image,
                    "citations": citations,
                    "node_type": node_type,
                }

            # User-facing nodes stop the turn so the user can respond — EXCEPT
            # a multiple_choice node that just resolved a successful match
            # (result["choice_made"] is set). That node already consumed the
            # user's input this turn; it isn't waiting on anything anymore, so
            # it must fall through to auto-advance like a transition node does.
            # FIX (root cause): previously ALL multiple_choice results stopped
            # here unconditionally, which meant a choice's destination node
            # (e.g. an end node, or another text_card) never executed in the
            # same turn as the click — the user saw nothing happen until they
            # sent an unrelated extra message, which then silently executed
            # the skipped node out of context. This is the second mechanism
            # (distinct from the text_card bug) behind "must send two messages
            # before the workflow advances" and "connected nodes are skipped".
            is_resolved_choice = node_type == "multiple_choice" and result.get("choice_made")
            if node_type in self.USER_FACING and not is_resolved_choice:
                context.current_node_id = next_id
                return {
                    "response": "\n\n".join(responses) if responses else "",
                    "next_node_id": next_id,
                    "context": context.to_dict(),
                    "ended": False,
                    "choices": choices,
                    "image": image,
                    "citations": citations,
                    "node_type": node_type,
                    "provider": result.get("provider"),
                }

            # Auto-advance through invisible nodes (plus resolved-choice multiple_choice).
            # ROOT CAUSE FIX: previously this blanked user_message for ALL of
            # transition/start/text_card uniformly. That's correct for
            # transition and text_card (neither one consumes the user's
            # message), but WRONG for start — start is the entry point and
            # hasn't consumed anything yet, so the user's actual first message
            # is meant for whatever node comes after it. In a "Start -> AI
            # Agent" graph (an extremely common, simplest-possible workflow
            # shape), this silently replaced the user's real question with an
            # empty string, breaking BOTH the LLM response (which saw an
            # empty turn) AND Knowledge Base retrieval (a falsy empty query
            # short-circuited "if kb_id and user_message:" entirely, so RAG
            # context was never fetched on a bot's very first response).
            # ROOT CAUSE FIX: "condition" behaves exactly like "transition"
            # here — it never emits a visible response and never consumes
            # the user's message, it only picks an outgoing edge — so it
            # must auto-advance the same way, instead of falling through to
            # "Default: stop and return" below and incorrectly handing
            # control back to the user at a node that has no message to show.
            if (node_type in ("transition", "text_card", "condition")) and next_id:
                current_node_id = next_id
                user_message = ""
                continue
            if is_resolved_choice and next_id:
                current_node_id = next_id
                # ROOT CAUSE FIX: a resolved multiple_choice node, unlike
                # transition/text_card, DOES consume real user input — the
                # option they picked. Blanking it to "" here meant that when
                # the next node is an AI Agent (the exact "start ->
                # multiple_choice -> ai_agent" shape every marketplace
                # template uses), the agent's very first turn carried an
                # empty user message. Some providers tolerate an empty string
                # on that one turn; Claude's API rejects it outright
                # ("'content' argument must not be empty"), and even a
                # tolerant provider fails on a LATER turn once that empty
                # entry is replayed as part of history. Forward the chosen
                # option's own label/value instead of discarding it.
                choice = result.get("choice_made") or {}
                user_message = choice.get("label") or choice.get("value") or ""
                continue
            if node_type == "start" and next_id:
                current_node_id = next_id
                continue

            # Default: stop and return
            context.current_node_id = next_id
            return {
                "response": "\n\n".join(responses) if responses else "",
                "next_node_id": next_id,
                "context": context.to_dict(),
                "ended": False,
                "choices": choices,
                "image": image,
                "citations": citations,
                "node_type": node_type,
                "provider": result.get("provider"),
            }

        return {
            "response": "\n\n".join(responses) if responses else "Workflow execution limit reached.",
            "next_node_id": None,
            "context": context.to_dict(),
            "ended": True,
            "choices": None,
            "citations": [],
            "node_type": "error",
        }

    async def stream_run(
        self, user_message: str, context: ExecutionContext
    ) -> AsyncIterator[dict]:
        """
        FIX v5: context.current_node_id is managed entirely within the runner.
        The WS handler no longer touches current_node_id — it only reads
        next_node_id from done chunks for debugging. This eliminates the
        double-write that caused duplicate messages.
        """
        # ROOT CAUSE FIX (mirrors run()): `completed` is checked first, before
        # anything else, so a completed session — however it terminated —
        # can never be silently resumed.
        if context.completed:
            yield {"type": "ended"}
            return

        current_node_id = context.current_node_id

        if not current_node_id:
            start = self._get_start_node()
            if not start:
                yield {"type": "error", "content": "No Start node found in workflow"}
                return
            current_node_id = start["id"]

        # Terminal-state guard for sessions persisted before the `completed`
        # flag existed (back-compat only). A session already parked on an End
        # node must not re-execute it and re-emit the goodbye message on
        # every further stray/duplicate message.
        existing_node = self.nodes.get(current_node_id)
        if existing_node and existing_node.get("type") == "end":
            context.completed = True
            yield {"type": "ended"}
            return

        hops = 0
        last_seen = None
        last_repeat = 0

        while hops < self.MAX_HOPS:
            hops += 1
            node = self.nodes.get(current_node_id)
            if not node:
                break

            if current_node_id == last_seen:
                last_repeat += 1
                if last_repeat > 3:
                    yield {"type": "error", "content": "Workflow loop detected"}
                    return
            else:
                last_repeat = 0
                last_seen = current_node_id

            node_type = node.get("type")

            if node_type == "ai_agent":
                handler = self._get_handler(node)

                full_text = ""
                async for token in handler.stream_response(user_message, context):
                    full_text += token
                    yield {"type": "token", "content": token}

                stay = handler.data.get("stayOnNode", True)
                # ROOT CAUSE FIX: "stayOnNode" is the only intentional replay.
                # When stayOnNode is False and there is genuinely no outgoing
                # edge, this must terminate the workflow — not silently fall
                # back to replaying this same AI Agent node forever via
                # "if next_id is None: next_id = node['id']".
                next_id = node["id"] if stay else handler.get_first_next()

                # FIX v6: surface citations on the WS path too (previously only
                # the non-streaming REST run() path returned them — WebSocket
                # chat users never saw which documents an answer was grounded in).
                citations = getattr(handler, "last_citations", [])

                if next_id is None:
                    context.current_node_id = current_node_id
                    context.completed = True
                    yield {
                        "type": "done",
                        "node_type": "ai_agent",
                        "next_node_id": None,
                        "ended": True,
                        "citations": citations,
                    }
                    return

                # FIX v5: single authoritative context update in runner
                context.current_node_id = next_id

                yield {
                    "type": "done",
                    "node_type": "ai_agent",
                    "next_node_id": next_id,
                    "ended": False,
                    "citations": citations,
                }
                return

            elif node_type == "multiple_choice":
                handler = self._get_handler(node)
                result = await handler.execute(user_message, context)
                # FIX (root cause): mutate the caller's context object in place.
                # stream_run is a generator with no return value — rebinding the
                # local `context` name here would discard all state the instant
                # the generator returns, since chat_ws.py holds the ORIGINAL
                # object reference and persists that to Redis after the turn.
                context.apply_from(ExecutionContext.from_dict(result["context"]))

                if result.get("response") or result.get("choices"):
                    yield {
                        "type": "message",
                        "content": result.get("response") or "",
                        "node_type": "multiple_choice",
                        "choices": result.get("choices"),
                        "image": result.get("image"),
                    }

                next_id = result.get("next_node_id")

                # FIX (root cause): a multiple_choice result with choice_made set
                # already consumed the user's input and resolved a destination —
                # it must auto-advance into that node within the SAME turn,
                # exactly like a transition node does. Previously this branch
                # always yielded "done" and returned here unconditionally, which
                # meant the destination node (e.g. an end node right after the
                # choice) silently never ran until an unrelated extra message
                # arrived. Only the presentation phase (no choice_made yet,
                # i.e. the question + choices were just shown) genuinely needs
                # to stop and wait for the user.
                if result.get("choice_made") and next_id:
                    current_node_id = next_id
                    # ROOT CAUSE FIX: same issue as the non-streaming run()
                    # path above — forward the selected option's own
                    # label/value instead of blanking to "", so an AI Agent
                    # immediately following this choice never receives an
                    # empty-content user turn (which Claude's API rejects,
                    # and which poisons later turns via persisted history).
                    choice = result.get("choice_made") or {}
                    user_message = choice.get("label") or choice.get("value") or ""
                    continue

                # ROOT CAUSE FIX: a resolved choice with NO outgoing edge on the
                # selected option is a dead end — terminate immediately instead
                # of yielding ended=False, which previously left
                # current_node_id at None and caused the NEXT message to
                # silently restart the whole workflow from Start.
                if result.get("choice_made") and next_id is None:
                    context.current_node_id = current_node_id
                    context.completed = True
                    yield {
                        "type": "done",
                        "node_type": "multiple_choice",
                        "next_node_id": None,
                        "ended": True,
                    }
                    return

                yield {
                    "type": "done",
                    "node_type": "multiple_choice",
                    "next_node_id": next_id,
                    "ended": False,
                }
                return

            else:
                handler = self._get_handler(node)
                result = await handler.execute(user_message, context)
                # FIX (root cause): same issue as the multiple_choice branch above —
                # mutate in place rather than rebind, so state survives past the
                # point where this generator returns/continues.
                context.apply_from(ExecutionContext.from_dict(result["context"]))

                if result.get("response"):
                    yield {
                        "type": "message",
                        "content": result["response"],
                        "node_type": result.get("node_type"),
                        "choices": result.get("choices"),
                    }

                if result.get("ended"):
                    context.completed = True
                    yield {"type": "ended"}
                    return

                next_id = result.get("next_node_id")
                ntype = result.get("node_type")

                # ROOT CAUSE FIX: the single choke point for this branch
                # (start, text_card, transition, and any future custom node
                # type that doesn't get its own dedicated branch above). A
                # node with NO outgoing edge on the selected path must
                # terminate the workflow immediately — never auto-advance,
                # never search for another node, and never leave
                # current_node_id as None (indistinguishable from "session
                # never started", which would silently restart from Start on
                # the next message).
                if next_id is None:
                    context.current_node_id = current_node_id
                    context.completed = True
                    yield {"type": "ended"}
                    return

                # Auto-advance through invisible/non-interactive nodes.
                # ROOT CAUSE FIX (also applied to run() above): "start" must
                # NOT blank user_message — it hasn't consumed anything yet,
                # and the user's real message is meant for whatever follows
                # it (e.g. a direct "Start -> AI Agent" graph). Only
                # transition/text_card (which never consume the message)
                # correctly reset it here.
                #
                # This is a SEPARATE, additional fix from the text_card
                # auto-advance fix already documented below — that one fixed
                # text_card getting stuck; this one fixes start silently
                # discarding the user's first message before it ever reaches
                # an AI Agent or Knowledge Base retrieval.
                if ntype == "text_card" and next_id:
                    current_node_id = next_id
                    context.current_node_id = next_id
                    user_message = ""
                    continue
                # ROOT CAUSE FIX: "condition" belongs alongside "transition"
                # here for the same reason as in run() above — it never
                # consumes the user's message and never emits a response, it
                # only selects an outgoing edge, so it must auto-advance
                # instead of stalling the stream at a node with no output.
                if ntype in ("transition", "start", "condition") and next_id:
                    current_node_id = next_id
                    context.current_node_id = next_id
                    if ntype in ("transition", "condition"):
                        user_message = ""
                    continue

                # Terminal node for this turn (e.g. text_card/transition/end with
                # no outgoing edge, or any future node type added to this branch).
                # Always persist next_id into context — mirrors run()'s fallback.
                context.current_node_id = next_id

                yield {
                    "type": "done",
                    "node_type": ntype,
                    "next_node_id": next_id,
                    "ended": False,
                }
                return

        yield {"type": "error", "content": "Workflow execution limit reached"}
