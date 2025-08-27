import copy
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from openhands.core.config.agent_config import AgentConfig
from openhands.core.config.llm_config import LLMConfig
from openhands.core.config.openhands_config import OpenHandsConfig
from openhands.core.logger import openhands_logger as logger
from openhands.core.message import Message
from openhands.events.event import Event
from openhands.llm.llm import LLM

if TYPE_CHECKING:
    from openhands.router.base import BaseRouter


class RegistryEvent(BaseModel):
    llm: LLM
    service_id: str

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )


class LLMRegistry:
    def __init__(
        self,
        config: OpenHandsConfig,
        agent_cls: str | None = None,
        retry_listener: Callable[[int, int], None] | None = None,
    ):
        self.registry_id = str(uuid4())
        self.config = copy.deepcopy(config)
        self.retry_listner = retry_listener
        self.agent_to_llm_config = self.config.get_agent_to_llm_config_map()
        self.service_to_llm: dict[str, LLM] = {}
        self.subscriber: Callable[[Any], None] | None = None

        selected_agent_cls = self.config.default_agent
        if agent_cls:
            selected_agent_cls = agent_cls

        agent_name = selected_agent_cls if selected_agent_cls is not None else 'agent'
        llm_config = self.config.get_llm_config_from_agent(agent_name)
        self.active_agent_llm: LLM = self.get_llm('agent', llm_config)

        # Router for model routing
        self.router: 'BaseRouter' | None = None

    def _create_new_llm(
        self, service_id: str, config: LLMConfig, with_listener: bool = True
    ) -> LLM:
        if with_listener:
            llm = LLM(
                service_id=service_id, config=config, retry_listener=self.retry_listner
            )
        else:
            llm = LLM(service_id=service_id, config=config)
        self.service_to_llm[service_id] = llm
        self.notify(RegistryEvent(llm=llm, service_id=service_id))
        return llm

    def request_extraneous_completion(
        self, service_id: str, llm_config: LLMConfig, messages: list[dict[str, str]]
    ) -> str:
        logger.info(f'extraneous completion: {service_id}')
        if service_id not in self.service_to_llm:
            self._create_new_llm(
                config=llm_config, service_id=service_id, with_listener=False
            )

        llm = self.service_to_llm[service_id]
        response = llm.completion(messages=messages)
        return response.choices[0].message.content.strip()

    def get_llm_from_agent_config(self, service_id: str, agent_config: AgentConfig):
        llm_config = self.config.get_llm_config_from_agent_config(agent_config)
        if service_id in self.service_to_llm:
            if self.service_to_llm[service_id].config != llm_config:
                # TODO: update llm config internally
                # Done when agent delegates has different config, we should reuse the existing LLM
                pass
            return self.service_to_llm[service_id]

        return self._create_new_llm(config=llm_config, service_id=service_id)

    def get_llm(
        self,
        service_id: str,
        config: LLMConfig | None = None,
    ):
        logger.info(
            f'[LLM registry {self.registry_id}]: Registering service for {service_id}'
        )

        # Attempting to switch configs for existing LLM
        if (
            service_id in self.service_to_llm
            and self.service_to_llm[service_id].config != config
        ):
            raise ValueError(
                f'Requesting same service ID {service_id} with different config, use a new service ID'
            )

        if service_id in self.service_to_llm:
            return self.service_to_llm[service_id]

        if not config:
            raise ValueError('Requesting new LLM without specifying LLM config')

        return self._create_new_llm(config=config, service_id=service_id)

    def get_active_llm(self) -> LLM:
        return self.active_agent_llm

    def _set_active_llm(self, service_id) -> None:
        if service_id not in self.service_to_llm:
            raise ValueError(f'Unrecognized service ID: {service_id}')
        self.active_agent_llm = self.service_to_llm[service_id]

    def initialize_router(self, agent_config: AgentConfig) -> None:
        """Initialize the router for model routing based on agent configuration."""
        # Import here to avoid circular imports
        from openhands.router import BaseRouter

        logger.info(f'Initializing router: {agent_config.model_routing.router_name}')
        self.router = BaseRouter.from_config(
            llm_registry=self,
            agent_config=agent_config,
        )

    def get_router(self, agent_config: AgentConfig) -> 'LLM':
        """
        Get a router instance that inherits from LLM.

        Args:
            agent_config: Agent configuration containing model routing settings

        Returns:
            RouterLLM instance that can be used as a drop-in replacement for LLM
        """

        router_name = agent_config.model_routing.router_name

        if router_name == 'noop_router':
            # Return the main LLM directly (no routing)
            return self.get_llm_from_agent_config('agent', agent_config)

        # Import here to avoid circular imports
        from openhands.router.base import BaseRouter

        # Create router using the existing factory method, but return as RouterLLM
        if router_name in ['multimodal_router']:
            # Use the new RouterLLM-based implementation
            from openhands.router.rule_based.impl import MultimodalRouter

            return MultimodalRouter(agent_config, self)
        else:
            # Fallback to old BaseRouter for other router types (during transition)
            router = BaseRouter.from_config(self, agent_config)
            # Wrap in a compatibility layer if needed
            return self._wrap_legacy_router(router, agent_config)

    def _wrap_legacy_router(
        self, router: 'BaseRouter', agent_config: AgentConfig
    ) -> 'LLM':
        """
        Wrap legacy BaseRouter in RouterLLM interface for backward compatibility.
        This is a temporary measure during the transition period.
        """
        from openhands.llm.router_llm import RouterLLM

        class LegacyRouterWrapper(RouterLLM):
            def __init__(self, legacy_router, agent_config, llm_registry):
                super().__init__(agent_config, llm_registry)
                self.legacy_router = legacy_router

            def _select_llm(self, messages, events):
                # Delegate to legacy router
                service_id = self.legacy_router.get_active_llm(messages, events)
                # Map service_id back to our key format
                if service_id == 'agent':
                    return 'main'
                elif service_id.startswith('llm_for_routing.'):
                    return service_id.replace('llm_for_routing.', '')
                else:
                    return 'main'  # Fallback

        return LegacyRouterWrapper(router, agent_config, self)

    def configure_active_llm(
        self, messages: list[Message], events: list[Event]
    ) -> None:
        """Set the active LLM based on routing decisions."""
        if self.router:
            selected_service_id = self.router.get_active_llm(messages, events)
            self._set_active_llm(selected_service_id)

    def subscribe(self, callback: Callable[[RegistryEvent], None]) -> None:
        self.subscriber = callback

        # Subscriptions happen after default llm is initialized
        # Notify service of this llm
        self.notify(
            RegistryEvent(
                llm=self.active_agent_llm, service_id=self.active_agent_llm.service_id
            )
        )

    def notify(self, event: RegistryEvent):
        if self.subscriber:
            try:
                self.subscriber(event)
            except Exception as e:
                logger.warning(f'Failed to emit event: {e}')
