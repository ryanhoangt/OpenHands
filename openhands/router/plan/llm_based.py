import copy
import re

from openhands.core.config import LLMConfig
from openhands.llm.llm import LLM
from openhands.router.base import BaseRouter
from openhands.router.plan.prompts import (
    TRAJECTORY_JUDGE_REASONING_SYSTEM_PROMPT,
    TRAJECTORY_JUDGE_REASONING_USER_PROMPT,
)


class LLMBasedPlanRouter(BaseRouter):
    """
    Router that routes the prompt that is judged by a LLM as complex and requires a step-by-step plan.
    """

    JUDGE_MODEL = 'gpt-4o'
    NUM_TURNS_GAP = 3

    def __init__(self, llm_config: LLMConfig):
        super().__init__()

        judge_llm_config = copy.deepcopy(llm_config)
        self.judge_llm = LLM(judge_llm_config)
        self.routed_turns: list[int] = []

    def should_route_to_custom_model(self, prompt: str) -> bool:
        cur_turn = self._extract_latest_turn_number(prompt)
        if cur_turn - max(self.routed_turns, default=0) < self.NUM_TURNS_GAP:
            return False

        messages = [
            {
                'role': 'system',
                'content': TRAJECTORY_JUDGE_REASONING_SYSTEM_PROMPT,
            },
            {
                'role': 'user',
                'content': TRAJECTORY_JUDGE_REASONING_USER_PROMPT.format(
                    interaction_log=prompt,
                    routed_turns=', '.join(map(str, self.routed_turns)),
                ),
            },
        ]

        response = self.judge_llm.completion(
            messages=messages,
            model=self.JUDGE_MODEL,
        )
        should_route = int(response['choices'][0]['message']['content'].strip()) == 1
        if should_route:
            self.routed_turns.append(cur_turn)
        return should_route

    def _extract_latest_turn_number(self, prompt: str) -> int:
        turn_numbers = re.findall(r'\*\*\* Turn (\d+) -', prompt)
        latest_turn = max(map(int, turn_numbers)) if turn_numbers else 0
        return latest_turn
