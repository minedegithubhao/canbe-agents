from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中配置。

    配置从 .env 读取，并用默认值保证本地开发时能启动。
    命名上按外部依赖和检索参数分组：LLM、Mongo、Milvus、ES、Redis、百炼、retrieval。
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "faq-rag-assistant"
    # Mongo 集合名前缀，例如 canbe_faq_rag_faq_items、canbe_faq_rag_chat_logs；
    # 用于让同一个 MongoDB database 中的不同项目数据彼此隔离。
    project_prefix: str = "canbe_faq_rag"

    jd_help_cleaned_jsonl_path: Path = Field(default=Path("exports/jd_help_faq.cleaned.jsonl"))
    jd_help_chunks_jsonl_path: Path = Field(default=Path("exports/jd_help_faq.chunks.jsonl"))
    jd_help_synonyms_path: Path = Field(default=Path("configs/jd_help_synonyms.yaml"))

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: int = 60

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "canbe_faq_rag"

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_collection: str = "canbe_faq_rag_vector_index"

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_username: str = ""
    elasticsearch_password: str = ""
    elasticsearch_index: str = "canbe_faq_rag_search_index"

    redis_url: str = "redis://localhost:6379/0"
    redis_prefix: str = "canbe_faq_rag"

    bailian_api_key: str = ""
    dashscope_api_key: str = ""
    bailian_embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bailian_embedding_model: str = "text-embedding-v4"
    bailian_embedding_dimension: int = 1024
    bailian_embedding_batch_size: int = 10
    bailian_embedding_timeout_seconds: int = 60
    bailian_rerank_base_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1"
    bailian_rerank_model: str = "qwen3-rerank"
    bailian_rerank_timeout_seconds: int = 60

    retrieval_dense_top_k: int = 20
    retrieval_sparse_top_k: int = 20
    retrieval_keyword_top_k: int = 20
    retrieval_final_top_k: int = 5
    retrieval_prompt_top_k: int = 3
    retrieval_rrf_k: int = 60
    retrieval_medium_confidence_threshold: float = 0.65
    retrieval_rerank_candidate_multiplier: int = 4

    @property
    def bailian_effective_api_key(self) -> str:
        """兼容两种环境变量命名：优先 BAILIAN_API_KEY，回退 DASHSCOPE_API_KEY。"""
        return self.bailian_api_key or self.dashscope_api_key


@lru_cache
def get_settings() -> Settings:
    """缓存配置对象，避免每次请求重复解析 .env。"""
    return Settings()
