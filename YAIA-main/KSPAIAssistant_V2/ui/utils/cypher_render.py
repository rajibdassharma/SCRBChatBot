import json
import re
from typing import Any, Dict


def render_cypher_for_neovis(cypher: str, params: Dict[str, Any]) -> str:
    """
    Convert parameterized Cypher into a plain Cypher string
    safe for client-side execution (Neovis / Browser).

    Example:
      MATCH ... WHERE r.crime_no = $crime_no
      params = {"crime_no": "1098"}

    Result:
      MATCH ... WHERE r.crime_no = "1098"
    """

    if not cypher or not params:
        return cypher

    rendered = cypher

    for key, value in params.items():
        placeholder = f"${key}"

        # Convert value to valid Cypher literal
        if value is None:
            replacement = "null"

        elif isinstance(value, bool):
            replacement = "true" if value else "false"

        elif isinstance(value, (int, float)):
            replacement = str(value)

        elif isinstance(value, (list, tuple)):
            # List → Cypher list
            replacement = json.dumps(value)

        else:
            # String → escape quotes safely
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            replacement = f'"{escaped}"'

        # Replace ONLY full parameter tokens (avoid partial matches)
        rendered = re.sub(
            rf"\{placeholder}\b",
            replacement,
            rendered
        )

    return rendered
