"""
Vector Embedding Manager.

Handles the logic for Adaptive JIT Vector Embeddings (Phase 5.7).
Predicts whether global embeddings will cause an OOM crash based
on codebase size, and recommends 'global' or 'lazy' embedding strategies.
"""

from pathlib import Path

from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

# Threshold for switching to lazy embeddings (approx. 300 files)
# At ~300 files, the ONNX embedder starts pushing past 8-10GB of RAM.
LAZY_EMBEDDING_THRESHOLD = 300


def predict_embedding_strategy(repo_path: Path, language: str = "python") -> str:
    """
    Predict whether to use 'global' or 'lazy' (JIT) embeddings.

    Args:
        repo_path: Path to the codebase root.
        language: Programming language to check.

    Returns:
        "global" if the codebase is small enough to embed all at once safely.
        "lazy" if the codebase is too large and will likely OOM the machine.
    """
    pattern = "*.py" if language == "python" else f"*.{language}"
    
    try:
        # We only need to count, so we use a generator and sum
        file_count = sum(1 for _ in repo_path.rglob(pattern))
        
        logger.info(
            "predict_embedding_strategy", 
            file_count=file_count, 
            threshold=LAZY_EMBEDDING_THRESHOLD
        )
        
        if file_count >= LAZY_EMBEDDING_THRESHOLD:
            return "lazy"
        return "global"
        
    except Exception as e:
        logger.error(f"Failed to scan directory for strategy prediction: {e}")
        # Default to lazy if we can't tell, to be safe.
        return "lazy"
