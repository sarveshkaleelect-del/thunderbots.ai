"""
ThunderBots Node Handlers v5
FIX: MultipleChoiceNodeHandler — eliminated race condition where first click
     was ignored because context.current_node_id was not yet set to the choice
     node when the user responded. Now uses a "waiting" flag in context variables.
FIX: AIAgentNodeHandler.stream_response — context update now happens after all
     tokens yielded, not before, preventing duplicate messages.
FIX: TransitionNodeHandler — no longer swallows default fallback, ensuring
     workflow never hangs silently.
FIX: StartNodeHandler — sets context.current_node_id before returning.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from app.engine.context import ExecutionContext
from app.services.ai_engine import ai_engine, resolve_agent_provider
from app.knowledge.pipeline import retrieval_engine


class BaseNodeHandler(ABC):
    def __init__(self, node: dict, adj: dict[str, list[tuple[str, str]]], nodes: dict[str, dict]):
        self.node = node
        self.adj = adj
        self.nodes = nodes
        self.data = node.get("data", {})
        self.node_id = node["id"]
        self.user_id: Optional[str] = None

    def get_next_nodes(self, handle: str = "output_0") -> list[str]:
        connections = self.adj.get(self.node_id, [])
        return [target for target, h in connections if h == handle]

    def get_first_next(self, handle: str = "output_0") -> Optional[str]:
        """
        Returns the target of the edge stored for `handle`, or None if no such
        edge exists.
        ROOT CAUSE FIX: this used to fall back to "the first edge from this
        node, on ANY handle" whenever the requested handle had no match. That
        silently routed execution down an edge the user never selected —
        e.g. clicking a Multiple Choice option with no outgoing edge would
        jump into whichever edge happened to exist on a *different* option,
        and a Transition whose matched condition/default had no edge would
        jump into an unrelated sibling edge. Only the edge stored for the
        exact requested handle may ever be followed; anything else is a
        dead end and must be reported as None so callers can terminate.
        """
        nexts = self.get_next_nodes(handle)
        return nexts[0] if nexts else None

    def interpolate(self, text: str, context: ExecutionContext) -> str:
        if not text:
            return text
        return ai_engine.interpolate_variables(text, context.variables)

    @abstractmethod
    async def execute(self, user_message: str, context: ExecutionContext) -> dict: ...


# ── Start ─────────────────────────────────────────────────────────────────────

class StartNodeHandler(BaseNodeHandler):
    async def execute(self, user_message: str, context: ExecutionContext) -> dict:
        next_id = self.get_first_next()
        welcome = self.interpolate(self.data.get("welcomeMessage", ""), context)
        # FIX: mark that we've left start node
        context.current_node_id = next_id
        return {
            "response": welcome or None,
            "next_node_id": next_id,
            "context": context.to_dict(),
            "ended": False,
            "node_type": "start",
            "node_id": self.node_id,
        }


# ── Text Card ─────────────────────────────────────────────────────────────────

class TextCardNodeHandler(BaseNodeHandler):
    async def execute(self, user_message: str, context: ExecutionContext) -> dict:
        text = self.interpolate(self.data.get("content", ""), context)
        next_id = self.get_first_next()
        if text:
            context.add_message("assistant", text, self.node_id)
        # FIX: write current_node_id here, consistent with every other handler
        # (Start/MultipleChoice/Transition/AIAgent). Previously only the runner's
        # auto-advance branch updated this, which meant any code path that didn't
        # explicitly include "text_card" in its auto-advance set left the session
        # permanently stuck on this node. Setting it here makes the handler
        # self-sufficient regardless of which runner branch processes it.
        context.current_node_id = next_id
        return {
            "response": text or "",
            "next_node_id": next_id,
            "context": context.to_dict(),
            "ended": False,
            "node_type": "text_card",
            "node_id": self.node_id,
        }


# ── Multiple Choice ───────────────────────────────────────────────────────────

class MultipleChoiceNodeHandler(BaseNodeHandler):
    """
    FIX v5: Two-phase execution eliminates the race condition.

    Phase 1 (presentation): When we first arrive at this node, store a
    "waiting_choice:{node_id}" flag in context variables and return the
    question + choices to the user. The runner stops here.

    Phase 2 (response): On the NEXT user message, the runner calls this
    node again. We check the flag — if it's set, we are in response mode
    and match the user's input against the choices.

    This means we no longer rely on context.current_node_id == self.node_id,
    which was set inconsistently (sometimes BEFORE the WS send, sometimes after).
    """

    _WAITING_KEY = "__waiting_choice_{}"

    def _waiting_key(self):
        return self._WAITING_KEY.format(self.node_id)

    async def execute(self, user_message: str, context: ExecutionContext) -> dict:
        choices: list[dict] = self.data.get("choices", [])
        question = self.interpolate(self.data.get("question", ""), context)
        waiting_key = self._waiting_key()

        # Phase 2: we were waiting for user input
        if context.get_variable(waiting_key) and user_message:
            matched = self._match_choice(user_message, choices)
            if matched:
                context.set_variable("last_choice", matched["value"])
                context.set_variable(waiting_key, None)  # clear flag
                context.add_message("user", user_message, self.node_id)
                handle = f"choice_{matched['index']}"
                # ROOT CAUSE FIX: only follow the edge on the SELECTED option's
                # own handle. The previous "or self.get_first_next()" fallback
                # meant a choice with no outgoing edge would silently jump to
                # whatever edge existed on a different, unrelated choice.
                next_id = self.get_first_next(handle)
                context.current_node_id = next_id if next_id is not None else self.node_id
                return {
                    "response": None,
                    "next_node_id": next_id,
                    "context": context.to_dict(),
                    # FIX: this dict never carried an "ended" key at all, so a
                    # dead-end choice (next_id None) was silently reported as
                    # not-ended. Explicit here; the runner also enforces this
                    # centrally for every node type as defense in depth.
                    "ended": next_id is None,
                    "node_type": "multiple_choice",
                    "node_id": self.node_id,
                    "choice_made": matched,
                }
            else:
                # User sent something that didn't match — re-present choices
                return {
                    "response": f"Please choose one of the options below.",
                    "next_node_id": self.node_id,
                    "choices": choices,
                    "image": self.data.get("image"),
                    "context": context.to_dict(),
                    "ended": False,
                    "node_type": "multiple_choice",
                    "node_id": self.node_id,
                }

        # Phase 1: present question + choices, set waiting flag
        context.set_variable(waiting_key, True)
        context.current_node_id = self.node_id
        if question:
            context.add_message("assistant", question, self.node_id)
        return {
            "response": question or "",
            "next_node_id": self.node_id,
            "choices": choices,
            "image": self.data.get("image"),
            "context": context.to_dict(),
            "ended": False,
            "node_type": "multiple_choice",
            "node_id": self.node_id,
        }

    def _match_choice(self, user_message: str, choices: list[dict]) -> Optional[dict]:
        msg_lower = user_message.lower().strip()
        for i, choice in enumerate(choices):
            label = str(choice.get("label", "")).lower()
            value = str(choice.get("value", "")).lower()
            if msg_lower in (label, value) or msg_lower == str(i + 1):
                return {
                    "index": i,
                    "label": choice.get("label", ""),
                    "value": choice.get("value", choice.get("label", "")),
                }
        return None


# ── AI Agent ──────────────────────────────────────────────────────────────────

class AIAgentNodeHandler(BaseNodeHandler):

    # ROOT CAUSE FIX (Issue 2 — "generated chatbot sometimes does not answer"):
    # any exception raised while resolving a provider or calling the AI
    # engine (no API key configured, invalid/expired key, provider outage,
    # rate limit, timeout, network failure, ...) used to propagate straight
    # out of execute()/stream_response(). WorkflowRunner.run() had no guard
    # for it, so it bubbled all the way to the API layer, which turned it
    # into a raw HTTP 500 (see chat.py) or a broken WS/webhook turn — the
    # end user saw no bot response at all. An AI Agent node is a USER_FACING
    # node with no other node type able to take over for it, so it must
    # never let the turn end in silence. FRIENDLY_FALLBACK_MESSAGE is what
    # every caller now gets instead whenever the underlying call fails.
    FRIENDLY_FALLBACK_MESSAGE = (
        "Sorry, I'm having trouble answering that right now. "
        "Could you try again in a moment? If this keeps happening, "
        "a member of our team can take over from here."
    )

    def _fallback_result(self, user_message: str, context: ExecutionContext, error_detail: str) -> dict:
        """Builds a normal-shaped, user-facing response out of a failure —
        the workflow keeps running exactly as if the AI Agent had answered
        normally (same stay/advance logic), it just answers with the
        friendly fallback message instead of a real completion. Never
        raises, and always records both turns so history/analytics stay
        consistent with a successful turn."""
        context.add_message("user", user_message, self.node_id)
        context.add_message("assistant", self.FRIENDLY_FALLBACK_MESSAGE, self.node_id)

        stay = self.data.get("stayOnNode", True)
        next_id = self.node_id if stay else self.get_first_next()
        context.current_node_id = next_id if next_id is not None else self.node_id

        return {
            "response": self.FRIENDLY_FALLBACK_MESSAGE,
            "next_node_id": next_id,
            "context": context.to_dict(),
            "ended": (not stay) and next_id is None,
            "node_type": "ai_agent",
            "node_id": self.node_id,
            "citations": [],
            "provider": None,
            "error": error_detail,
        }

    async def execute(self, user_message: str, context: ExecutionContext) -> dict:
        # ROOT CAUSE FIX: no more hardcoded "openai" fallback. A node with no
        # explicit provider (every marketplace template, post-fix) now
        # resolves against the user's own configured default provider at run
        # time, raising an actionable error if neither is set — see
        # resolve_agent_provider in app/services/ai_engine.py. That raise (and
        # any failure from the AI call itself) is now caught below so it can
        # never reach the runner as an unhandled exception.
        try:
            provider = await resolve_agent_provider(self.data.get("provider"), self.user_id)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"AI Agent node {self.node_id}: provider resolution failed, using fallback response: {e}"
            )
            return self._fallback_result(user_message, context, str(e))

        model       = self.data.get("model") or None
        sys_prompt  = self.interpolate(self.data.get("systemPrompt", ""), context)
        instructions = self.interpolate(self.data.get("instructions", ""), context)
        temperature  = float(self.data.get("temperature", 0.7))
        max_tokens   = int(self.data.get("maxTokens", 1000))
        kb_id        = self.data.get("knowledgeBaseId")

        kb_context = None
        citations = []
        if kb_id and user_message:
            kb_data = await self._get_kb_data(kb_id)
            if kb_data:
                try:
                    results = await retrieval_engine.retrieve(
                        query=user_message,
                        collection_name=kb_data["chroma_collection"],
                        kb_id=kb_id,
                        user_id=self.user_id,
                        embedding_provider=kb_data.get("embedding_provider"),
                        embedding_model=kb_data.get("embedding_model"),
                    )
                    kb_context = retrieval_engine.format_context(results)
                    citations  = retrieval_engine.format_citations(results)
                except Exception as e:
                    # FIX v6: a vector-database failure (connectivity, API version
                    # mismatch, etc) must not take down the entire AI Agent turn —
                    # retrieval is an enhancement layer. Log the real error for
                    # diagnosis and let the agent respond without KB context
                    # rather than failing the whole chat response.
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        f"KB retrieval failed for kb={kb_id}, continuing without context: {e}"
                    )

        history_limit = int(self.data.get("contextWindow", 10))
        messages = context.get_message_history(limit=history_limit)
        # DEFENSE IN DEPTH: get_message_history() can no longer return
        # empty-content entries (see ExecutionContext.add_message), and the
        # runner no longer hands this node an empty user_message after a
        # multiple_choice hand-off (see WorkflowRunner). This guard is the
        # last line of defense so a genuinely empty turn (e.g. some future
        # node type that doesn't consume user input) still never reaches the
        # provider as an empty "content" string, which Claude's API rejects
        # outright and which would otherwise poison every later turn once
        # persisted to history.
        #
        # It also avoids a SECOND, related defect: a resolved multiple_choice
        # node records the user's chosen option into history itself (so the
        # full transcript shows what they picked). If the very next node is
        # this AI Agent, appending user_message again here would put two
        # consecutive "user"-role messages back to back — most providers
        # (including Claude) require strictly alternating roles, so this
        # would trade the empty-content rejection for a role-alternation
        # rejection instead. Skip the append when history already ends with
        # this exact user turn.
        already_recorded = bool(
            messages and messages[-1]["role"] == "user" and messages[-1]["content"] == user_message
        )
        if user_message and not already_recorded:
            messages.append({"role": "user", "content": user_message})
        elif not messages:
            messages.append({"role": "user", "content": "Hello"})

        try:
            response = await ai_engine.complete(
                provider=provider,
                system_prompt=sys_prompt,
                instructions=instructions,
                messages=messages,
                context=context.to_dict(),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                kb_context=kb_context,
                user_id=self.user_id,
            )
        except Exception as e:
            # ROOT CAUSE FIX: any provider failure (auth, quota, timeout,
            # network, malformed key, etc.) gets a friendly answer instead of
            # crashing the turn. The user already sent a real message, so it
            # is still recorded into history via _fallback_result exactly
            # like a successful turn.
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"AI Agent node {self.node_id}: provider '{provider}' call failed, using fallback response: {e}"
            )
            return self._fallback_result(user_message, context, str(e))

        # FIX v5: Update context ONCE after getting response
        # ROOT CAUSE FIX: skip re-recording the user turn when the upstream
        # node (a resolved multiple_choice) already added this exact message
        # to history a moment earlier in the same turn — see the
        # `already_recorded` guard above. Persisting it twice would leave two
        # consecutive "user"-role entries in history, which breaks role
        # alternation on every future turn that replays this history to the
        # provider, not just this one.
        if not already_recorded:
            context.add_message("user", user_message, self.node_id)
        context.add_message("assistant", response, self.node_id)

        stay = self.data.get("stayOnNode", True)
        # ROOT CAUSE FIX: "stayOnNode" is the only intentional replay — the
        # designer explicitly configured this node to keep talking to the
        # user turn after turn. When stayOnNode is False (the designer wants
        # to move on) and there is genuinely no outgoing edge, next_id must
        # stay None and terminate the workflow, not silently fall back to
        # replaying this same AI Agent node forever ("next_id or self.node_id").
        next_id = self.node_id if stay else self.get_first_next()
        context.current_node_id = next_id if next_id is not None else self.node_id

        return {
            "response": response,
            "next_node_id": next_id,
            "context": context.to_dict(),
            "ended": (not stay) and next_id is None,
            "node_type": "ai_agent",
            "node_id": self.node_id,
            "citations": citations,
            "provider": provider,
        }

    async def stream_response(
        self, user_message: str, context: ExecutionContext
    ) -> AsyncIterator[str]:
        """Async generator — yields tokens, then updates context once complete."""
        # ROOT CAUSE FIX: same as execute() above — resolve dynamically
        # instead of hardcoding "openai" as the fallback. Any failure here
        # (no API key configured, etc.) is treated like a mid-stream provider
        # failure below — yield the friendly fallback message as normal
        # token content instead of letting the exception escape into
        # WorkflowRunner.stream_run (which had no handling for it, so it
        # bubbled up as a raw SSE/WS error frame with no bot response).
        self.last_citations: list[dict] = []
        try:
            provider = await resolve_agent_provider(self.data.get("provider"), self.user_id)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"AI Agent node {self.node_id}: provider resolution failed, streaming fallback response: {e}"
            )
            context.add_message("user", user_message, self.node_id)
            context.add_message("assistant", self.FRIENDLY_FALLBACK_MESSAGE, self.node_id)
            yield self.FRIENDLY_FALLBACK_MESSAGE
            return

        model        = self.data.get("model") or None
        sys_prompt   = self.interpolate(self.data.get("systemPrompt", ""), context)
        instructions = self.interpolate(self.data.get("instructions", ""), context)
        temperature  = float(self.data.get("temperature", 0.7))
        max_tokens   = int(self.data.get("maxTokens", 1000))
        kb_id        = self.data.get("knowledgeBaseId")

        kb_context = None
        # FIX v6: citations were never computed on the streaming path at all
        # (only execute(), the non-streaming REST path, called format_citations).
        # This meant WebSocket chat users — i.e. everyone using the actual chat
        # UI — never saw which documents an AI Agent's answer was grounded in,
        # even when retrieval was working correctly. Exposed via an instance
        # attribute (read by WorkflowRunner.stream_run after the token loop
        # completes) rather than changing this method's AsyncIterator[str]
        # yield contract, which other code already depends on.
        self.last_citations: list[dict] = []
        if kb_id and user_message:
            kb_data = await self._get_kb_data(kb_id)
            if kb_data:
                try:
                    results = await retrieval_engine.retrieve(
                        query=user_message,
                        collection_name=kb_data["chroma_collection"],
                        kb_id=kb_id,
                        user_id=self.user_id,
                        embedding_provider=kb_data.get("embedding_provider"),
                        embedding_model=kb_data.get("embedding_model"),
                    )
                    kb_context = retrieval_engine.format_context(results)
                    self.last_citations = retrieval_engine.format_citations(results)
                except Exception as e:
                    # FIX v6: same as execute() above — a vector-database failure
                    # must not crash the streaming AI Agent turn. Log and continue
                    # without KB context.
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        f"KB retrieval failed for kb={kb_id}, continuing without context: {e}"
                    )

        history_limit = int(self.data.get("contextWindow", 10))
        messages = context.get_message_history(limit=history_limit)
        # DEFENSE IN DEPTH: see the matching comment in execute() above. Also
        # avoids appending a duplicate consecutive "user" entry when a
        # resolved multiple_choice node already recorded this exact message
        # into history a moment earlier in the same turn.
        already_recorded = bool(
            messages and messages[-1]["role"] == "user" and messages[-1]["content"] == user_message
        )
        if user_message and not already_recorded:
            messages.append({"role": "user", "content": user_message})
        elif not messages:
            messages.append({"role": "user", "content": "Hello"})

        full_response = ""
        try:
            async for token in ai_engine.stream(
                provider=provider,
                system_prompt=sys_prompt,
                instructions=instructions,
                messages=messages,
                context=context.to_dict(),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                kb_context=kb_context,
                user_id=self.user_id,
            ):
                full_response += token
                yield token
        except Exception as e:
            # ROOT CAUSE FIX: a provider failure part-way through (or before)
            # streaming used to propagate out of this generator uncaught,
            # which WorkflowRunner.stream_run had no handling for — the user
            # ended the turn with either a truncated answer and no
            # explanation, or nothing at all. Substitute the friendly
            # fallback message (appended after any partial content already
            # shown, so nothing already seen by the user is contradicted)
            # and keep going as if this had been the real answer.
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"AI Agent node {self.node_id}: provider '{provider}' stream failed, using fallback response: {e}"
            )
            fallback_chunk = ("\n\n" + self.FRIENDLY_FALLBACK_MESSAGE) if full_response else self.FRIENDLY_FALLBACK_MESSAGE
            full_response += fallback_chunk
            yield fallback_chunk

        # FIX v5: Update context ONCE after streaming completes (not during)
        # ROOT CAUSE FIX: see the matching comment in execute() above — don't
        # re-persist a user turn the upstream node already recorded, or every
        # later turn's history would carry a broken, non-alternating
        # duplicate.
        if not already_recorded:
            context.add_message("user", user_message, self.node_id)
        context.add_message("assistant", full_response, self.node_id)

    async def _get_kb_data(self, kb_id: str) -> Optional[dict]:
        """Try Redis cache first, fall back to DB. Never raises."""
        import logging
        logger = logging.getLogger(__name__)

        from app.core.redis import CacheService
        cache = CacheService()
        cached = await cache.get(f"kb:{kb_id}")
        if cached:
            return cached

        try:
            from app.core.database import AsyncSessionLocal
            from sqlalchemy import select
            from app.models.knowledge import KnowledgeBase
            from app.config import settings

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
                )
                kb = result.scalar_one_or_none()
                if not kb:
                    return None
                data = {
                    "id": str(kb.id),
                    "name": kb.name,
                    "chroma_collection": kb.chroma_collection,
                    # ROOT CAUSE FIX: carried through so retrieve() embeds the
                    # query with the same provider/model used to index this
                    # KB's documents — see app/knowledge/pipeline.py.
                    "embedding_provider": kb.embedding_provider,
                    "embedding_model": kb.embedding_model,
                }
                await cache.set(f"kb:{kb_id}", data, ttl=settings.KB_CACHE_TTL)
                return data
        except Exception as e:
            logger.warning(f"KB lookup failed for {kb_id}: {e}")
            return None


# ── Transition ────────────────────────────────────────────────────────────────

class TransitionNodeHandler(BaseNodeHandler):
    async def execute(self, user_message: str, context: ExecutionContext) -> dict:
        conditions: list[dict] = self.data.get("conditions", [])

        target_id = None
        for condition in conditions:
            if self._evaluate(condition, context, user_message):
                handle = condition.get("handle", "output_0")
                target_id = self.get_first_next(handle)
                break

        # ROOT CAUSE FIX: only an explicit "default" edge (a designer-defined
        # else-branch) may be used when no condition matched. The previous
        # trailing "or self.get_first_next()" blindly grabbed ANY other edge
        # from this node — e.g. one condition's own branch — even though the
        # user's input never matched it and no default edge was defined. That
        # is exactly the "auto-selects another node" / "traverses unrelated
        # nodes" bug. If there is no default edge either, this is a genuine
        # dead end and target_id correctly stays None.
        if not target_id:
            target_id = self.get_first_next("default")

        context.current_node_id = target_id if target_id is not None else self.node_id

        return {
            "response": None,
            "next_node_id": target_id,
            "context": context.to_dict(),
            "ended": target_id is None,
            "node_type": "transition",
            "node_id": self.node_id,
        }

    def _evaluate(self, condition: dict, context: ExecutionContext, user_message: str) -> bool:
        field    = condition.get("field", "")
        operator = condition.get("operator", "contains")
        value    = str(condition.get("value", ""))

        if field == "user_message":
            actual = user_message.lower()
        elif field == "turn_count":
            actual = str(context.turn_count)
        else:
            actual = str(context.get_variable(field, "")).lower()

        value_lower = value.lower()

        match operator:
            case "contains":     return value_lower in actual
            case "equals":       return actual == value_lower
            case "starts_with":  return actual.startswith(value_lower)
            case "ends_with":    return actual.endswith(value_lower)
            case "not_contains": return value_lower not in actual
            case "greater_than":
                try: return float(actual or 0) > float(value or 0)
                except ValueError: return False
            case "less_than":
                try: return float(actual or 0) < float(value or 0)
                except ValueError: return False
            case _: return False


# ── Condition ─────────────────────────────────────────────────────────────────

class ConditionNodeHandler(BaseNodeHandler):
    """
    ROOT CAUSE FIX: the Condition node type was never registered in
    NODE_HANDLERS, so the runner raised "Unknown node type: 'condition'" the
    moment execution reached one. This mirrors ConditionNodeData (frontend/
    types/index.ts) and the "if"/"else" source handles defined on
    ConditionNode (components/builder/Nodes/NodeComponents.tsx): a single
    variable == value comparison, routing to the "if" handle on a match and
    the "else" handle otherwise.
    """
    async def execute(self, user_message: str, context: ExecutionContext) -> dict:
        variable = self.data.get("variable", "")
        expected = str(self.data.get("value", ""))
        actual = str(context.get_variable(variable, "")) if variable else ""

        handle = "if" if actual == expected else "else"
        target_id = self.get_first_next(handle)
        context.current_node_id = target_id if target_id is not None else self.node_id

        return {
            "response": None,
            "next_node_id": target_id,
            "context": context.to_dict(),
            "ended": target_id is None,
            "node_type": "condition",
            "node_id": self.node_id,
        }


# ── End ───────────────────────────────────────────────────────────────────────

class EndNodeHandler(BaseNodeHandler):
    async def execute(self, user_message: str, context: ExecutionContext) -> dict:
        message = self.interpolate(self.data.get("message", ""), context)
        if message:
            context.add_message("assistant", message, self.node_id)
        # FIX: consistent with every other handler — set current_node_id even
        # though both runner paths currently short-circuit on ended=True before
        # reaching auto-advance logic. End is terminal (self.node_id, no outgoing
        # edge expected), so this is zero-risk and closes any latent path where a
        # future change to the ended short-circuit could reintroduce stale state.
        context.current_node_id = self.node_id
        return {
            "response": message or None,
            "next_node_id": None,
            "context": context.to_dict(),
            "ended": True,
            "node_type": "end",
            "node_id": self.node_id,
        }


# ── Registry ──────────────────────────────────────────────────────────────────

NODE_HANDLERS: dict[str, type[BaseNodeHandler]] = {
    "start":           StartNodeHandler,
    "text_card":       TextCardNodeHandler,
    "multiple_choice": MultipleChoiceNodeHandler,
    "ai_agent":        AIAgentNodeHandler,
    "transition":      TransitionNodeHandler,
    "end":             EndNodeHandler,
    "condition":       ConditionNodeHandler,
}
