"""
config.py - Configurations for heraldapp
"""
from typing import Annotated as A, Literal, Any
import os
from pathlib import Path
from functools import lru_cache
from pydantic import Field, computed_field, AfterValidator, BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent

class ModelConfig(BaseModel):
    """
    Configuration for a model. Supported backends:
      - openai     : OpenAI or Azure OpenAI (url is the deployment endpoint)
      - anthropic  : Claude via Anthropic API (url optional, only if proxying)
      - vllm       : Self-hosted vLLM HTTP server, OpenAI-compatible (url is the vLLM endpoint)
    """
    type: A[
        Literal["local", "openai", "anthropic", "vllm"],
        Field(description="Backend type — see ModelConfig docstring for options")
    ]
    name: A[str, Field(description="Model name (HF model id, OpenAI deployment, or Anthropic model name)")]
    url: A[str|None, Field(description="API base URL (required for openai and vllm)")] = None
    key: A[str|None, Field(description="API key or token")] = None
    extra_args: A[dict[str, Any], Field(description="Extra kwargs forwarded to the model, e.g. temperature")] = {}

    @model_validator(mode='after')
    def is_valid(self):
        if self.type == "openai" and not self.url:
            raise ValueError("URL is required for type='openai' (use the Azure deployment endpoint)")
        if self.type == "vllm" and not self.url:
            raise ValueError("URL is required for type='vllm' (point to the vLLM server, e.g. http://host:8000/v1)")
        return self

OptModelConfig = ModelConfig|Literal["disabled"]


class Settings(BaseSettings):
    # Site profile
    site_profile: str = Field(
        default="localdev",
        description="Site profile (e.g., localdev, staging, production)"
    )

    # Application names
    app_name: str = Field(
        default="heraldapp",
        description="Name of the application"
    )

    base_path: A[str,
        Field(description="Base URL of the application"),
        AfterValidator(lambda p: p.removesuffix("/")),
    ] = ""

    large_model: ModelConfig = ModelConfig(
        type = "openai",
        name = "gpt-4o",
        url = "https://<your-resource>.openai.azure.com/openai/deployments/gpt-4o?api-version=2025-01-01-preview",
    )
    """ Model to use for the main chat model """
    # "disabled", not a type='local' ModelConfig: 'local' (in-process
    # HuggingFace) was removed from make_openai_client — any real ModelConfig
    # with that type raises on first use. "disabled" is the actually-supported
    # unconfigured state (see _get_dbs()/get_sql_model_client()'s graceful
    # None-client handling) and is what an empty .env should mean by default.
    small_model: OptModelConfig = "disabled"
    """ Model to use in the lower levels in the hierarchy """
    sql_model: A[OptModelConfig, Field(description = "Model to use for the sql generation")] = "disabled"
    """ Model to use for the sql chain """
    db_module: str = "src.site.ornl.frontier.db"
    """
    Path to a python module, e.g. "src.site.ornl.frontier.db", which contains two functions
    `create_sql_database()` and `create_sql_prompt_template()`
    """

    @model_validator(mode='before')
    def is_valid(data):
        return data

    # Nvidia GPU Visibility
    cuda_visible_devices: str = Field(
        default="0",
        description="Comma separated list of visible Nvidia GPU instances on the system"
    )

    llm_request_timeout_seconds: float = Field(
        default=120.0,
        description="Default per-request timeout for every LLM API client (orchestrator, "
                    "SQL, RAG, job-pred) -- none of the client constructors set one "
                    "otherwise, so a slow/unresponsive endpoint hangs a chat request "
                    "indefinitely with no error, just an endless spinner. Override per-model "
                    "via that model's EXTRA_ARGS={\"timeout\": ...} in .env (e.g. a slower "
                    "self-hosted vLLM or a high-reasoning-effort model that genuinely needs "
                    "longer) -- that takes precedence over this global default.",
    )

    # Local scratch volume
    scratch_base: str = Field(
        default=str(PROJECT_ROOT / ".scratch"),
        description="Local scratch space - accepts only POSIX paths"

    )

    shared_base: str = Field(
        default=str(PROJECT_ROOT / ".shared"),
        description="Local project space - accepts only POSIX paths"
    )

    # Object store access
    data_base: str = Field(
        default=str(PROJECT_ROOT / ".data" / "shared"),
        description="Primary prefix of the data files either POSIX or an s3a:// prefix"
    )
    data_priv_base: str = Field(
        default=str(PROJECT_ROOT / ".data" / "private"),
        description="Primary prefix of sensitive data files POSIX or an s3a:// prefix"
    )

    @computed_field
    @property
    def is_data_base_remote(self) -> bool:
        """Is data base remote?"""
        return self.data_base.startswith("s3a:/")

    @computed_field
    @property
    def is_data_priv_base_remote(self) -> bool:
        """Is data base remote?"""
        return self.data_base.startswith("s3a:/")

    # aws S3 interface
    aws_endpoint_url: str = Field(
        default="",
        description="Custom endpoint URL for AWS S3 (leave empty for default)"
    )
    aws_access_key_id: str = Field(
        default="",
        description="AWS access key ID for S3 access"
    )
    aws_secret_access_key: str = Field(
        default="",
        description="AWS secret access key for S3 access"
    )

    @computed_field
    @property
    def has_aws_object_store(self) -> bool:
        """Return whether we have an AWS S3 based object store available"""
        return self.aws_endpoint_url != "" and self.aws_access_key_id != "" and self.aws_secret_access_key != ""

    # Kubernetes settings
    kubeconfig: str = Field(
        default="~/.kube/config",
        description="Path to the Kubernetes config file"
    )
    kubernetes_service_host: str = Field(
        default="",
        description="Kubernetes API server host"
    )
    kubernetes_service_port: str = Field(
        default="",
        description="Kubernetes API server port"
    )
    kubernetes_namespace: str = Field(
        default="default",
        description="Default Kubernetes namespace"
    )
    kubernetes_app_namespace: str = Field(
        default="default",
        description="Kubernetes namespace for applications"
    )
    kubernetes_batch_namespace: str = Field(
        default="default",
        description="Kubernetes namespace for batch workflows"
    )

    @computed_field
    @property
    def has_kubernetes(self) -> bool:
        """Returns whether we have a kubernetes cluster in our environment"""
        return self.kubernetes_service_host != ""

    # Metadata server
    metadata_service: str = Field(
        default=str(Path(__file__).resolve().parent.parent),
        description="Metadata service to use (local, remote)"
    )

    @computed_field
    @property
    def is_metadata_service_remote(self) -> bool:
        """Is data base remote?"""
        return self.metadata_service.startswith("s3a:/")

    vllm_base_url: str = Field(
        default="http://localhost:8000/v1",
        description="OpenAI-compatible base URL for local vLLM-served models (used by PydanticAI agent)."
    )

    enabled_tools: list[str] = Field(
        default=["sql", "rag", "jobpred", "syslog"],
        description=(
            "Tools/sub-agents to activate. Remove a name to disable that tool for all sessions. "
            "Valid values: 'sql', 'rag', 'jobpred', 'syslog'. Add new tool names here as they "
            "are registered in src/mcp/registry.py."
        ),
    )

    # ── RAG user-document ingestion (src/rag/ingest_user.py) ──────────────
    rag_upload_dir: str = Field(
        default=str(PROJECT_ROOT / ".data" / "rag_uploads"),
        description="Directory where user-uploaded RAG documents/images are stored. "
                    "Uploaded images are kept here so they remain reachable for display.",
    )
    rag_image_base_dir: str = Field(
        default="",
        description="Base directory to resolve relative image paths stored in the RAG image "
                    "collection (e.g. 'images/foo.jpg'). Leave empty to skip non-upload images. "
                    "User-uploaded images store absolute paths and don't need this.",
    )
    rag_image_max_results: int = Field(
        default=1,
        description="Max relevant images to surface in a chat documentation answer. 0 disables "
                    "in-chat image display.",
    )
    rag_image_max_distance: float = Field(
        default=0.0,
        description="Optional CLIP distance cutoff for in-chat images (lower = more similar). "
                    "0 disables the cutoff (always show up to rag_image_max_results). Tune to "
                    "suppress loosely-related images.",
    )
    rag_upload_max_bytes: int = Field(
        default=50 * 1024 * 1024,
        description="Maximum size (bytes) for a single uploaded RAG document. Default 50 MiB.",
    )
    rag_upload_allowed_extensions: list[str] = Field(
        default=[".txt", ".md", ".markdown", ".rst", ".html", ".htm",
                 ".pdf", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".webp"],
        description="Lower-cased file extensions accepted by the RAG ingest endpoint.",
    )
    rag_watch_dir: str = Field(
        default="",
        description="If set, a background watcher auto-ingests supported files dropped into "
                    "this directory (and re-ingests them when they change). Empty = disabled.",
    )
    rag_watch_interval_seconds: int = Field(
        default=30,
        description="How often (seconds) the RAG folder watcher rescans rag_watch_dir. Min 5.",
    )

    syslog_store_backend: Literal["duckdb", "clickhouse"] = Field(
        default="duckdb",
        description=(
            "Backend for the persistent syslog events store. "
            "'duckdb' uses syslog_db_path (good for dev / ~10B rows). "
            "'clickhouse' uses the clickhouse_* settings (good for 500B+)."
        ),
    )
    syslog_noise_sampling_enabled: bool = Field(
        default=False,
        description=(
            "If True, apply classifier.py's DEFAULT_NOISE_SAMPLE_RATE — "
            "stochastic per-event dropping of known high-volume noise types "
            "(NET_CXI_RAW_DATA, FS_DISK_FULL, INFO_NOISE, SYS_X11_NOISE) "
            "before they're written to the store. Default False: keep every "
            "raw message, matching the SC26 paper's own frequency-balancing "
            "approach (it never discards raw data, only caps counts within "
            "bounded analysis windows). The true per-type COUNT is tracked "
            "via event_true_counts regardless of this flag; this only "
            "controls whether raw message bodies for noise types are also "
            "kept. Enable only if storage/bandwidth at real production "
            "volume (NET_CXI_RAW_DATA alone was ~65% of 18.4B real Frontier "
            "events) requires shedding raw noise-type messages."
        ),
    )
    syslog_db_path: str = Field(
        default=str(PROJECT_ROOT / ".data" / "syslog_events.duckdb"),
        description="DuckDB file backing the persistent syslog events store (when syslog_store_backend='duckdb').",
    )
    clickhouse_host: str = Field(default="localhost", description="ClickHouse host (when syslog_store_backend='clickhouse').")
    clickhouse_port: int = Field(default=8123, description="ClickHouse HTTP port.")
    clickhouse_database: str = Field(default="herald_syslog", description="ClickHouse database name.")
    clickhouse_user: str = Field(default="default", description="ClickHouse user.")
    clickhouse_password: str = Field(default="", description="ClickHouse password.")
    clickhouse_secure: bool = Field(default=False, description="Use HTTPS for ClickHouse connection.")
    clickhouse_async_insert: bool = Field(
        default=True,
        description="P5c: server-side INSERT batching via async_insert. Fire-and-forget; fine for live-stream ingest.",
    )
    clickhouse_event_ttl_days: int = Field(
        default=0,
        description="P5c: drop events older than N days via ALTER TABLE MODIFY TTL. 0 = no TTL (default). Rollups are kept regardless.",
    )
    clickhouse_rollup_intervals: list[str] = Field(
        default=["5 SECOND", "1 MINUTE", "10 MINUTE"],
        description=(
            "Each entry creates "
            "events_rollup_<n><unit> + its MV (CREATE IF NOT EXISTS — safe to "
            "re-run). Add an entry to add a new rollup. Removing an entry is "
            "NOT destructive — use clickhouse_rollup_drop to actually delete "
            "tables. Format: '<n> SECOND|MINUTE|HOUR|DAY'."
        ),
    )
    syslog_extensions_path: str = Field(
        default=str(PROJECT_ROOT / ".data" / "syslog_patterns_extension.jsonl"),
        description=(
            "patterns.py at import time; takes effect on next API restart."
        ),
    )
    syslog_proposals_rejected_path: str = Field(
        default=str(PROJECT_ROOT / ".data" / "syslog_proposals_rejected.jsonl"),
        description=(
            
            "Keyed by (event_type, regex); re-proposed duplicates are suppressed."
        ),
    )
    syslog_proposal_min_cluster: int = Field(
        default=5,
        description="minimum residual cluster size to surface to the LLM proposer.",
    )
    syslog_proposal_min_residuals: int = Field(
        default=100,
        description="minimum total residuals required before running the proposer.",
    )

    syslog_proposer_auto_apply: bool = Field(
        default=False,
        description=(
            "P6+: when True, high-confidence proposals (see "
            "syslog_proposer_auto_apply_min_frequency, canonical subsystem prefix, "
            "no label collision, regex not over-broad) are appended directly to "
            "the extension JSONL with auto_approved_at, skipping the human queue. "
            "Default False — every proposal routes to the queue."
        ),
    )
    syslog_proposer_auto_apply_min_frequency: int = Field(
        default=50,
        description=(
            "P6+: minimum cluster frequency to consider a proposal for auto-apply. "
            "Higher = more conservative. Only effective when "
            "syslog_proposer_auto_apply is True."
        ),
    )

    syslog_alert_slack_webhook_url: str = Field(
        default="",
        description=(
            "residual-rate alerts. Empty (default) disables all alerts."
        ),
    )
    syslog_alert_queue_threshold: int = Field(
        default=20,
        description="fire an alert when proposal-queue pending count >= this.",
    )
    syslog_alert_residual_rate_per_min_threshold: int = Field(
        default=1000,
        description=(
            "fire an alert when residual events/min in the recent window "
            "exceed this value. 0 disables the rule."
        ),
    )
    syslog_alert_residual_rate_window_minutes: int = Field(
        default=5,
        description="lookback window for the residual-rate rule.",
    )
    syslog_alert_cooldown_minutes: int = Field(
        default=60,
        description=(
            "minimum minutes between two alert fires for the same rule, "
            "so a sustained condition doesn't page the on-call every cron tick."
        ),
    )
    syslog_alert_state_path: str = Field(
        default=str(PROJECT_ROOT / ".data" / "syslog_alert_state.json"),
        description="where the alert script records last-fired-at per rule for cooldown.",
    )

    clickhouse_rollup_drop: list[str] = Field(
        default=[],
        description=(
            "Drops run before "
            "creates, so changing window sizes is safe in one config edit."
        ),
    )

    # ── Kafka live-tail ingestion connector ──────────────────────────
    kafka_bootstrap_servers: str = Field(
        default="",
        description="P8: comma-separated host:port list for the Kafka cluster. Empty = connector disabled.",
    )
    kafka_topic: str = Field(default="", description="P8: topic carrying syslog messages.")
    kafka_consumer_group: str = Field(
        default="herald-syslog-ingest",
        description="P8: consumer group id. Determines how partitions are shared across worker processes.",
    )
    kafka_batch_size: int = Field(
        default=500,
        description="P8: flush to the store after this many events, whichever of size/time comes first.",
    )
    kafka_batch_timeout_seconds: float = Field(
        default=2.0,
        description="P8: flush to the store after this many seconds since the last flush, even if batch_size isn't reached — needed for bursty live traffic (unlike paced file replay).",
    )
    kafka_consumer_auto_offset_reset: Literal["earliest", "latest"] = Field(
        default="latest",
        description="P8: where a new consumer group starts. 'latest' avoids replaying the topic's full retention on first connect unless intentional.",
    )

    # ── Elasticsearch backfill connector ─────────────────────────────
    elasticsearch_hosts: str = Field(
        default="",
        description="P8: comma-separated ES host(s), e.g. 'https://es.example.org:9200'. Empty = connector disabled.",
    )
    elasticsearch_index: str = Field(default="", description="P8: index (or index pattern) holding historical syslog documents.")
    elasticsearch_backfill_batch_size: int = Field(
        default=1000,
        description="P8: page size for PIT + search_after pagination.",
    )
    elasticsearch_field_map: dict[str, str] = Field(
        default={"message": "message", "timestamp": "@timestamp", "node": "host.name", "pid": "process.pid", "identifier": "process.name"},
        description=(
            "P8: logical field -> real ES field name, since the org's index schema isn't a fixed "
            "HERALD convention. Defaults follow common ECS (Elastic Common Schema) naming; override "
            "per-field if the real index differs."
        ),
    )
    elasticsearch_backfill_checkpoint_path: str = Field(
        default=str(PROJECT_ROOT / ".data" / "elasticsearch_backfill_checkpoint.json"),
        description="P8: where the backfill's PIT/search_after position is saved, so a restart resumes instead of re-scanning from the start.",
    )

    query_output_limit: int = Field(
        default = 1000,
        description = "Limit to how many results will be kept from a query, as a safety measure if the model tries to dump the whole DB on us.",
    )

    query_output_limit_table: int = Field(
        default = 100,
        description = "Limit to how many results will be displayed in query result tables",
    )

    query_output_limit_chat_model: int = Field(
        default = 200,
        description = "Limit to how many results will passed to the top-level chat model (to avoid eating up too many tokens)",
    )

    # Reading from the .env file and the environment
    # Extra arguments are allowed for now (FIXME: Narrow it down)
    model_config = SettingsConfigDict(
        env_file = ".env",
        extra = "ignore",
        env_nested_delimiter = '__',
    )


@lru_cache
def _get_settings():
    """Return a fully instantiated settings object"""
    return Settings()


def get_settings() -> Settings:
    """Return a fully instantiated settings object

    This function also exports important environment variables to the
    environment, enabling overrides of the environment via the .env file 
    """
    import os
    settings = _get_settings()
    
    
    # Export CUDA_VISIBAL_DEVICES settings
    os.environ["CUDA_VISIBLE_DEVICES"] = settings.cuda_visible_devices

    return settings