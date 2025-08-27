"""
RouterLLM - Base class for routers that inherit from LLM.

This module provides a base class for implementing model routing by inheriting from LLM,
allowing routers to be used as drop-in replacements for LLM instances while providing
intelligent routing between multiple underlying LLM models.
"""

import copy
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Union

from openhands.core.config import AgentConfig
from openhands.core.logger import openhands_logger as logger
from openhands.core.message import Message, TextContent
from openhands.events.event import Event
from openhands.llm.llm import LLM
from openhands.llm.metrics import Metrics

if TYPE_CHECKING:
    from openhands.llm.llm_registry import LLMRegistry


class RouterLLM(LLM):
    """
    Base class for routers that inherit from LLM.
    
    This class provides a foundation for implementing model routing by inheriting from LLM,
    allowing routers to work with multiple underlying LLM models while presenting a unified
    LLM interface to consumers.
    
    Key features:
    - Works with multiple LLMs configured via llms_for_routing
    - Reports union of capabilities from all available LLMs
    - Delegates context-dependent operations to the selected LLM
    - Provides clean routing interface through _select_llm() method
    """
    
    def __init__(
        self,
        agent_config: AgentConfig,
        llm_registry: 'LLMRegistry',  # Type hint as string to avoid circular import
        service_id: str = "router",
        metrics: Metrics | None = None,
        retry_listener: Callable[[int, int], None] | None = None,
    ):
        """
        Initialize RouterLLM with multiple LLM support.
        
        Args:
            agent_config: Agent configuration containing model routing settings
            llm_registry: Registry for managing LLM instances
            service_id: Service identifier for this router
            metrics: Optional metrics instance
            retry_listener: Optional retry listener callback
        """
        # Store references
        self.llm_registry = llm_registry
        self.model_routing_config = agent_config.model_routing
        
        # Get the main agent LLM
        self.main_llm = llm_registry.get_llm_from_agent_config('agent', agent_config)
        
        # Instantiate all the LLM instances for routing (same as current BaseRouter)
        llms_for_routing_config = self.model_routing_config.llms_for_routing
        self.llms_for_routing = {
            config_name: self.llm_registry.get_llm(
                f'llm_for_routing.{config_name}', config=llm_config
            )
            for config_name, llm_config in llms_for_routing_config.items()
        }
        
        # All available LLMs for routing (set this BEFORE calling super().__init__)
        self.available_llms = {
            'main': self.main_llm,
            **self.llms_for_routing
        }
        
        # Create router config based on main LLM
        router_config = copy.deepcopy(self.main_llm.config)
        
        # Update model name to indicate this is a router
        llm_names = [self.main_llm.config.model]
        if self.model_routing_config.llms_for_routing:
            llm_names.extend(config.model for config in self.model_routing_config.llms_for_routing.values())
        router_config.model = f"router({','.join(llm_names)})"
        
        # Initialize parent LLM class
        super().__init__(
            config=router_config,
            service_id=service_id,
            metrics=metrics,
            retry_listener=retry_listener,
        )
        
        # Current LLM state
        self._current_llm = self.main_llm  # Default to main LLM
        self._last_routing_decision = 'main'
        
        logger.info(f'RouterLLM initialized with {len(self.available_llms)} LLMs: {list(self.available_llms.keys())}')
    
    @abstractmethod
    def _select_llm(self, messages: list[Message], events: list[Event]) -> str:
        """
        Select which LLM to use based on messages and events.
        
        Args:
            messages: List of messages for the completion
            events: List of events from the conversation history
            
        Returns:
            Key from available_llms indicating which LLM to use
            
        Note:
            This method must be implemented by subclasses to provide specific routing logic.
        """
        pass
    
    def _get_llm_by_key(self, llm_key: str) -> LLM:
        """
        Get LLM instance by key.
        
        Args:
            llm_key: Key from available_llms
            
        Returns:
            LLM instance
            
        Raises:
            ValueError: If llm_key is not found in available_llms
        """
        if llm_key not in self.available_llms:
            raise ValueError(
                f"Unknown LLM key: {llm_key}. Available: {list(self.available_llms.keys())}"
            )
        return self.available_llms[llm_key]
    
    @property
    def completion(self) -> Callable:
        """
        Override completion to route to appropriate LLM.
        
        This method intercepts completion calls and routes them to the appropriate
        underlying LLM based on the routing logic implemented in _select_llm().
        """
        def router_completion(*args: Any, **kwargs: Any) -> Any:
            # Extract messages for routing decision
            messages = kwargs.get('messages', [])
            if args and not messages:
                messages = args[0] if args else []
            
            # Convert dict messages to Message objects if needed for routing decision
            routing_messages = self._prepare_messages_for_routing(messages)
            
            # Create events list (empty for now, but could be populated from context)
            events: list[Event] = []
            
            # Select appropriate LLM
            selected_llm_key = self._select_llm(routing_messages, events)
            selected_llm = self._get_llm_by_key(selected_llm_key)
            
            # Update current state
            self._current_llm = selected_llm
            self._last_routing_decision = selected_llm_key
            
            logger.debug(f'RouterLLM routing to {selected_llm_key} ({selected_llm.config.model})')
            
            # Delegate to selected LLM
            return selected_llm.completion(*args, **kwargs)
        
        return router_completion
    
    def _prepare_messages_for_routing(self, messages: Union[list[dict], list[Message]]) -> list[Message]:
        """
        Prepare messages for routing decision.
        
        Converts dict messages to Message objects if needed for routing logic.
        
        Args:
            messages: Raw messages from completion call
            
        Returns:
            List of Message objects suitable for routing decision
        """
        if not messages:
            return []
        
        if messages and isinstance(messages[0], dict):
            # Convert dict messages to Message objects for routing
            message_objects: list[Message] = []
            for msg in messages:
                if isinstance(msg, dict):
                    try:
                        content = msg.get('content', '')
                        if isinstance(content, str):
                            # Convert string content to TextContent list
                            content_list = [TextContent(text=content)]
                        elif isinstance(content, list):
                            # Assume it's already a list of content objects
                            content_list = content
                        else:
                            # Fallback: convert to string and wrap in TextContent
                            content_list = [TextContent(text=str(content))]
                        
                        message_objects.append(Message(
                            role=msg.get('role', 'user'),
                            content=content_list
                        ))
                    except Exception as e:
                        logger.warning(f'Failed to convert message to Message object: {e}')
                        # Fallback: create simple text message
                        message_objects.append(Message(
                            role='user',
                            content=[TextContent(text=str(msg.get('content', '')))]
                        ))
                else:
                    # This shouldn't happen in this branch, but handle it
                    message_objects.append(msg)
            return message_objects
        else:
            # Already Message objects or empty list
            return messages
    
    # Capability methods - report union of capabilities from all available LLMs
    def vision_is_active(self) -> bool:
        """
        Report if any of the available LLMs support vision.
        
        Returns:
            True if any available LLM supports vision
        """
        return any(llm.vision_is_active() for llm in self.available_llms.values())
    
    def is_function_calling_active(self) -> bool:
        """
        Report if any of the available LLMs support function calling.
        
        Returns:
            True if any available LLM supports function calling
        """
        return any(llm.is_function_calling_active() for llm in self.available_llms.values())
    
    def is_caching_prompt_active(self) -> bool:
        """
        Report if any of the available LLMs support prompt caching.
        
        Returns:
            True if any available LLM supports prompt caching
        """
        return any(llm.is_caching_prompt_active() for llm in self.available_llms.values())
    
    # Context-dependent methods - use selected LLM for accurate results
    def get_token_count(self, messages: list[dict] | list[Message]) -> int:
        """
        Use the selected LLM's tokenizer for accurate counting.
        
        Args:
            messages: Messages to count tokens for
            
        Returns:
            Token count using the appropriate LLM's tokenizer
        """
        # Make routing decision for token counting
        routing_messages = self._prepare_messages_for_routing(messages)
        selected_llm_key = self._select_llm(routing_messages, [])
        selected_llm = self._get_llm_by_key(selected_llm_key)
        
        return selected_llm.get_token_count(messages)
    
    def format_messages_for_llm(self, messages: Message | list[Message]) -> list[dict]:
        """
        Use the selected LLM's formatting rules.
        
        Args:
            messages: Messages to format
            
        Returns:
            Formatted messages using the appropriate LLM's formatting
        """
        if isinstance(messages, Message):
            messages = [messages]
        
        # Make routing decision for message formatting
        selected_llm_key = self._select_llm(messages, [])
        selected_llm = self._get_llm_by_key(selected_llm_key)
        
        return selected_llm.format_messages_for_llm(messages)
    
    def __str__(self) -> str:
        """String representation of the router."""
        return f'{self.__class__.__name__}(llms={list(self.available_llms.keys())})'
    
    def __repr__(self) -> str:
        """Detailed string representation of the router."""
        return (
            f'{self.__class__.__name__}('
            f'main={self.main_llm.config.model}, '
            f'routing_llms={[llm.config.model for llm in self.llms_for_routing.values()]}, '
            f'current={self._last_routing_decision})'
        )