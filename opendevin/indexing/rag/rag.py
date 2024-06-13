import os

from dotenv import load_dotenv
from llama_index.core import (
    ServiceContext,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.readers.file import FlatReader
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.readers.gpt_repo import GPTRepoReader
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone
from tqdm import tqdm

load_dotenv()


class VectorIndex:
    embedding_model_name = 'jinaai/jina-embeddings-v2-base-code'
    # index_name = 'sphi-82ef497a8c88f0f6e50d84520e7276bfbf65025d'

    def __init__(self, index_name=None) -> None:
        db = Pinecone(
            api_key=os.getenv('PINECONE_API_KEY'),
        )
        if index_name is None:
            # create a new index with a random name
            pc_index = db.create_index(name='my_index', dimension=768)
        else:
            pc_index = db.Index(index_name)

        self.vector_store = PineconeVectorStore(pinecone_index=pc_index)
        self.embed_model = HuggingFaceEmbedding(
            model_name=self.embedding_model_name,
            embed_batch_size=3,
            trust_remote_code=True,
        )

        # Debugging stuff
        llama_debug_cb = LlamaDebugHandler(print_trace_on_end=True)  # print trace
        callback_manager = CallbackManager(handlers=[llama_debug_cb])
        self.service_context = ServiceContext.from_defaults(
            callback_manager=callback_manager
        )
        self.storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )

        self.index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store,
            embed_model=self.embed_model,
            service_context=self.service_context,
        )
        self.llm = OpenAI(model='gpt-3.5-turbo', temperature=0.0)

    def retrieve(self, query: str, k: int) -> list:
        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=k,
        )
        results = retriever.retrieve(query)
        # return the text and the source info
        return [(r.get_text(), r.node.metadata) for r in results]

    def query(self, query: str) -> str:
        query_engine = self.index.as_query_engine()

        response = query_engine.query(query)
        return response

    def ingest_directory(self, repo_path: str) -> None:
        required_exts = ['.py', '.md', '.sh']
        parser = FlatReader()

        dir_reader = SimpleDirectoryReader(
            input_dir=repo_path,
            file_extractor={
                '.py': parser,
                '.md': parser,
                '.sh': parser,
            },  # TODO: add more file types
            required_exts=required_exts,
            recursive=True,
        )
        docs = dir_reader.load_data()

        # node_parser = SimpleNodeParser.from_defaults(
        #     chunk_size=500,
        #     chunk_overlap=20,
        # )

        # read from documents
        for doc in docs:
            self.index.insert(document=doc)

    def ingest_github_repo(self, owner: str, repo: str, commit_sha: str) -> None:
        github_token = os.environ.get('GITHUB_TOKEN')
        github_client = GithubClient(github_token=github_token, verbose=True)

        documents = GithubRepositoryReader(
            github_client=github_client,
            owner=owner,
            repo=repo,
            use_parser=False,
            verbose=False,
            filter_file_extensions=(
                [
                    '.py'  # TODO: add more file types
                ],
                GithubRepositoryReader.FilterType.INCLUDE,
            ),
        ).load_data(commit_sha=commit_sha)

        # insert with tqdm progress bar
        for doc in tqdm(documents):
            self.index.insert(document=doc)

        print(f'Indexed {len(documents)} documents')

    def ingest_git_repo(self, repo_path: str) -> None:
        reader = GPTRepoReader()
        documents = reader.load_data(
            repo_path=repo_path, extensions=['.py', '.md', '.sh']
        )
        ingest_pipeline = IngestionPipeline(
            transformations=[
                self.embed_model,
            ],
            vector_store=self.vector_store,
        )

        embedded_nodes = ingest_pipeline.run(documents=documents, show_progress=True)

        print(f'Embedded {len(embedded_nodes)} vectors.')


if __name__ == '__main__':
    vi = VectorIndex('test-code-index')
    # vi.ingest_repo('sphinx-doc', 'sphinx', '82ef497a8c88f0f6e50d84520e7276bfbf65025d')
    vi.ingest_git_repo('/home/ryan/sphinx')

    response = vi.retrieve(
        'viewcode creates pages for epub even if `viewcode_enable_epub=False` on `make html epub`',
        10,
    )
    for i, r in enumerate(response):
        # pretty print
        print('Result', i + 1, ':')
        text, metadata = r
        print('Text:', text)
        for key, value in metadata.items():
            print(key, ':', value)
    # vi.ingest_git_repo(
    #     repo_path='/Users/ryan/Developer/files-localization-for-code-gen-agents/llamaindex-playground'
    # )