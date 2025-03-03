import numpy as np

from openhands.core.config.model_routing_config import ModelRoutingConfig
from openhands.llm.llm import LLM
from openhands.router.base import BaseRouter


class RandomRouter(BaseRouter):
    # PERCENTAGE_CALLS_TO_STRONG_LLM = 0.2
    WEAK_MODEL_CONFIG = 'weak_model'
    REASONING_MODEL_CONFIG = 'reasoning_model'

    def __init__(
        self,
        llm: LLM,
        routing_llms: dict[str, LLM],
        model_routing_config: ModelRoutingConfig,
    ):
        self.llm = llm
        self.routing_llms = routing_llms
        self.model_routing_config = model_routing_config

        print(f'RandomRouter initialized with {len(routing_llms)} routing LLMs')

    def should_route_to(self, prompt: str) -> LLM:
        random = np.random.randint(0, 3) + 1
        print('RandomRouter random:', random)
        if random == 1:
            return self.llm  # Use default LLM

        if random == 2:
            return self.routing_llms[self.REASONING_MODEL_CONFIG]

        return self.routing_llms[self.WEAK_MODEL_CONFIG]
