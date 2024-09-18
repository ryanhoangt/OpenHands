import os
import re
from pathlib import Path, PurePosixPath

import git
import pathspec

if __package__ is None or __package__ == '':
    from utils import get_token_count_from_text
else:
    from openhands.runtime.plugins.agent_skills.utils.aider.utils import (
        get_token_count_from_text,
    )


class RepoMap:
    def __init__(
        self,
        map_tokens=1024,
        root=None,
        model_name=None,
        repo_content_prefix=None,
        aider_ignore_file='.aiderignore',
    ) -> None:
        self.max_map_tokens = map_tokens

        if not root:
            root = os.getcwd()
        self.root = root

        self.model_name = model_name
        self.repo_content_prefix = repo_content_prefix

        self.aider_ignore_file = Path(aider_ignore_file)
        self.aider_ignore_ts = 0

    def get_history_aware_repo_map(self, messages: list) -> str:
        full_messages_text = self.get_full_messages_text(messages)
        mentioned_fnames = self.get_file_mentions(full_messages_text)
        mentioned_idents = self.get_identifier_mentions(full_messages_text)

        other_files = set(self.get_all_absolute_files())
        repo_map_content = self.get_repo_map(
            other_files=other_files,
            mentioned_fnames=mentioned_fnames,
            mentioned_idents=mentioned_idents,
        )
        if not repo_map_content:
            repo_map_content = self.get_repo_map(other_files)

        return repo_map_content

    def get_repo_map(self, other_files, mentioned_fnames=None, mentioned_idents=None):
        raise NotImplementedError

    def estimate_token_count(self, text):
        """
        An efficient way to estimate the token count of the given text.
        """
        len_text = len(text)
        if len_text < 200:
            return get_token_count_from_text(self.model_name, text)

        lines = text.splitlines(keepends=True)
        num_lines = len(lines)
        step = num_lines // 100 or 1
        lines = lines[::step]
        sample_text = ''.join(lines)
        sample_tokens = get_token_count_from_text(self.model_name, sample_text)
        est_tokens = sample_tokens / len(sample_text) * len_text
        return est_tokens

    def get_full_messages_text(self, messages: list) -> str:
        return '\n'.join([msg['content'] for msg in messages])

    def get_file_mentions(self, full_messages_text: str):
        words = set(word for word in full_messages_text.split())

        # Drop sentence punctuation from the end
        words = set(word.rstrip(',.!;:') for word in words)

        # Strip away all kinds of quotes
        quotes = ''.join(['"', "'", '`'])
        words = set(word.strip(quotes) for word in words)

        addable_rel_fnames = self.get_addable_relative_files()

        mentioned_rel_fnames = set()
        fname_to_rel_fnames: dict = {}
        for rel_fname in addable_rel_fnames:
            if rel_fname in words:
                mentioned_rel_fnames.add(str(rel_fname))

            fname = os.path.basename(rel_fname)

            # Don't add basenames that could be plain words like "run" or "make"
            if '/' in fname or '.' in fname or '_' in fname or '-' in fname:
                if fname not in fname_to_rel_fnames:
                    fname_to_rel_fnames[fname] = []
                fname_to_rel_fnames[fname].append(rel_fname)

        for fname, rel_fnames in fname_to_rel_fnames.items():
            if len(rel_fnames) == 1 and fname in words:
                mentioned_rel_fnames.add(rel_fnames[0])

        return list(mentioned_rel_fnames)

    def get_identifier_mentions(self, text: str):
        # Split the string on any character that is not alphanumeric
        # \W+ matches one or more non-word characters (equivalent to [^a-zA-Z0-9_]+)
        words = set(re.split(r'\W+', text))
        return words

    # ================== File utils ==================
    def get_addable_relative_files(self):
        return set(self.get_all_relative_files())

    def get_all_absolute_files(self):
        rel_files = self.get_all_relative_files()
        abs_files = [self.get_absolute_path(rel_path) for rel_path in rel_files]
        return abs_files

    def get_all_relative_files(self):
        # Construct a git repo object and get all the relative files tracked by git and staged files
        try:
            repo = git.Repo(self.root)

            if repo.bare:
                raise Exception('The repository is bare.')

            # Get a list of all tracked files
            tracked_files: list = [
                item.path for item in repo.tree().traverse() if item.type == 'blob'
            ]
        except git.InvalidGitRepositoryError:
            # logger.error(
            #     'The directory is not a git repository. RepoMap will not be enabled.'
            # )
            return []
        except git.NoSuchPathError:
            # logger.error('The directory does not exist. RepoMap will not be enabled.')
            return []
        except Exception:
            # logger.error(
            #     f'An error occurred when getting tracked files in git repo: {e}'
            # )
            return []

        # Add staged files
        index = repo.index
        staged_files = [path for path, _ in index.entries.keys()]
        tracked_files.extend(staged_files)

        # Normalize the paths
        tracked_files = list(set(self.normalize_path(path) for path in tracked_files))
        tracked_files = [
            fname for fname in tracked_files if not self.file_is_ignored(fname)
        ]

        files = [
            fname
            for fname in tracked_files
            if Path(self.get_absolute_path(fname)).is_file()
        ]
        return sorted(set(files))

    def file_is_ignored(self, fname: str) -> bool:
        if not self.aider_ignore_file or not self.aider_ignore_file.is_file():
            return True

        try:
            fname = self.normalize_path(fname)
        except ValueError:
            return True

        mtime = int(self.aider_ignore_file.stat().st_mtime)
        if self.aider_ignore_ts != mtime:
            self.aider_ignore_ts = int(mtime)

            lines = self.aider_ignore_file.read_text().splitlines()
            self.aider_ignore_spec = pathspec.PathSpec.from_lines(
                pathspec.patterns.GitWildMatchPattern,
                lines,
            )

        return self.aider_ignore_spec.match_file(fname)

    # ================== Path utils ==================
    def get_absolute_path(self, rel_path):
        res = Path(self.root) / rel_path
        return self.safe_absolute_path(res)

    def get_relative_fname(self, abs_path):
        return os.path.relpath(abs_path, self.root)

    def safe_absolute_path(self, res):
        res = Path(res).resolve()
        return str(res)

    def normalize_path(self, path):
        return str(Path(PurePosixPath((Path(self.root) / path).relative_to(self.root))))
