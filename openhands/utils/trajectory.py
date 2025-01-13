"""
Utility functions for processing and formatting trajectories.
Original code from: https://github.com/SWE-Gym/SWE-Gym/blob/main/scripts/openhands-verifier/aggregate_stats_pass_at_n.ipynb
"""

import json
from dataclasses import dataclass
from typing import List, Literal, Optional, TypedDict, Union


class ToolCallFunction(TypedDict):
    name: str
    arguments: str


class ToolCall(TypedDict):
    function: ToolCallFunction
    id: str
    type: Literal['function']


class TextContent(TypedDict):
    type: Literal['text']
    text: str


class Message(TypedDict, total=False):
    role: Literal['system', 'user', 'assistant', 'tool']
    content: Union[str, List[TextContent]]
    tool_calls: Optional[List[ToolCall]]


@dataclass
class FormattingConfig:
    """Configuration for trajectory formatting."""

    separator_length: int = 100
    separator_char: str = '-'
    system_header: str = (
        "*** System Message that describes the assistant's behavior ***"
    )
    turn_header_template: str = '*** Turn {turn_id} - {role} ***'


class TrajectoryFormatter:
    def __init__(self, config: Optional[FormattingConfig] = None):
        self.config = config or FormattingConfig()

    def _convert_content(self, content: Union[str, List[TextContent]]) -> str:
        """Convert message content to string format.

        Args:
            content: Either a string or a list of text content items.

        Returns:
            Formatted string content.

        Raises:
            AssertionError: If content format is unsupported.
        """
        if isinstance(content, list):
            return '\n'.join(
                item['text'] for item in content if self._validate_text_content(item)
            )
        assert isinstance(content, str), 'Only str is supported for now'
        return content

    def _validate_text_content(self, item: TextContent) -> bool:
        """Validate text content format.

        Args:
            item: Text content item to validate.

        Returns:
            True if valid, raises AssertionError otherwise.

        Raises:
            AssertionError: If content type is not 'text'.
        """
        assert item['type'] == 'text', 'Only text is supported for now'
        return True

    def _format_tool_call(self, tool_call: ToolCall) -> str:
        """Format a tool call into string representation.

        Args:
            tool_call: Tool call dictionary to format.

        Returns:
            Formatted tool call string.

        Raises:
            ValueError: If tool call format is invalid.
        """
        self._validate_tool_call(tool_call)

        formatted = f"<function={tool_call['function']['name']}>\n"

        try:
            args = json.loads(tool_call['function']['arguments'])
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse arguments as JSON: {tool_call['function']['arguments']}"
            ) from e

        for param_name, param_value in args.items():
            is_multiline = isinstance(param_value, str) and '\n' in param_value
            param_content = (
                f'<parameter={param_name}>'
                f'{f"{param_value}" if not is_multiline else f"\n{param_value}\n"}'
                '</parameter>\n'
            )
            formatted += param_content

        return formatted + '</function>'

    def _validate_tool_call(self, tool_call: ToolCall) -> None:
        """Validate tool call format.

        Args:
            tool_call: Tool call dictionary to validate.

        Raises:
            ValueError: If tool call format is invalid.
        """
        required_keys = {'function', 'id', 'type'}
        missing_keys = required_keys - set(tool_call.keys())
        if missing_keys:
            raise ValueError(f'Tool call missing required keys: {missing_keys}')
        if tool_call['type'] != 'function':
            raise ValueError("Tool call type must be 'function'.")

    def _merge_user_messages(self, trajectory: List[Message]) -> List[Message]:
        """Merge consecutive user messages into single messages.

        Args:
            trajectory: List of messages to process.

        Returns:
            List of messages with consecutive user messages merged.
        """
        merged: List[Message] = []
        current_user_messages: List[Message] = []

        for message in trajectory:
            if message['role'] == 'user':
                current_user_messages.append(message)
            else:
                if current_user_messages:
                    merged_content = '\n'.join(
                        self._convert_content(msg['content'])
                        for msg in current_user_messages
                    )
                    merged.append({'role': 'user', 'content': merged_content})
                    current_user_messages = []
                merged.append(message)

        if current_user_messages:
            merged_content = '\n'.join(
                self._convert_content(msg['content']) for msg in current_user_messages
            )
            merged.append({'role': 'user', 'content': merged_content})

        return merged

    def format_trajectory(self, trajectory: List[Message]) -> str:
        """Format a conversation trajectory into a readable string.

        Args:
            trajectory: List of conversation messages to format.

        Returns:
            Formatted conversation string.

        Raises:
            ValueError: If message role is unexpected.
        """
        output = []

        # Handle system message if present
        if trajectory and trajectory[0]['role'] == 'system':
            system_message = trajectory[0]
            content = self._convert_content(system_message['content'])
            output.extend([self.config.system_header, f'{content}\n'])
            trajectory = trajectory[1:]

        # Merge and process trajectory
        merged_trajectory = self._merge_user_messages(trajectory)

        for i, message in enumerate(merged_trajectory):
            role = message['role']
            content = self._convert_content(message['content'])
            turn_id = i // 2 + 1

            output.extend(
                [
                    self.config.separator_char * self.config.separator_length,
                    self.config.turn_header_template.format(
                        turn_id=turn_id,
                        role=role.upper()
                        if role != 'tool'
                        else 'TOOL EXECUTION RESULT',
                    ),
                ]
            )

            if role == 'assistant' and message.get('tool_calls'):
                output.extend(
                    [
                        content,
                        *[
                            f'### Tool Call {i}\n{self._format_tool_call(tool_call)}'
                            for i, tool_call in enumerate(message['tool_calls'] or [])
                        ],
                    ]
                )
            else:
                output.append(content)

        output.append(self.config.separator_char * self.config.separator_length)
        return '\n'.join(output)
