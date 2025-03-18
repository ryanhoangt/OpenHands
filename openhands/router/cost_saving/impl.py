import numpy as np
import sglang as sgl
from sglang import RuntimeEndpoint, set_default_backend, system, user

from openhands.core.config import ModelRoutingConfig
from openhands.llm.llm import LLM
from openhands.router.base import BaseRouter
from openhands.router.cost_saving.prompts import (
    TRAJECTORY_JUDGE_COST_SAVING_SYSTEM_PROMPT,
    TRAJECTORY_JUDGE_COST_SAVING_USER_PROMPT,
)

set_default_backend(
    RuntimeEndpoint(
        base_url='https://weofgkeh1d64v9.r20.modal.host',
        api_key='minhnguyet',
    )
)


@sgl.function
def score_trajectory(s, trajectory, **kwargs):
    s += system(TRAJECTORY_JUDGE_COST_SAVING_SYSTEM_PROMPT)
    s += user(TRAJECTORY_JUDGE_COST_SAVING_USER_PROMPT.format(conversation=trajectory))
    s += sgl.gen(
        'answer',
        choices=['0', '1'],
        return_logprob=True,
        choices_method=sgl.token_length_normalized,
    )


class CostSavingRouter(BaseRouter):
    WEAK_MODEL_CONFIG = 'weak_model'
    CPT_THRESHOLD = 0.7549149868676284

    def __init__(
        self,
        llm: LLM,
        routing_llms: dict[str, LLM],
        model_routing_config: ModelRoutingConfig,
    ):
        super().__init__(llm, routing_llms, model_routing_config)

        self._validate_model_routing_config(model_routing_config, routing_llms)

        self.judge_llm = routing_llms[model_routing_config.judge_llm_config_name]
        self.weak_llm = routing_llms[self.WEAK_MODEL_CONFIG]
        self.routing_history: list[int] = []
        self.max_token_exceeded = False

    def should_route_to(self, prompt: str) -> LLM:
        if self.max_token_exceeded:
            self.routing_history.append(0)
            return self.llm

        # messages = [
        #     {
        #         'role': 'system',
        #         'content': TRAJECTORY_JUDGE_COST_SAVING_SYSTEM_PROMPT,
        #     },
        #     {
        #         'role': 'user',
        #         'content': TRAJECTORY_JUDGE_COST_SAVING_USER_PROMPT.format(
        #             conversation=prompt
        #         ),
        #     },
        # ]

        state = score_trajectory(prompt)
        logit_0 = np.exp(state.get_meta_info('answer')['input_token_logprobs'][0][0][0])
        logit_1 = np.exp(state.get_meta_info('answer')['input_token_logprobs'][1][0][0])
        threshold = logit_1 / (logit_0 + logit_1)
        print('CostSavingRouter threshold:', threshold)

        if threshold < self.CPT_THRESHOLD:
            self.routing_history.append(0)
            return self.llm

        self.routing_history.append(1)
        return self.weak_llm

        # try:
        #     response = self.judge_llm.completion(
        #         messages=messages,
        #     )
        # except Exception as e:
        #     print('❌ Failed to get response from judge LLM:', e)
        #     self.routing_history.append(0)
        #     self.max_token_exceeded = True
        #     return self.llm

        # try:
        #     should_route = (
        #         int(response['choices'][0]['message']['content'].strip()) == 1
        #     )
        #     # print('CostSavingRouter should_route:', should_route)
        # except ValueError:
        #     print('❌ Invalid response from judge LLM, using default LLM:', response)
        #     should_route = False

        # if should_route:
        #     self.routing_history.append(1)
        #     return self.weak_llm

        # self.routing_history.append(0)
        # return self.llm

    def _validate_model_routing_config(
        self, model_routing_config: ModelRoutingConfig, routing_llms: dict[str, LLM]
    ):
        if self.WEAK_MODEL_CONFIG not in routing_llms:
            raise ValueError(
                f'Weak LLM config {model_routing_config.reasoning_llm_config_name} not found'
            )
