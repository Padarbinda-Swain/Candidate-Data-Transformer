"""
config_loader.py
-----------------
Loads the runtime projection config and applies it to an internal canonical
record to produce the final output document.

The config controls *output shaping only* — it never changes how extraction,
normalization, or merging happen internally. This keeps the engine stable
while letting downstream consumers reshape/rename/select fields without
touching code, per the assignment's "configurable output" requirement.

Config schema (config/config.json):
{
  "fields": [
    {"path": "<output.path>", "from": "<internal.path>", "type": "string",
     "required": true|false, "normalize": "<name>|null"}
  ],
  "include_confidence": true|false,
  "on_missing": "null" | "omit" | "error"
}

- "path"  : dotted path in the OUTPUT document (supports list shorthand
            "skills[].name" meaning "for each item in skills, take .name").
- "from"  : dotted path in the INTERNAL canonical record to read the value
            from. Same dotted/list syntax as "path".
- "normalize": optional name of a normalizer already applied during the
            pipeline; recorded here only for documentation/traceability —
            actual normalization happens in normalizer.py.
- on_missing: what to do when a value can't be resolved:
            "null" -> set null (default, matches required schema)
            "omit" -> drop the key entirely
            "error"-> raise immediately (fail loud, used for strict configs)
"""
import json
import copy


DEFAULT_CONFIG = {
    "fields": [
        {"path": "candidate_id", "from": "candidate_id", "type": "string", "required": True},
        {"path": "full_name", "from": "full_name", "type": "string", "required": True},
        {"path": "emails", "from": "emails", "type": "string[]", "required": False},
        {"path": "phones", "from": "phones", "type": "string[]", "required": False},
        {"path": "location", "from": "location", "type": "object", "required": False},
        {"path": "links", "from": "links", "type": "object", "required": False},
        {"path": "headline", "from": "headline", "type": "string", "required": False},
        {"path": "years_experience", "from": "years_experience", "type": "number", "required": False},
        {"path": "skills", "from": "skills", "type": "array", "required": False},
        {"path": "experience", "from": "experience", "type": "array", "required": False},
        {"path": "education", "from": "education", "type": "array", "required": False},
        {"path": "provenance", "from": "provenance", "type": "array", "required": False},
        {"path": "overall_confidence", "from": "overall_confidence", "type": "number", "required": False},
    ],
    "include_confidence": True,
    "on_missing": "null",
}


def load_config(path):
    """Load a JSON config file, falling back to DEFAULT_CONFIG if no path given."""
    if not path:
        return copy.deepcopy(DEFAULT_CONFIG)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("fields", DEFAULT_CONFIG["fields"])
    cfg.setdefault("include_confidence", True)
    cfg.setdefault("on_missing", "null")
    return cfg


def _split_path(path):
    """Split 'a.b[].c' into [('a', False), ('b', True), ('c', False)]
    where the bool marks 'iterate over this list'. A trailing [] on the
    final token means 'this whole field is a list'."""
    tokens = []
    for raw in path.split("."):
        is_list = raw.endswith("[]")
        name = raw[:-2] if is_list else raw
        tokens.append((name, is_list))
    return tokens


def get_path(record, path):
    """Resolve a dotted path (with optional [] list markers) against `record`.
    Returns the resolved value, or None if any part of the path is missing."""
    tokens = _split_path(path)
    current = record

    for i, (name, is_list) in enumerate(tokens):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(name)
        else:
            return None

        if is_list:
            if not isinstance(current, list):
                return None
            remaining = ".".join(
                ("%s[]" % n if lst else n) for n, lst in tokens[i + 1:]
            )
            if not remaining:
                return current
            return [get_path(item, remaining) for item in current]
    return current


def _set_path(doc, path, value):
    """Set a value into `doc` at dotted path, creating nested dicts as needed."""
    parts = path.split(".")
    cur = doc
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def apply_config(internal_record, config):
    """Project an internal canonical record into the configured output shape."""
    output = {}
    on_missing = config.get("on_missing", "null")

    for field in config["fields"]:
        out_path = field["path"]
        from_path = field.get("from", out_path)
        value = get_path(internal_record, from_path)

        if value is None:
            if field.get("required") and on_missing == "error":
                raise ValueError(f"Required field '{out_path}' missing (from '{from_path}')")
            if on_missing == "omit" and not field.get("required"):
                continue
            value = None  # default: explicit null, never crash

        _set_path(output, out_path, value)

    if not config.get("include_confidence", True):
        output.pop("overall_confidence", None)

    return output
