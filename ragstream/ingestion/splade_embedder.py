# -*- coding: utf-8 -*-
"""
splade_embedder.py

Purpose:
    SPLADE-side counterpart of embedder.py for RAGstream ingestion.

Role in architecture:
    - Dense side:
        Embedder.embed(texts) -> List[List[float]]
    - Sparse SPLADE side:
        SpladeEmbedder.embed(texts) -> List[Dict[str, float]]

Design goals:
    - Keep the public ingestion-facing API parallel to Embedder:
        embed(texts) -> one sparse representation per text
    - Add query-specific helpers for the later retrieval phase:
        embed_queries(...)
        embed_query(...)
    - Persist nothing here; this module is encoder-only.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

try:
    import torch
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "splade_embedder.py requires PyTorch. Please install torch first."
    ) from exc

try:
    from sentence_transformers import SparseEncoder
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "splade_embedder.py requires sentence-transformers with SparseEncoder support."
    ) from exc


SparseVector = Dict[str, float]


class SpladeEmbedder:
    """
    High-level SPLADE sparse encoder.

    Public API is intentionally parallel to dense Embedder where possible:
        - embed(texts)         : document-side sparse encoding for ingestion
        - embed_queries(texts) : query-side sparse encoding for retrieval
        - embed_query(text)    : single-query convenience wrapper

    Internal sparse representation:
        Dict[str, float]
            key   = vocabulary dimension id as string
            value = SPLADE weight for that active dimension
    """

    def __init__(
        self,
        model: str = "naver/splade-cocondenser-ensembledistil",
        *,
        device: str = "cpu",
        backend: str = "torch",
        batch_size: int = 16,
        max_active_dims: int | None = 256,
        show_progress_bar: bool = False,
    ) -> None:
        """
        Args:
            model:
                SPLADE model name or local path.
            device:
                Usually "cpu" on your laptop for now.
            backend:
                SparseEncoder backend, e.g. "torch", "onnx", "openvino".
            batch_size:
                Default batch size for encoding.
            max_active_dims:
                Optional cap on active dimensions to keep sparse output bounded.
            show_progress_bar:
                Whether Sentence Transformers should show progress bars.
        """
        self.model = model
        self.device = device
        self.backend = backend
        self.batch_size = int(batch_size)
        self.max_active_dims = max_active_dims
        self.show_progress_bar = bool(show_progress_bar)

        self.encoder = SparseEncoder(
            model,
            device=device,
            backend=backend,
            max_active_dims=max_active_dims,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, texts: List[str]) -> List[SparseVector]:
        """
        Document-side sparse encoding for ingestion.

        This is the ingestion-parallel counterpart of dense Embedder.embed(...).

        Args:
            texts:
                List of chunk texts.

        Returns:
            List[Dict[str, float]]:
                One sparse representation per input text.
        """
        return self._encode_documents(texts)

    def embed_queries(self, texts: List[str]) -> List[SparseVector]:
        """
        Query-side sparse encoding for retrieval.

        Kept here already so retriever_splade.py can later use the same class.
        """
        if not texts:
            return []

        raw = self.encoder.encode_query(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=self.show_progress_bar,
            convert_to_tensor=False,
            convert_to_sparse_tensor=True,
            save_to_cpu=True,
            max_active_dims=self.max_active_dims,
        )
        return [self._tensor_to_sparse_dict(t) for t in self._ensure_list(raw)]

    def embed_query(self, text: str) -> SparseVector:
        """
        Convenience wrapper for one retrieval query.
        """
        text = (text or "").strip()
        if not text:
            return {}
        return self.embed_queries([text])[0]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _encode_documents(self, texts: Sequence[str]) -> List[SparseVector]:
        if not texts:
            return []

        raw = self.encoder.encode_document(
            list(texts),
            batch_size=self.batch_size,
            show_progress_bar=self.show_progress_bar,
            convert_to_tensor=False,
            convert_to_sparse_tensor=True,
            save_to_cpu=True,
            max_active_dims=self.max_active_dims,
        )
        return [self._tensor_to_sparse_dict(t) for t in self._ensure_list(raw)]

    @staticmethod
    def _ensure_list(raw: object) -> List[torch.Tensor]:
        """
        Sentence Transformers may return a single tensor or a list of tensors,
        depending on input shape and conversion settings.
        """
        if isinstance(raw, list):
            return raw
        if isinstance(raw, torch.Tensor):
            return [raw]
        raise TypeError(f"Unsupported sparse encoder output type: {type(raw)!r}")

    @staticmethod
    def _tensor_to_sparse_dict(tensor: torch.Tensor) -> SparseVector:
        """
        Convert one sparse tensor into Dict[str, float].

        Expected common case:
            sparse COO tensor, shape [vocab_size]

        Fallback:
            dense tensor -> convert non-zero entries only
        """
        if tensor.is_sparse:
            t = tensor.coalesce()
            indices = t.indices()
            values = t.values()

            if indices.numel() == 0:
                return {}

            # 1D sparse vector: indices shape [1, nnz]
            # Defensive fallback: use last row if shape differs.
            if indices.dim() == 2:
                dim_ids = indices[-1].tolist()
            else:
                dim_ids = indices.tolist()

            return {
                str(int(dim_id)): float(value)
                for dim_id, value in zip(dim_ids, values.tolist())
                if float(value) != 0.0
            }

        # Dense fallback
        nonzero = torch.nonzero(tensor, as_tuple=False).flatten().tolist()
        if not nonzero:
            return {}

        return {
            str(int(idx)): float(tensor[idx].item())
            for idx in nonzero
            if float(tensor[idx].item()) != 0.0
        }