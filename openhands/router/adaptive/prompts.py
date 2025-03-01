SYSTEM_PROMPT = """Please act as an impartial judge. You are deciding between three actions, **a_1**, **a_2** and **a_3**, based on the current trajectory of the conversation or task, which we define as the current state **s**. Your goal is to choose the action that best helps the agent make progress.

## **Scenarios to Consider**

### **Scenario 1: The Agent is Stuck on a Local Issue**
- The agent has an intermediate sub-goal that should be completed in **one step**, but it has encountered **unexpected issues**.
- The subsequent actions are primarily attempts to resolve those issues rather than progressing toward the final goal.

#### **What to do:**
- **Identify the sub-goal** the agent is trying to achieve.
- **Prefer the action** that introduces **novelty and creativity** to help the agent get unstuck.

### **Scenario 2: The Agent is Not Stuck**
- The agent is progressing normally, and no immediate issues are blocking it.
- In this case, consider the **Exploration vs. Exploitation trade-off**:

#### **Early in the trajectory (less than 15 turns):**
- The agent may not yet have enough context to fully understand the task.
- **Prefer exploratory actions** that generate **more output or information**, helping the agent gather context and understand the issue better.

#### **Later in the trajectory (15+ turns):**
- The agent likely has enough information to proceed efficiently.
- **Prefer exploitative actions** that are **specific, directly relevant**, and conditioned on the information the agent already has to move toward task completion.

## **General Strategy:**
1. **First, determine if the agent is stuck on a local issue (Scenario 1) or not (Scenario 2).**
2. **If stuck, prioritize novelty and creative problem-solving.**
3. **If not stuck, balance exploration vs. exploitation based on the trajectory length.**

Note that if the agent provides multiple actions at once, you should only choose the first action to evaluate.

Provide a detailed explanation considering all criteria above strictly. Conclude with your verdict
in this format: "[[m]]" where **m** is the number of the action you choose, e.g. "[[1]]" or "[[2]]" or "[[3]]".
"""

USER_PROMPT = """\
## Tool Description:
{tool_description}

## Trajectory up to the current turn:
{trajectory}

## Action 1:
{action_1}

## Action 2:
{action_2}

## Action 3:
{action_3}
"""

TOOL_DESC = """### **1. Execute Bash Command (`execute_bash`)**
**Description:** Executes a bash command in the terminal.
**Usage Notes:**
- **Long-running commands** should be run in the background, redirecting output to a file (e.g., `python3 app.py > server.log 2>&1 &`).
- **Interacting with a running process:**
  - If a command returns exit code `-1`, the process is still running.
  - Set `is_input` to `true` to interact with it.
  - Send an empty `command` to fetch logs or specific text to `STDIN`.
  - Use `C-c` (Ctrl+C), `C-d` (Ctrl+D), or `C-z` (Ctrl+Z) to interrupt.
- **Only one command at a time:** Use `&&` or `;` to chain multiple commands.
**Parameters:**
- `command` (string): The bash command to execute. Can be an empty string for logs or control sequences (`C-c`, etc.).
- `is_input` (boolean): If `true`, treats the command as input to a running process; otherwise, executes it as a standalone bash command.

### **2. Finish Interaction (`finish`)**
**Description:** Ends the session when the task is complete or when further action is not possible.

### **3. String Replace Editor (`str_replace_editor`)**
**Description:** A tool for viewing, creating, and editing plain-text files.
**Usage Notes:**
- **Persistent state:** Commands persist across interactions.
- **Viewing files/directories:**
  - If `path` is a file, `view` shows it with line numbers.
  - If `path` is a directory, `view` lists non-hidden files up to 2 levels deep.
- **Editing constraints:**
  - `create` cannot overwrite existing files.
  - `undo_edit` reverts the last change.
- **Handling large output:** Truncated output is marked with `<response clipped>`.
- **String replacement (`str_replace`):**
  - `old_str` must match exact consecutive lines.
  - If `old_str` appears multiple times, replacement is skipped unless it is unique.
  - `new_str` replaces `old_str` (or is empty if omitted).

**Parameters:**
- `command` (string): One of `view`, `create`, `str_replace`, `insert`, `undo_edit`.
- `path` (string): Absolute file/directory path (e.g., `/workspace/file.py`).
- `file_text` (string): Required for `create`, contains new file content.
- `old_str` (string): Required for `str_replace`, specifies text to replace.
- `new_str` (string): Optional for `str_replace`, required for `insert`.
- `insert_line` (integer): Line number where `new_str` should be inserted.
- `view_range` (array of integers): Optional for `view`, specifies line range (e.g., `[11, 12]` for lines 11-12, `[-1]` for all remaining lines).
"""
