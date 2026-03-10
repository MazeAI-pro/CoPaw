# -*- coding: utf-8 -*-
# pylint: disable=unused-argument too-many-branches too-many-statements
import asyncio
import json
import logging
from pathlib import Path

from agentscope.pipeline import stream_printing_messages
from agentscope.tool import Toolkit
from agentscope_runtime.engine.runner import Runner
from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest
from dotenv import load_dotenv

from .command_dispatch import (
    _get_last_user_text,
    _is_command,
    run_command_path,
)
from .query_error_dump import write_query_error_dump
from .session import SafeJSONSession
from .utils import build_env_context
from ...utils.tracing import create_trace, flush as langfuse_flush
from ..channels.schema import DEFAULT_CHANNEL
from ..user_scope import (
    DEFAULT_USER_ID,
    get_user_chats_path,
    get_user_root,
    get_user_sessions_dir,
    migrate_legacy_to_user_dir,
    normalize_user_id,
    reset_current_user_id,
    set_current_user_id,
)
from .manager import ChatManager
from .repo.json_repo import JsonChatRepository
from ...agents.memory import MemoryManager
from ...agents.model_factory import create_model_and_formatter
from ...agents.react_agent import CoPawAgent
from ...agents.tools import read_file, write_file, edit_file
from ...agents.utils.token_counting import _get_token_counter
from ...config import load_config
from ...constant import MEMORY_COMPACT_RATIO

logger = logging.getLogger(__name__)


class AgentRunner(Runner):
    def __init__(self) -> None:
        super().__init__()
        self.framework_type = "agentscope"
        self._chat_manager_by_user: dict[str, ChatManager] = {}
        self._session_by_user: dict[str, SafeJSONSession] = {}
        self._memory_manager_by_user: dict[str, MemoryManager] = {}
        self._memory_manager_lock = asyncio.Lock()
        self._mcp_manager = None  # MCP client manager for hot-reload
        self._shared_chat_model = None
        self._shared_formatter = None
        self._shared_token_counter = None
        self._shared_toolkit: Toolkit | None = None
        self.memory_manager: MemoryManager | None = None
        self.session: SafeJSONSession | None = None

    def set_chat_manager(self, chat_manager):
        """Compatibility shim; chat managers are user-scoped now."""
        del chat_manager

    def get_chat_manager_for_user(self, user_id: str | None) -> ChatManager:
        uid = normalize_user_id(user_id)
        manager = self._chat_manager_by_user.get(uid)
        if manager is None:
            manager = ChatManager(
                repo=JsonChatRepository(get_user_chats_path(uid)),
            )
            self._chat_manager_by_user[uid] = manager
        return manager

    def get_session_for_user(self, user_id: str | None) -> SafeJSONSession:
        uid = normalize_user_id(user_id)
        session_store = self._session_by_user.get(uid)
        if session_store is None:
            session_store = SafeJSONSession(
                save_dir=str(get_user_sessions_dir(uid)),
            )
            self._session_by_user[uid] = session_store
            if uid == DEFAULT_USER_ID:
                # Keep legacy attribute for compatibility.
                self.session = session_store
        return session_store

    async def get_or_create_memory_manager(
        self,
        user_id: str | None,
    ) -> MemoryManager:
        uid = normalize_user_id(user_id)
        existing = self._memory_manager_by_user.get(uid)
        if existing is not None:
            return existing

        async with self._memory_manager_lock:
            existing = self._memory_manager_by_user.get(uid)
            if existing is not None:
                return existing

            if (
                self._shared_chat_model is None
                or self._shared_formatter is None
                or self._shared_token_counter is None
                or self._shared_toolkit is None
            ):
                # init_handler should populate shared resources first.
                chat_model, formatter = create_model_and_formatter()
                token_counter = _get_token_counter()
                toolkit = Toolkit()
                toolkit.register_tool_function(read_file)
                toolkit.register_tool_function(write_file)
                toolkit.register_tool_function(edit_file)
                self._shared_chat_model = chat_model
                self._shared_formatter = formatter
                self._shared_token_counter = token_counter
                self._shared_toolkit = toolkit

            config = load_config()
            memory_manager = MemoryManager(
                working_dir=str(get_user_root(uid)),
                chat_model=self._shared_chat_model,
                formatter=self._shared_formatter,
                token_counter=self._shared_token_counter,
                toolkit=self._shared_toolkit,
                max_input_length=config.agents.running.max_input_length,
                memory_compact_ratio=MEMORY_COMPACT_RATIO,
            )
            await memory_manager.start()
            self._memory_manager_by_user[uid] = memory_manager
            if uid == DEFAULT_USER_ID:
                # Keep legacy attribute for compatibility.
                self.memory_manager = memory_manager
            return memory_manager

    def set_mcp_manager(self, mcp_manager):
        """Set MCP client manager for hot-reload support.

        Args:
            mcp_manager: MCPClientManager instance
        """
        self._mcp_manager = mcp_manager

    async def query_handler(
        self,
        msgs,
        request: AgentRequest = None,
        **kwargs,
    ):
        """
        Handle agent query.
        """
        # Command path: do not create agent; yield from run_command_path
        query = _get_last_user_text(msgs)
        if query and _is_command(query):
            req_user_id = normalize_user_id(getattr(request, "user_id", DEFAULT_USER_ID))
            self.session = self.get_session_for_user(req_user_id)
            self.memory_manager = await self.get_or_create_memory_manager(
                req_user_id,
            )
            logger.info("Command path: %s", query.strip()[:50])
            async for msg, last in run_command_path(request, msgs, self):
                yield msg, last
            return

        agent = None
        chat = None
        session_state_loaded = False
        user_ctx_token = None
        session_id = ""
        user_id = DEFAULT_USER_ID
        try:
            session_id = request.session_id
            user_id = normalize_user_id(request.user_id)
            user_ctx_token = set_current_user_id(user_id)
            channel = getattr(request, "channel", DEFAULT_CHANNEL)
            user_root = get_user_root(user_id)
            session_store = self.get_session_for_user(user_id)
            chat_manager = self.get_chat_manager_for_user(user_id)
            memory_manager = await self.get_or_create_memory_manager(user_id)

            logger.info(
                "Handle agent query:\n%s",
                json.dumps(
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "channel": channel,
                        "msgs_len": len(msgs) if msgs else 0,
                        "msgs_str": str(msgs)[:300] + "...",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            create_trace(
                session_id=session_id,
                user_id=user_id,
                input_preview=str(msgs)[:500],
            )

            env_context = build_env_context(
                session_id=session_id,
                user_id=user_id,
                channel=channel,
                working_dir=str(user_root),
            )

            # Get MCP clients from manager (hot-reloadable)
            mcp_clients = []
            if self._mcp_manager is not None:
                mcp_clients = await self._mcp_manager.get_clients()

            config = load_config()
            max_iters = config.agents.running.max_iters
            max_input_length = config.agents.running.max_input_length

            agent = CoPawAgent(
                env_context=env_context,
                mcp_clients=mcp_clients,
                memory_manager=memory_manager,
                max_iters=max_iters,
                max_input_length=max_input_length,
            )
            await agent.register_mcp_clients()
            agent.set_console_output_enabled(enabled=False)

            logger.debug(
                f"Agent Query msgs {msgs}",
            )

            name = "New Chat"
            if len(msgs) > 0:
                content = msgs[0].get_text_content()
                if content:
                    name = msgs[0].get_text_content()[:10]
                else:
                    name = "Media Message"

            chat = await chat_manager.get_or_create_chat(
                session_id,
                user_id,
                channel,
                name=name,
            )

            try:
                await session_store.load_session_state(
                    session_id=session_id,
                    user_id=user_id,
                    agent=agent,
                )
            except KeyError as e:
                logger.warning(
                    "load_session_state skipped (state schema mismatch): %s; "
                    "will save fresh state on completion to recover file",
                    e,
                )
            session_state_loaded = True

            # Rebuild system prompt so it always reflects the latest
            # AGENTS.md / SOUL.md / PROFILE.md, not the stale one saved
            # in the session state.
            agent.rebuild_sys_prompt()

            async for msg, last in stream_printing_messages(
                agents=[agent],
                coroutine_task=agent(msgs),
            ):
                yield msg, last

        except asyncio.CancelledError as exc:
            logger.info(f"query_handler: {session_id} cancelled!")
            if agent is not None:
                await agent.interrupt()
            raise RuntimeError("Task has been cancelled!") from exc
        except Exception as e:
            debug_dump_path = write_query_error_dump(
                request=request,
                exc=e,
                locals_=locals(),
            )
            path_hint = (
                f"\n(Details:  {debug_dump_path})" if debug_dump_path else ""
            )
            logger.exception(f"Error in query handler: {e}{path_hint}")
            if debug_dump_path:
                setattr(e, "debug_dump_path", debug_dump_path)
                if hasattr(e, "add_note"):
                    e.add_note(
                        f"(Details:  {debug_dump_path})",
                    )
                suffix = f"\n(Details:  {debug_dump_path})"
                e.args = (
                    (f"{e.args[0]}{suffix}" if e.args else suffix.strip()),
                ) + e.args[1:]
            raise
        finally:
            langfuse_flush()

            if agent is not None and session_state_loaded:
                session_store = self.get_session_for_user(
                    normalize_user_id(getattr(request, "user_id", DEFAULT_USER_ID)),
                )
                await session_store.save_session_state(
                    session_id=session_id,
                    user_id=user_id,
                    agent=agent,
                )

            if chat is not None:
                chat_manager = self.get_chat_manager_for_user(user_id)
                await chat_manager.update_chat(chat)
            if user_ctx_token is not None:
                reset_current_user_id(user_ctx_token)

    async def init_handler(self, *args, **kwargs):
        """
        Init handler.
        """
        # Load environment variables from .env file
        env_path = Path(__file__).resolve().parents[4] / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            logger.debug(f"Loaded environment variables from {env_path}")
        else:
            logger.debug(
                f".env file not found at {env_path}, "
                "using existing environment variables",
            )

        migrate_legacy_to_user_dir(DEFAULT_USER_ID)
        try:
            # Shared resources for user-scoped MemoryManager instances.
            chat_model, formatter = create_model_and_formatter()
            token_counter = _get_token_counter()
            toolkit = Toolkit()
            toolkit.register_tool_function(read_file)
            toolkit.register_tool_function(write_file)
            toolkit.register_tool_function(edit_file)
            self._shared_chat_model = chat_model
            self._shared_formatter = formatter
            self._shared_token_counter = token_counter
            self._shared_toolkit = toolkit
            # Pre-warm default user stores for backward compatibility.
            self.session = self.get_session_for_user(DEFAULT_USER_ID)
            self.memory_manager = await self.get_or_create_memory_manager(
                DEFAULT_USER_ID,
            )
        except Exception as e:
            logger.exception(f"MemoryManager start failed: {e}")

    async def shutdown_handler(self, *args, **kwargs):
        """
        Shutdown handler.
        """
        for uid, manager in list(self._memory_manager_by_user.items()):
            try:
                await manager.close()
            except Exception as e:
                logger.warning(
                    "MemoryManager stop failed for user %s: %s",
                    uid,
                    e,
                )
