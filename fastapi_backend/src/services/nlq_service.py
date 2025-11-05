"""
Natural Language Query (NLQ) service with deterministic parsing.

Provides a simple, rule-based mapping from natural language phrases to MongoDB-style
filters and query options. This is intentionally deterministic for predictable behavior
and testability without AI dependencies.

Note:
- This module has no runtime dependency on MongoDB client packages and must remain import-safe.

Supported patterns (case-insensitive, order-insensitive):
- Date ranges:
  * "last N days|weeks|months" -> created_at in ISODate range
  * "today", "yesterday"       -> created_at between day boundaries
- Equality:
  * "field equals VALUE" or "field is VALUE"
- Comparisons:
  * "field > N", "field >= N", "field < N", "field <= N"
- Category/contains:
  * "category: value", "category in a,b,c", "<field> contains <text>"
- Sorting:
  * "sort by <field>", "sort by <field> desc|asc"
- Limit/offset:
  * "top N", "limit N", "offset N"
- Field selection:
  * "fields a,b,c", "select a,b,c"

All date comparisons assume a document field named "created_at" holding ISO 8601 strings
or BSON Date; we emit filter on "created_at". The caller can adapt or map fields externally.

Note:
- Parsing is best-effort; unrecognized segments are ignored.
- Numeric detection attempts float then int; non-numeric values kept as strings.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_number(val: str) -> Union[int, float, str]:
    try:
        if "." in val:
            return float(val)
        return int(val)
    except Exception:
        return val


def _parse_list_csv(text: str) -> List[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def _ensure_projection(fields: Optional[List[str]]) -> Optional[Dict[str, int]]:
    if not fields:
        return None
    proj = {f: 1 for f in fields}
    if "_id" not in proj:
        proj["_id"] = 1
    return proj


def _apply_date_range(tokens: str, now: datetime) -> Optional[Dict[str, Any]]:
    """
    Parse phrases like:
      - last 7 days
      - last 4 weeks
      - last 3 months
      - today
      - yesterday
    Returns: filter for created_at.
    """
    t = tokens.lower().strip()

    if t == "today":
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return {"created_at": {"$gte": start, "$lt": end}}

    if t == "yesterday":
        end = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        start = end - timedelta(days=1)
        return {"created_at": {"$gte": start, "$lt": end}}

    m = re.match(r"last\s+(\d+)\s*(day|days|week|weeks|month|months)\b", t)
    if m:
        qty = int(m.group(1))
        unit = m.group(2)
        if "day" in unit:
            delta = timedelta(days=qty)
        elif "week" in unit:
            delta = timedelta(weeks=qty)
        else:
            # Approximate month as 30 days for deterministic behavior
            delta = timedelta(days=qty * 30)
        start = now - delta
        return {"created_at": {"$gte": start}}

    return None


def _parse_sort(phrase: str) -> Optional[Tuple[str, int]]:
    # return (field, direction) where direction is 1 asc, -1 desc
    m = re.search(r"sort\s+by\s+([a-zA-Z0-9_\.]+)(?:\s+(asc|desc))?", phrase, re.IGNORECASE)
    if not m:
        return None
    field = m.group(1)
    dir_token = (m.group(2) or "asc").lower()
    direction = 1 if dir_token != "desc" else -1
    return (field, direction)


def _parse_limit_offset(phrase: str) -> Tuple[Optional[int], Optional[int]]:
    lim = None
    off = None
    m1 = re.search(r"\btop\s+(\d+)\b", phrase, re.IGNORECASE)
    m2 = re.search(r"\blimit\s+(\d+)\b", phrase, re.IGNORECASE)
    m3 = re.search(r"\boffset\s+(\d+)\b", phrase, re.IGNORECASE)
    for m in (m1, m2):
        if m:
            lim = int(m.group(1))
            break
    if m3:
        off = int(m3.group(1))
    return lim, off


def _parse_fields(phrase: str) -> Optional[List[str]]:
    m = re.search(r"\b(fields|select)\s+([a-zA-Z0-9_,\.\s]+)", phrase, re.IGNORECASE)
    if m:
        return _parse_list_csv(m.group(2))
    return None


def _merge_and(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    if not src:
        return dst
    # If same field appears twice, merge conditions
    for k, v in src.items():
        if k not in dst:
            dst[k] = v
        else:
            if isinstance(dst[k], dict) and isinstance(v, dict):
                dst[k].update(v)
            else:
                # Different literal, combine using $and
                existing = dst.pop(k)
                conds: List[Dict[str, Any]] = [{"{}".format(k): existing}, {"{}".format(k): v}]
                if "$and" in dst and isinstance(dst["$and"], list):
                    dst["$and"].extend(conds)
                else:
                    # Move remaining single-field dst into $and too for safety
                    and_list = [{"{}".format(k2): v2} for k2, v2 in dst.items()]
                    dst.clear()
                    dst["$and"] = and_list + conds
    return dst


def _parse_equality(phrase: str) -> Optional[Dict[str, Any]]:
    # field equals value | field is value
    m = re.search(r"\b([a-zA-Z0-9_\.]+)\s+(equals|is)\s+([^\s,]+)", phrase, re.IGNORECASE)
    if m:
        field = m.group(1)
        raw = m.group(3).strip().strip("'\"")
        val = _parse_number(raw)
        return {field: val}
    return None


def _parse_comparison(phrase: str) -> Optional[Dict[str, Any]]:
    # field >= N, field <= N, field > N, field < N
    m = re.search(r"\b([a-zA-Z0-9_\.]+)\s*(>=|<=|>|<)\s*([^\s,]+)", phrase, re.IGNORECASE)
    if not m:
        return None
    field, op, sval = m.group(1), m.group(2), m.group(3)
    val = _parse_number(sval)
    op_map = {">": "$gt", ">=": "$gte", "<": "$lt", "<=": "$lte"}
    return {field: {op_map[op]: val}}


def _parse_category(phrase: str) -> Optional[Dict[str, Any]]:
    # category: Retail or category in A,B,C
    m = re.search(r"\b([a-zA-Z0-9_\.]+)\s*:\s*([a-zA-Z0-9_\-\.]+)", phrase, re.IGNORECASE)
    if m:
        return {m.group(1): m.group(2)}
    m2 = re.search(r"\b([a-zA-Z0-9_\.]+)\s+in\s+([a-zA-Z0-9_,\.\s\-]+)", phrase, re.IGNORECASE)
    if m2:
        field = m2.group(1)
        values = _parse_list_csv(m2.group(2))
        # try numeric conversion
        converted = [_parse_number(v) for v in values]
        return {field: {"$in": converted}}
    return None


def _parse_contains(phrase: str) -> Optional[Dict[str, Any]]:
    # field contains text -> case-insensitive regex
    m = re.search(r"\b([a-zA-Z0-9_\.]+)\s+contains\s+([^\s,]+)", phrase, re.IGNORECASE)
    if m:
        field = m.group(1)
        text = re.escape(m.group(2).strip().strip("'\""))
        return {field: {"$regex": text, "$options": "i"}}
    return None


def _collect_filters(phrase: str, now: datetime) -> Dict[str, Any]:
    filt: Dict[str, Any] = {}

    # Date range keywords
    for key in ("today", "yesterday"):
        if re.search(rf"\b{key}\b", phrase, re.IGNORECASE):
            cond = _apply_date_range(key, now)
            if cond:
                _merge_and(filt, cond)

    # "last N days/weeks/months"
    m = re.search(r"last\s+\d+\s*(day|days|week|weeks|month|months)\b", phrase, re.IGNORECASE)
    if m:
        cond = _apply_date_range(m.group(0), now)
        if cond:
            _merge_and(filt, cond)

    # Comparisons
    comp = _parse_comparison(phrase)
    if comp:
        _merge_and(filt, comp)

    # Equality
    eq = _parse_equality(phrase)
    if eq:
        _merge_and(filt, eq)

    # Category/in
    cat = _parse_category(phrase)
    if cat:
        _merge_and(filt, cat)

    # Contains
    cont = _parse_contains(phrase)
    if cont:
        _merge_and(filt, cont)

    return filt


# PUBLIC_INTERFACE
def parse_nlq_to_query(nlq: str) -> Dict[str, Any]:
    """Parse NLQ into a dict: { filter, projection, sort, limit, offset }.

    The output is deterministic. Unknown segments are ignored.
    """
    phrase = (nlq or "").strip()
    now = _now_utc()
    filter_doc = _collect_filters(phrase, now)

    sort_spec = _parse_sort(phrase)
    limit, offset = _parse_limit_offset(phrase)
    fields = _parse_fields(phrase)
    projection = _ensure_projection(fields)

    out: Dict[str, Any] = {"filter": filter_doc}
    if projection:
        out["projection"] = projection
    if sort_spec:
        out["sort"] = [list(sort_spec)]  # [["field", 1|-1]] format convenient for pymongo
    if limit is not None:
        out["limit"] = limit
    if offset is not None:
        out["offset"] = offset
    return out
