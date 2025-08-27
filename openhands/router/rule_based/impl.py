from openhands.core.config import AgentConfig
from openhands.core.logger import openhands_logger as logger
from openhands.core.message import Message
from openhands.events.action import MessageAction
from openhands.events.event import Event
from openhands.llm.llm import LLM
from openhands.llm.llm_registry import LLMRegistry
from openhands.llm.router_llm import RouterLLM
from openhands.router.base import ROUTER_REGISTRY


class MultimodalRouter(RouterLLM):
    SECONDARY_MODEL_CONFIG_NAME = 'secondary_model'
    ROUTER_NAME = 'multimodal_router'

    def __init__(self, agent_config: AgentConfig, llm_registry: LLMRegistry, **kwargs):
        super().__init__(agent_config, llm_registry, **kwargs)

        self._validate_model_routing_config(self.llms_for_routing)

        # State for multimodal routing
        self.max_token_exceeded = False

    def _select_llm(self, messages: list[Message], events: list[Event]) -> str:
        """Select LLM based on multimodal content and token limits."""
        route_to_primary = False

        # Check for multimodal content in messages
        if self._has_multimodal_content(messages):
            logger.info(
                'Multimodal content detected in messages. Routing to the primary model.'
            )
            route_to_primary = True

        # Handle multimodal input from events (backward compatibility)
        for event in events:
            if (
                isinstance(event, MessageAction)
                and event.source == 'user'
                and event.image_urls
            ):
                logger.info(
                    'Image content detected in events. Routing to the primary model.'
                )
                route_to_primary = True
                break

        if not route_to_primary and self.max_token_exceeded:
            route_to_primary = True

        # Check if `messages` exceeds context window of the secondary model
        # Assuming the secondary model has a lower context window limit compared to the primary model
        secondary_llm = self.available_llms.get(self.SECONDARY_MODEL_CONFIG_NAME)
        if secondary_llm and (
            secondary_llm.config.max_input_tokens
            and secondary_llm.get_token_count(messages)
            > secondary_llm.config.max_input_tokens
        ):
            logger.warning(
                f"Messages having {secondary_llm.get_token_count(messages)} tokens, exceed secondary model's max input tokens ({secondary_llm.config.max_input_tokens} tokens). "
                'Routing to the primary model.'
            )
            self.max_token_exceeded = True
            route_to_primary = True

        if route_to_primary:
            logger.info('Routing to the primary model...')
            return 'main'
        else:
            logger.info('Routing to the secondary model...')
            return self.SECONDARY_MODEL_CONFIG_NAME

    def _has_multimodal_content(self, messages: list[Message]) -> bool:
        """Check if messages contain multimodal content."""
        for message in messages:
            if hasattr(message, 'contains_vision') and message.contains_vision():
                return True
            # Also check content directly for image content
            if hasattr(message, 'content') and isinstance(message.content, list):
                for content_item in message.content:
                    if (
                        hasattr(content_item, 'type')
                        and content_item.type == 'image_url'
                    ):
                        return True
        return False

    def _validate_model_routing_config(self, llms_for_routing: dict[str, LLM]):
        if self.SECONDARY_MODEL_CONFIG_NAME not in llms_for_routing:
            raise ValueError(
                f'Secondary LLM config {self.SECONDARY_MODEL_CONFIG_NAME} not found.'
            )


# Register the router
ROUTER_REGISTRY[MultimodalRouter.ROUTER_NAME] = MultimodalRouter
