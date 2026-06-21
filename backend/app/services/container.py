"""Composition root.

Builds the concrete object graph from :class:`Settings` and exposes it as a
single :class:`Container`. This is the *only* place where interfaces are bound to
implementations, so swapping a backend (provider, vector store, repository,
Shopify client) is a config decision made here — nothing downstream changes.

Offline-by-default: in demo mode / tests it wires the deterministic Fake LLM,
the hashing embedder, the in-memory vector store, the overlap reranker, the
in-memory repository, and the Fake Shopify client with a synthetic catalog — so
the full pipeline (including catalog sync) runs with no external services.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from app.billing.budget import SessionBudget
from app.compliance.service import ComplianceService
from app.config import Settings
from app.core.intent_classifier import (
    HeuristicIntentClassifier,
    IntentClassifier,
    LLMIntentClassifier,
)
from app.core.orchestrator import Orchestrator
from app.handoff.base import HandoffProvider
from app.handoff.log_provider import LoggingHandoffProvider
from app.handoff.webhook_provider import WebhookHandoffProvider
from app.llm.base import LLMProvider
from app.llm.factory import build_provider, real_llm_enabled, uses_chain
from app.observability.logging import get_logger
from app.rag.embeddings import Embedder, HashingEmbedder, ProviderEmbedder
from app.rag.image_embeddings import CLIPImageEmbedder, FakeImageEmbedder, ImageEmbedder
from app.rag.indexer import Indexer
from app.rag.models import Document
from app.rag.reranker import OverlapReranker, Reranker
from app.rag.retriever import Retriever
from app.rag.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorStore
from app.rag.visual_search import VisualIndexer, VisualSearchService, offline_descriptor_source
from app.recommendations.service import RecommendationService
from app.repositories.base import ConversationRepository
from app.repositories.content import ContentRepository, InMemoryContentRepository
from app.repositories.memory import InMemoryConversationRepository
from app.services.analytics import AnalyticsService
from app.services.content_service import ContentService
from app.services.gaps import ContentGapService
from app.services.jobs import InlineJobQueue, JobQueue
from app.services.seed import load_seed_documents
from app.services.widget_config import WidgetConfigStore
from app.shopify.catalog_sync import CatalogSyncService
from app.shopify.client import ShopifyClient
from app.shopify.fake import FakeShopifyClient
from app.shopify.freshness import FreshnessPosture, resolve_posture
from app.shopify.orders import OrderService

_log = get_logger("container")

_QDRANT_COLLECTION = "kb_text"
_QDRANT_IMAGE_COLLECTION = "kb_image"
_DEMO_CATALOG_SIZE = 24


@dataclass(slots=True)
class Container:
    """The wired application object graph."""

    settings: Settings
    provider: LLMProvider
    embedder: Embedder
    store: VectorStore
    retriever: Retriever
    orchestrator: Orchestrator
    repository: ConversationRepository
    handoff: HandoffProvider
    indexer: Indexer
    shopify_client: ShopifyClient
    catalog: CatalogSyncService
    order_service: OrderService
    recommender: RecommendationService
    content: ContentService
    gaps: ContentGapService
    analytics: AnalyticsService
    compliance: ComplianceService
    widget_config: WidgetConfigStore
    budget: SessionBudget
    visual_search: VisualSearchService | None
    visual_indexer: VisualIndexer | None
    job_queue: JobQueue
    freshness: FreshnessPosture

    async def bootstrap(self) -> int:
        """Index seed KB content (+ a synthetic catalog in demo); return chunks."""
        docs = _read_seed_documents(self.settings.seed_dir)
        count = await self.indexer.index(docs) if docs else 0
        product_docs: list[Document] = []
        if self.settings.demo_mode and isinstance(self.shopify_client, FakeShopifyClient):
            from app.shopify.bulk import group_jsonl_by_parent
            from app.shopify.mapping import documents_from_products

            product_docs = documents_from_products(
                group_jsonl_by_parent(self.shopify_client.jsonl_lines)
            )
            count += await self.catalog.full_import(lines=self.shopify_client.jsonl_lines)
        if self.visual_indexer is not None and product_docs:
            await self.visual_indexer.index(product_docs)
        _log.info("bootstrap_complete", seed_documents=len(docs), total_chunks=count)
        return count


def _read_seed_documents(seed_dir: str) -> list[Document]:
    """Resolve the seed directory and load its documents (synchronous I/O)."""
    seed_path = Path(seed_dir)
    if not seed_path.is_absolute():
        seed_path = Path(__file__).resolve().parents[2] / seed_dir
    if not seed_path.exists():
        _log.warning("seed_dir_missing", path=str(seed_path))
        return []
    return load_seed_documents(seed_path)


def _provider_can_embed(settings: Settings) -> bool:
    """Whether the configured chat provider(s) expose an embeddings API.

    Groq is chat-only (no embeddings endpoint), so a Groq-only deployment must
    fall back to the offline hashing embedder for retrieval.
    """
    embed_capable = {"openai", "gemini", "google"}
    if settings.llm_chain:
        return any(c.provider in embed_capable for c in settings.llm_chain)
    return settings.llm_default_provider.lower() in embed_capable


def _build_embedder(settings: Settings, provider: LLMProvider) -> Embedder:
    if settings.demo_mode:
        return HashingEmbedder(dimension=settings.embedding_dimension)
    backend = settings.embedding_backend
    use_provider = backend == "provider" or (backend == "auto" and _provider_can_embed(settings))
    if use_provider:
        return ProviderEmbedder(provider, dimension=settings.embedding_dimension)
    # "hashing", or "auto" with a chat-only provider (e.g. Groq).
    _log.info("embedder_offline_fallback", backend=backend, provider=settings.llm_default_provider)
    return HashingEmbedder(dimension=settings.embedding_dimension)


def _build_store(settings: Settings) -> VectorStore:
    if settings.demo_mode or not settings.qdrant_url:
        return InMemoryVectorStore()
    return QdrantVectorStore(
        settings.qdrant_url,
        collection=_QDRANT_COLLECTION,
        dimension=settings.embedding_dimension,
        api_key=settings.qdrant_api_key,
    )


def _build_reranker(settings: Settings) -> Reranker:
    return OverlapReranker()


def _build_repository(settings: Settings) -> ConversationRepository:
    if settings.demo_mode or not settings.database_url:
        return InMemoryConversationRepository()
    from app.repositories.sql import SqlConversationRepository  # lazy import

    return SqlConversationRepository(settings.database_url)


def _build_shopify_client(settings: Settings) -> ShopifyClient:
    """Fake client offline; the throttled Admin GraphQL client when credentials exist.

    Credential precedence: Dev Dashboard client-credentials (preferred, auto-
    refreshing 24h token) → legacy static Admin API token (fallback) → fake.
    """
    has_oauth = bool(settings.shopify_client_id and settings.shopify_client_secret)
    has_static = bool(settings.shopify_admin_api_token)
    if settings.demo_mode or not settings.shopify_store_domain or not (
        has_oauth or has_static
    ):
        return FakeShopifyClient(n_products=_DEMO_CATALOG_SIZE)

    from app.shopify.client import AdminGraphQLClient  # lazy import

    if has_oauth:
        from app.shopify.auth import ClientCredentialsTokenProvider  # lazy import

        token_provider = ClientCredentialsTokenProvider(
            settings.shopify_store_domain,
            settings.shopify_client_id,  # type: ignore[arg-type]
            settings.shopify_client_secret,  # type: ignore[arg-type]
        )
        return AdminGraphQLClient(
            settings.shopify_store_domain,
            token_provider=token_provider,
            api_version=settings.shopify_api_version,
            max_retries=settings.webhook_retry_max,
        )

    return AdminGraphQLClient(
        settings.shopify_store_domain,
        settings.shopify_admin_api_token,
        api_version=settings.shopify_api_version,
        max_retries=settings.webhook_retry_max,
    )


def _build_image_embedder(settings: Settings) -> ImageEmbedder:
    if settings.demo_mode:
        return FakeImageEmbedder(dimension=settings.image_embedding_dimension)
    return CLIPImageEmbedder(settings.clip_model_name, dimension=settings.image_embedding_dimension)


def _build_image_store(settings: Settings) -> VectorStore:
    if settings.demo_mode or not settings.qdrant_url:
        return InMemoryVectorStore()
    return QdrantVectorStore(
        settings.qdrant_url,
        collection=_QDRANT_IMAGE_COLLECTION,
        dimension=settings.image_embedding_dimension,
        api_key=settings.qdrant_api_key,
    )


def _build_handoff(settings: Settings) -> HandoffProvider:
    """Select the handoff channel from config; logging is the safe default."""
    if settings.handoff_provider == "webhook" and settings.handoff_webhook_url:
        return WebhookHandoffProvider(
            settings.handoff_webhook_url, token=settings.handoff_webhook_token
        )
    return LoggingHandoffProvider()


def build_container(settings: Settings) -> Container:
    """Construct the full object graph for ``settings``."""
    provider = build_provider(settings)
    embedder = _build_embedder(settings, provider)
    store = _build_store(settings)
    reranker = _build_reranker(settings)
    retriever = Retriever(
        embedder,
        store,
        reranker,
        candidate_k=settings.rag_candidate_k,
        final_k=settings.rag_final_k,
    )
    handoff = _build_handoff(settings)
    repository = _build_repository(settings)
    indexer = Indexer(embedder, store)

    shopify_client = _build_shopify_client(settings)
    catalog = CatalogSyncService(
        shopify_client, indexer, embed_batch_size=settings.catalog_embed_batch_size
    )
    order_service = OrderService(
        shopify_client,
        returns_enabled=settings.returns_enabled,
        exchanges_enabled=settings.exchanges_enabled,
    )
    recommender = RecommendationService(embedder, store, order_service)
    content_repo: ContentRepository = InMemoryContentRepository()
    content = ContentService(content_repo, indexer)
    gaps = ContentGapService(repository)
    analytics = AnalyticsService(repository)
    compliance = ComplianceService(repository, retention_days=settings.data_retention_days)
    widget_config = WidgetConfigStore.from_settings(settings)
    budget = SessionBudget(
        budget=settings.per_session_token_budget,
        anomaly_threshold=settings.cost_anomaly_session_threshold,
    )

    visual_search: VisualSearchService | None = None
    visual_indexer: VisualIndexer | None = None
    if settings.visual_search_enabled:
        image_embedder = _build_image_embedder(settings)
        image_store = _build_image_store(settings)
        image_source = offline_descriptor_source  # real path injects a downloader
        visual_indexer = VisualIndexer(image_embedder, image_store, image_source)
        visual_search = VisualSearchService(image_embedder, image_store, order_service)

    real_llm = real_llm_enabled(settings)
    soft_model = None if (not real_llm or uses_chain(settings)) else settings.llm_default_model
    intent_classifier: IntentClassifier = (
        LLMIntentClassifier(provider, model=soft_model) if real_llm else HeuristicIntentClassifier()
    )
    orchestrator = Orchestrator(
        provider,
        retriever,
        handoff,
        order_service=order_service,
        recommender=recommender,
        intent_classifier=intent_classifier,
        store_name=settings.store_name,
        min_confidence=settings.rag_min_confidence,
        require_verification=settings.require_identity_verification,
        allow_general_fallback=settings.assist_fallback_enabled and real_llm,
        model=(None if (not real_llm or uses_chain(settings)) else settings.llm_default_model),
    )
    job_queue = InlineJobQueue(
        {
            "reindex_product": _reindex_handler(catalog),
            "delete_product": _delete_handler(catalog),
        }
    )
    freshness = resolve_posture(settings)

    return Container(
        settings=settings,
        provider=provider,
        embedder=embedder,
        store=store,
        retriever=retriever,
        orchestrator=orchestrator,
        repository=repository,
        handoff=handoff,
        indexer=indexer,
        shopify_client=shopify_client,
        catalog=catalog,
        order_service=order_service,
        recommender=recommender,
        content=content,
        gaps=gaps,
        analytics=analytics,
        compliance=compliance,
        widget_config=widget_config,
        budget=budget,
        visual_search=visual_search,
        visual_indexer=visual_indexer,
        job_queue=job_queue,
        freshness=freshness,
    )


def _reindex_handler(
    catalog: CatalogSyncService,
) -> Callable[..., Awaitable[None]]:
    async def _run(product_gid: str) -> None:
        await catalog.reindex_product(product_gid)

    return _run


def _delete_handler(
    catalog: CatalogSyncService,
) -> Callable[..., Awaitable[None]]:
    async def _run(product_gid: str) -> None:
        await catalog.delete_product(product_gid)

    return _run
