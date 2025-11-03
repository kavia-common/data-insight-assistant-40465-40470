"""
Utility to generate and write the OpenAPI schema to interfaces/openapi.json.

Usage:
  python -m src.api.generate_openapi
"""

import json
from pathlib import Path

from fastapi.openapi.utils import get_openapi  # type: ignore

from .main import app
from ..core.logger import get_logger

logger = get_logger(__name__)


# PUBLIC_INTERFACE
def generate_openapi_file(output_path: str = "interfaces/openapi.json") -> str:
    """Generate the OpenAPI schema and write it to the given path.

    Args:
        output_path: Relative path from fastapi_backend root to write JSON.

    Returns:
        The absolute path to the written file.
    """
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description or "",
        routes=app.routes,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    abs_path = str(out.resolve())
    logger.info("OpenAPI schema written.", extra={"path": abs_path})
    return abs_path


if __name__ == "__main__":
    generate_openapi_file()
