if __package__ is None or __package__ == '':
    from linter import Linter, LintResult
    from repomap import RepoMap
else:
    from openhands.runtime.plugins.agent_skills.utils.aider.linter import (
        Linter,
        LintResult,
    )
    from openhands.runtime.plugins.agent_skills.utils.aider.repomap import RepoMap

__all__ = ['Linter', 'LintResult', 'RepoMap']
