class RepoMap:
    def __init__(self, map_tokens=1024, root=None, repo_content_prefix=None) -> None:
        pass

    def get_history_aware_repo_map(self, messages: list) -> str:
        raise NotImplementedError

    def estimate_token_count(self, text):
        raise NotImplementedError
