from abc import abstractmethod

from openhands.core.config.model_routing_config import ModelRoutingConfig
from openhands.llm.llm import LLM


class BaseRouter:
    def __init__(
        self,
        llm: LLM,
        routing_llms: dict[str, LLM],
        model_routing_config: ModelRoutingConfig,
    ):
        self.llm = llm
        self.routing_llms = routing_llms
        self.model_routing_config = model_routing_config


class PredictiveRouter(BaseRouter):
    """
    Router that predicts which model to use without generating full responses.
    Only predicts the best model to route to based on the prompt.
    """

    @abstractmethod
    def should_route_to(self, prompt: str) -> LLM:
        pass


class GenerativeRouter(BaseRouter):
    """
    Router that generates responses from multiple models and selects the best one.
    Generates actual responses and compares them before returning the best one.
    """

    @abstractmethod
    def select_best_response(self, prompt: str, responses: dict[str, str]) -> str:
        pass
