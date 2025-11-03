"""
Natural Language Query (NLQ) service skeleton.

TODO:
- Implement rule-based mapping from user NL to MongoDB queries
- Add optional AI augmentation paths when ENABLE_NLQ_AI is true
"""

from typing import Any, Dict

# PUBLIC_INTERFACE
def parse_nlq_to_query(nlq: str) -> Dict[str, Any]:
    """Convert a natural language query string to a MongoDB filter (placeholder)."""
    # Placeholder: return a no-op filter. To be implemented later.
    return {}
