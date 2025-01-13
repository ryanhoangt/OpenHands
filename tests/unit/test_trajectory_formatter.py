from typing import List

import pytest

from openhands.utils.trajectory import (
    FormattingConfig,
    Message,
    TextContent,
    ToolCall,
    TrajectoryFormatter,
)


@pytest.fixture
def formatter():
    """Fixture providing default TrajectoryFormatter instance."""
    return TrajectoryFormatter()


@pytest.fixture
def custom_formatter():
    """Fixture providing TrajectoryFormatter with custom configuration."""
    config = FormattingConfig(
        separator_length=80,
        separator_char='*',
        system_header='### System Message ###',
        turn_header_template='### Turn {turn_id} - {role} ###',
    )
    return TrajectoryFormatter(config)


class TestContentConversion:
    def test_convert_string_content(self, formatter):
        """Test converting simple string content."""
        input_content = 'Hello, world!'
        result = formatter._convert_content(input_content)
        assert result == 'Hello, world!'

    def test_convert_text_list(self, formatter):
        """Test converting list of text items."""
        input_content: List[TextContent] = [
            {'type': 'text', 'text': 'Hello'},
            {'type': 'text', 'text': 'world'},
        ]
        result = formatter._convert_content(input_content)
        assert result == 'Hello\nworld'

    def test_invalid_content_type(self, formatter):
        """Test handling invalid content type."""
        invalid_content = [{'type': 'invalid', 'text': 'test'}]
        with pytest.raises(AssertionError):
            formatter._convert_content(invalid_content)


class TestToolCallFormatting:
    def test_valid_tool_call(self, formatter):
        """Test formatting valid tool call."""
        tool_call: ToolCall = {
            'id': 'call_123',
            'type': 'function',
            'function': {
                'name': 'test_function',
                'arguments': '{"param1": "value1", "param2": "value2"}',
            },
        }
        result = formatter._format_tool_call(tool_call)
        expected = (
            '<function=test_function>\n'
            '<parameter=param1>value1</parameter>\n'
            '<parameter=param2>value2</parameter>\n'
            '</function>'
        )
        assert result == expected

    def test_missing_required_keys(self, formatter):
        """Test handling tool call with missing required keys."""
        invalid_tool_call = {'function': {'name': 'test_function', 'arguments': '{}'}}
        with pytest.raises(ValueError, match='Tool call missing required keys'):
            formatter._format_tool_call(invalid_tool_call)

    def test_invalid_json_arguments(self, formatter):
        """Test handling invalid JSON in tool call arguments."""
        tool_call: ToolCall = {
            'id': 'call_123',
            'type': 'function',
            'function': {'name': 'test_function', 'arguments': 'invalid json'},
        }
        with pytest.raises(ValueError, match='Failed to parse arguments as JSON'):
            formatter._format_tool_call(tool_call)

    def test_multiline_arguments(self, formatter):
        """Test handling multiline arguments in tool call."""
        tool_call: ToolCall = {
            'id': 'call_123',
            'type': 'function',
            'function': {
                'name': 'test_function',
                'arguments': '{"code": "line1\\nline2\\nline3"}',
            },
        }
        result = formatter._format_tool_call(tool_call)
        assert '<parameter=code>\nline1\nline2\nline3\n</parameter>' in result


class TestTrajectoryFormatting:
    def test_simple_conversation(self, formatter):
        """Test formatting simple conversation."""
        trajectory: List[Message] = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi there!'},
        ]
        result = formatter.format_trajectory(trajectory)
        assert 'Turn 1 - USER' in result
        assert 'Hello' in result
        assert 'Turn 1 - ASSISTANT' in result
        assert 'Hi there!' in result

    def test_with_system_message(self, formatter):
        """Test formatting conversation with system message."""
        trajectory: List[Message] = [
            {'role': 'system', 'content': 'System prompt'},
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi'},
        ]
        result = formatter.format_trajectory(trajectory)
        assert "System Message that describes the assistant's behavior" in result
        assert 'System prompt' in result
        assert 'Turn 1 - USER' in result

    def test_merge_user_messages(self, formatter):
        """Test merging consecutive user messages."""
        trajectory: List[Message] = [
            {'role': 'user', 'content': 'Message 1'},
            {'role': 'user', 'content': 'Message 2'},
            {'role': 'assistant', 'content': 'Response'},
        ]
        result = formatter.format_trajectory(trajectory)
        assert 'Message 1\nMessage 2' in result
        assert 'Turn 1 - USER' in result
        assert result.count('USER') == 1

    def test_with_tool_calls(self, formatter):
        """Test formatting conversation with tool calls."""
        trajectory: List[Message] = [
            {'role': 'user', 'content': 'Do something'},
            {
                'role': 'assistant',
                'content': 'Let me help',
                'tool_calls': [
                    {
                        'id': 'call_123',
                        'type': 'function',
                        'function': {
                            'name': 'test_function',
                            'arguments': '{"param": "value"}',
                        },
                    }
                ],
            },
        ]
        result = formatter.format_trajectory(trajectory)
        assert 'Tool Call 0' in result
        assert '<function=test_function>' in result
        assert '<parameter=param>value</parameter>' in result


class TestCustomConfiguration:
    def test_custom_formatting(self, custom_formatter):
        """Test formatting with custom configuration."""
        trajectory: List[Message] = [
            {'role': 'system', 'content': 'System message'},
            {'role': 'user', 'content': 'Hello'},
        ]
        result = custom_formatter.format_trajectory(trajectory)
        assert '### System Message ###' in result
        assert '### Turn 1 - USER ###' in result
        assert '*' * 80 in result

    def test_different_separator_length(self, custom_formatter):
        """Test custom separator length."""
        trajectory: List[Message] = [{'role': 'user', 'content': 'Test'}]
        result = custom_formatter.format_trajectory(trajectory)
        separator_line = '*' * 80
        assert separator_line in result
        assert '-' * 100 not in result  # Default separator should not be present


def test_empty_trajectory(formatter):
    """Test handling empty trajectory."""
    result = formatter.format_trajectory([])
    assert result.strip() == '-' * 100


def test_tool_execution_result(formatter):
    """Test formatting tool execution results."""
    trajectory: List[Message] = [
        {'role': 'user', 'content': 'Command'},
        {
            'role': 'assistant',
            'content': 'Executing',
            'tool_calls': [
                {
                    'id': '1',
                    'type': 'function',
                    'function': {'name': 'test', 'arguments': '{}'},
                }
            ],
        },
        {'role': 'tool', 'content': 'Result'},
    ]
    result = formatter.format_trajectory(trajectory)
    assert 'TOOL EXECUTION RESULT' in result
    assert 'Result' in result
