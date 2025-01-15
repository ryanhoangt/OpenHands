from notdiamond import NotDiamond

from openhands.core.config import ModelRoutingConfig
from openhands.router.base import BaseRouter


class NotDiamondRouter(BaseRouter):
    """
    Router that aims to reduce cost by routing to a cheaper model if the next step is not complex.
    """

    SUPPORTED_MODELS = [
        'anthropic/claude-3-5-sonnet-20241022',
        'mistral/mistral-large-2407',
        'openai/gpt-4o-2024-08-06',
        'openai/gpt-4o-mini-2024-07-18',
    ]

    def __init__(self, model_routing_config: ModelRoutingConfig):
        super().__init__()

        self.model_routing_config = model_routing_config

        assert (
            model_routing_config.nd_api_key is not None
        ), 'NotDiamond API key must be provided for NotDiamondRouter'
        self._client = NotDiamond(api_key=model_routing_config.nd_api_key)

    def get_recommended_model(self, messages: list) -> str:
        _, provider = self._client.chat.completions.model_select(
            messages=messages,
            model=self.SUPPORTED_MODELS,
            preference_id=self.model_routing_config.nd_router_id,
        )
        return provider

    def should_route_to_custom_model(self, prompt: str) -> bool:
        raise NotImplementedError('This method is not supported for this router.')
