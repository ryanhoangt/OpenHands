instruction_template = """
<uploaded_files>
/workspace/{workspace_dir_name}
</uploaded_files>
I've uploaded a python code repository in the directory {workspace_dir_name}. Consider the following PR description:

<pr_description>
{problem_statement}
</pr_description>

My teammate was working on that PR, but they had to leave the project midway. I'm not sure if the changes they made are sufficient to meet the requirements of the PR.
Can you help me carefully review the changes to the repository and continue working on it if needed so that the requirements specified in the <pr_description> are met? Pay attention to edge cases and the reproduction script indeed reproduces the mentioned error.

Here are the diff changes made by my teammate, and it has been applied to the repository using `git apply`:
--------
{cur_diff_changes}
--------

It is possible that the changes made by my teammate are incorrect or incomplete. If you find any issues, please fix them. If you think the changes are correct and complete, you can exit.
You are allowed to explore the codebase more to verify the correctness of the changes or make additional changes if required.
I've already taken care of all changes to any of the test files described in the <pr_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
The task is to make the minimal changes to non-tests files in the /workspace/{workspace_dir_name} directory to ensure the <pr_description> is satisfied.
Follow these steps to resolve the issue:
1. As a first step, it might be a good idea to explore the repo to familiarize yourself with its structure.
2. Create a script in the above directory to reproduce the error and execute it with `python <filename.py>` using the BashTool, to confirm the error.
3. Edit the sourcecode of the repo to resolve the issue.
4. Rerun your reproduce script and confirm that the error is fixed!
5. Think about edgecases and make sure your fix handles them as well
"Your thinking should be thorough and so it's fine if it's very long."""
