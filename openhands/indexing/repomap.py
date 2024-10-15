import base64
import os
import re
import warnings
from collections import Counter, defaultdict, namedtuple
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any, Set

import git
import pathspec
from diskcache import Cache
from grep_ast import TreeContext, filename_to_lang
from pygments.lexers import guess_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound
from tqdm import tqdm
from tree_sitter_languages import get_language, get_parser

from openhands.indexing.utils import get_token_count_from_text, is_image_file

warnings.simplefilter('ignore', category=FutureWarning)

Tag = namedtuple('Tag', ('rel_fname', 'fname', 'line', 'name', 'kind'))


class RepoMap:
    CACHE_VERSION = 3
    TAGS_CACHE_DIR = f'.aider.tags.cache.v{CACHE_VERSION}'

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

        self.load_tags_cache()
        self.cache_missing = False
        self.warned_files: Set = set()

    def get_history_aware_repo_map(self, messages_history: str) -> str:
        mentioned_fnames = self.get_file_mentions(messages_history)
        mentioned_idents = self.get_identifier_mentions(messages_history)

        other_files = set(self.get_all_absolute_files())
        repo_map_content = self.get_repo_map(
            other_files=other_files,
            mentioned_fnames=mentioned_fnames,
            mentioned_idents=mentioned_idents,
        )
        if not repo_map_content:
            repo_map_content = self.get_repo_map(other_files)

        return repo_map_content

    def get_repo_map(
        self, other_files, mentioned_fnames=None, mentioned_idents=None
    ) -> str:
        if self.max_map_tokens <= 0:
            return ''
        if not other_files:
            return ''
        if not mentioned_fnames:
            mentioned_fnames = set()
        if not mentioned_idents:
            mentioned_idents = set()

        max_map_tokens = self.max_map_tokens

        try:
            files_listing = self.get_ranked_tags_map(
                other_files,
                max_map_tokens,
                mentioned_fnames,
                mentioned_idents,
            )
        except RecursionError:
            self.log_error('Disabling repo map, git repo too large?')
            self.max_map_tokens = 0
            return ''

        if not files_listing:
            return ''

        # num_tokens = self.estimate_token_count(self.model_name, files_listing)
        # logger.info(f'Repo-map: {num_tokens/1024:.1f} k-tokens')

        repo_content = self.repo_content_prefix or ''
        repo_content += files_listing

        return repo_content

    def get_ranked_tags_map(
        self,
        other_fnames=None,
        max_map_tokens=None,
        mentioned_fnames=None,
        mentioned_idents=None,
    ):
        # FIXME: implement cache if needed
        result = self.get_ranked_tags_map_uncached(
            other_fnames, max_map_tokens, mentioned_fnames, mentioned_idents
        )
        return result

    def get_ranked_tags_map_uncached(
        self,
        other_fnames=None,
        max_map_tokens=None,
        mentioned_fnames=None,
        mentioned_idents=None,
    ):
        if not other_fnames:
            other_fnames = list()
        if not max_map_tokens:
            max_map_tokens = self.max_map_tokens
        if not mentioned_fnames:
            mentioned_fnames = set()
        if not mentioned_idents:
            mentioned_idents = set()

        ranked_tags = self.get_ranked_tags(
            other_fnames, mentioned_fnames, mentioned_idents
        )

        # FIXME: Old implementation
        num_tags = len(ranked_tags)
        lower_bound = 0
        upper_bound = num_tags
        best_tree = None
        best_tree_tokens = 0

        # Guess a small starting number to help with giant repos
        middle = min(max_map_tokens // 25, num_tags)

        self.tree_cache = dict()

        while lower_bound <= upper_bound:
            tree = self.to_tree(ranked_tags[:middle])
            num_tokens = self.estimate_token_count(tree)

            if num_tokens < max_map_tokens and num_tokens > best_tree_tokens:
                best_tree = tree
                best_tree_tokens = num_tokens

            if num_tokens < max_map_tokens:
                lower_bound = middle + 1
            else:
                upper_bound = middle - 1

            middle = (lower_bound + upper_bound) // 2

        return best_tree

    def to_tree(self, tags: list):
        if not tags:
            return ''

        tags = sorted(tags)

        cur_fname: Any = None
        cur_abs_fname = None
        lois: Any = None
        output = ''

        # add a bogus tag at the end so we trip the this_fname != cur_fname...
        dummy_tag = (None,)
        for tag in tags + [dummy_tag]:
            this_rel_fname = tag[0]

            # ... here ... to output the final real entry in the list
            if this_rel_fname != cur_fname:
                if lois is not None:
                    output += cur_fname + ':\n'
                    output += self.render_tree(cur_abs_fname, cur_fname, lois)
                    lois = None
                elif cur_fname:
                    output += '\n' + cur_fname + '\n'

                if type(tag) is Tag:
                    lois = []
                    cur_abs_fname = tag.fname
                cur_fname = this_rel_fname

            if lois is not None:
                lois.append(tag.line)

        # truncate long lines, in case we get minified js or something else crazy
        output = '\n'.join([line[:100] for line in output.splitlines()]) + '\n'

        return output

    def render_tree(self, abs_fname, rel_fname, lois):
        key = (rel_fname, tuple(sorted(lois)))

        if key in self.tree_cache:
            return self.tree_cache[key]

        code = self.read_text(abs_fname) or ''
        if not code.endswith('\n'):
            code += '\n'

        context = TreeContext(
            rel_fname,
            code,
            color=False,
            line_number=False,
            child_context=False,
            last_line=False,
            margin=0,
            mark_lois=False,
            loi_pad=0,
            # header_max=30,
            show_top_of_file_parent_scope=False,
        )

        context.add_lines_of_interest(lois)
        context.add_context()
        res = context.format()
        self.tree_cache[key] = res
        return res

    def get_ranked_tags(self, other_fnames, mentioned_fnames, mentioned_idents):
        import networkx as nx

        defines = defaultdict(set)
        references = defaultdict(list)
        definitions = defaultdict(set)

        personalization = dict()

        fnames_set = set(other_fnames)
        fnames = sorted(fnames_set)

        # Default personalization for unspecified files is 1/num_nodes
        # https://networkx.org/documentation/stable/_modules/networkx/algorithms/link_analysis/pagerank_alg.html#pagerank
        personalize = 10 / len(fnames)

        if self.cache_missing:
            fnames = tqdm(fnames)
        self.cache_missing = False

        for fname in fnames:
            if not Path(fname).is_file():
                if fname not in self.warned_files:
                    if Path(fname).exists():
                        self.log_error(
                            f"Repo-map can't include {fname}, it is not a normal file"
                        )
                    else:
                        self.log_error(
                            f"Repo-map can't include {fname}, it no longer exists"
                        )

                self.warned_files.add(fname)
                continue

            # dump(fname)
            rel_fname = self.get_relative_fname(fname)

            if fname in mentioned_fnames:
                personalization[rel_fname] = personalize

            tags = list(self.get_tags(fname, rel_fname))

            for tag in tags:
                if tag.kind == 'def':
                    defines[tag.name].add(rel_fname)
                    key = (rel_fname, tag.name)
                    definitions[key].add(tag)

                if tag.kind == 'ref':
                    references[tag.name].append(rel_fname)

        ##
        # dump(defines)
        # dump(references)
        # dump(personalization)

        if not references:
            references = defaultdict(list)
            for k, v in defines.items():
                references[k] = list(v)

        idents = set(defines.keys()).intersection(set(references.keys()))

        G = nx.MultiDiGraph()

        for ident in idents:
            definers = defines[ident]
            if ident in mentioned_idents:
                mul = 10
            else:
                mul = 1
            for referencer, num_refs in Counter(references[ident]).items():
                for definer in definers:
                    # if referencer == definer:
                    #    continue
                    G.add_edge(referencer, definer, weight=mul * num_refs, ident=ident)

        if not references:
            pass

        if personalization:
            pers_args = dict(personalization=personalization, dangling=personalization)
        else:
            pers_args = dict()

        try:
            ranked = nx.pagerank(G, weight='weight', **pers_args)
        except ZeroDivisionError:
            return []

        # distribute the rank from each source node, across all of its out edges
        ranked_definitions: Any = defaultdict(float)
        for src in G.nodes:
            src_rank = ranked[src]
            total_weight = sum(
                data['weight'] for _src, _dst, data in G.out_edges(src, data=True)
            )
            # dump(src, src_rank, total_weight)
            for _src, dst, data in G.out_edges(src, data=True):
                data['rank'] = src_rank * data['weight'] / total_weight
                ident = data['ident']
                ranked_definitions[(dst, ident)] += data['rank']

        ranked_tags = []
        ranked_definitions = sorted(
            ranked_definitions.items(), reverse=True, key=lambda x: x[1]
        )

        # dump(ranked_definitions)

        for (fname, ident), rank in ranked_definitions:
            # print(f"{rank:.03f} {fname} {ident}")
            ranked_tags += list(definitions.get((fname, ident), []))

        rel_other_fnames_without_tags = set(
            self.get_relative_fname(fname) for fname in other_fnames
        )

        fnames_already_included = set(rt[0] for rt in ranked_tags)

        top_rank = sorted(
            [(rank, node) for (node, rank) in ranked.items()], reverse=True
        )
        for rank, fname in top_rank:
            if fname in rel_other_fnames_without_tags:
                rel_other_fnames_without_tags.remove(fname)
            if fname not in fnames_already_included:
                ranked_tags.append((fname,))

        for fname in rel_other_fnames_without_tags:
            ranked_tags.append((fname,))

        return ranked_tags

    def get_tags(self, fname, rel_fname):
        file_mtime = self.get_mtime(fname)
        if file_mtime is None:
            return []

        cache_key = fname
        if (
            cache_key in self.TAGS_CACHE
            and self.TAGS_CACHE[cache_key]['mtime'] == file_mtime
        ):
            return self.TAGS_CACHE[cache_key]['data']

        # miss!

        data = list(self.get_tags_raw(fname, rel_fname))

        # Update the cache
        self.TAGS_CACHE[cache_key] = {'mtime': file_mtime, 'data': data}
        # self.save_tags_cache()
        return data

    def get_tags_raw(self, fname, rel_fname):
        lang = filename_to_lang(fname)
        if not lang:
            return

        language = get_language(lang)
        parser = get_parser(lang)

        # Load the tags queries
        try:
            scm_fname = (
                resources.files('openhands.indexing')
                .joinpath('queries')
                .joinpath(f'tree-sitter-{lang}-tags.scm')
            )
        except KeyError:
            return
        query_scm = str(scm_fname)
        if not Path(query_scm).exists():
            return
        query_scm = scm_fname.read_text()

        code = self.read_text(fname)
        if not code:
            return
        tree = parser.parse(bytes(code, 'utf-8'))

        # Run the tags queries
        query = language.query(query_scm)
        captures = query.captures(tree.root_node)

        captures = list(captures)

        saw = set()
        for node, tag in captures:
            if tag.startswith('name.definition.'):
                kind = 'def'
            elif tag.startswith('name.reference.'):
                kind = 'ref'
            else:
                continue

            saw.add(kind)

            result = Tag(
                rel_fname=rel_fname,
                fname=fname,
                name=node.text.decode('utf-8'),
                kind=kind,
                line=node.start_point[0],
            )

            yield result

        if 'ref' in saw:
            return
        if 'def' not in saw:
            return

        # We saw defs, without any refs
        # Some tags files only provide defs (cpp, for example)
        # Use pygments to backfill refs

        try:
            lexer = guess_lexer_for_filename(fname, code)
        except ClassNotFound:
            return

        tokens = list(lexer.get_tokens(code))
        tokens = [token[1] for token in tokens if token[0] in Token.Name]

        for token in tokens:
            yield Tag(
                rel_fname=rel_fname,
                fname=fname,
                name=token,
                kind='ref',
                line=-1,
            )

    def read_text(self, filename):
        if is_image_file(filename):
            return self.read_image(filename)

        try:
            with open(str(filename), 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            self.log_error(
                f'Error when constructing repomap: {filename}: file not found error'
            )
            return
        except IsADirectoryError:
            self.log_error(f'{filename}: is a directory')
            return
        except UnicodeError as e:
            self.log_error(f'{filename}: {e}')
            self.log_error('Use --encoding to set the unicode encoding.')
            return

    def read_image(self, filename):
        try:
            with open(str(filename), 'rb') as image_file:
                encoded_string = base64.b64encode(image_file.read())
                return encoded_string.decode('utf-8')
        except FileNotFoundError:
            self.log_error(f'{filename}: file not found error')
            return
        except IsADirectoryError:
            self.log_error(f'{filename}: is a directory')
            return
        except Exception as e:
            self.log_error(f'{filename}: {e}')
            return

    def log_error(self, message):
        # FIXME: implement robust logging
        print(f'Error when constructing repomap: {message}')

    def load_tags_cache(self):
        path = Path(self.root) / self.TAGS_CACHE_DIR
        if not path.exists():
            self.cache_missing = True
        self.TAGS_CACHE = Cache(path)

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
                print('The repository is bare. RepoMap is empty.')
                # raise Exception('The repository is bare.')

            # Get a list of all tracked files
            tracked_files: list = [
                item.path for item in repo.tree().traverse() if item.type == 'blob'
            ]
        except git.InvalidGitRepositoryError:
            print('The directory is not a git repository. RepoMap will not be enabled.')
            return []
        except git.NoSuchPathError:
            print('The directory does not exist. RepoMap will not be enabled.')
            return []
        except Exception:
            print('An error occurred when getting tracked files in git repo')
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
            return False

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

    def get_mtime(self, fname: str):
        try:
            return os.path.getmtime(fname)
        except FileNotFoundError:
            self.log_error(f'File not found error: {fname}')

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


if __name__ == '__main__':
    repo_map = RepoMap()
    messages_hist = 'This is a test message.\nThis is another test message.'
    print(repo_map.get_history_aware_repo_map(messages_hist))
