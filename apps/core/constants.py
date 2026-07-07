# Offset pagination (`page` / `page_size`) and reception-style list `limit` (``parse_list_limit``).
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100
ALLOWED_LIST_PAGE_SIZES: tuple[int, ...] = (10, 20, 50, 100)

# Maximum JSON body size for ``read_json_body`` and similar guards.
MAX_JSON_BODY_BYTES = 1024 * 1024
