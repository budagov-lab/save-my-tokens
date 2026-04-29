"""SMT config command: read/write .env settings and ~/.smt/config.json user prefs."""

from typing import Any, Optional

from src.cli._helpers import (
    SMT_DIR,
    _GLOBAL_CONFIG_SCHEMA,
    _GLOBAL_CONFIG_FILE,
    _read_global_config,
    _write_global_config,
)

# ---------------------------------------------------------------------------
# .env keys (Neo4j / container settings)
# ---------------------------------------------------------------------------

_ENV_KEYS = {
    'SMT_NEO4J_HEAP_INIT': ('512m',                  'Neo4j JVM heap initial size  (e.g. 256m, 512m, 1g)'),
    'SMT_NEO4J_HEAP_MAX':  ('1g',                    'Neo4j JVM heap max size       (e.g. 512m, 1g, 2g)'),
    'SMT_NEO4J_PAGECACHE': ('512m',                  'Neo4j page-cache size         (e.g. 256m, 512m, 1g)'),
    'NEO4J_PASSWORD':      ('password',              'Neo4j auth password'),
    'NEO4J_URI':           ('bolt://localhost:7687', 'Neo4j bolt URI'),
}

# Keep legacy alias so callers that import _CONFIG_KEYS still work
_CONFIG_KEYS = _ENV_KEYS


def _read_env() -> dict:
    env_file = SMT_DIR / '.env'
    result: dict = {}
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                result[k.strip()] = v.strip()
    return result


def _write_env_key(key: str, value: str) -> None:
    env_file = SMT_DIR / '.env'
    lines = env_file.read_text(encoding='utf-8').splitlines() if env_file.exists() else []
    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f'{key}=') or stripped == key:
            new_lines.append(f'{key}={value}')
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f'{key}={value}')
    env_file.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')


def _coerce_global_value(key: str, raw: str) -> Any:
    """Parse a CLI string into the correct type for a global config key."""
    schema = _GLOBAL_CONFIG_SCHEMA[key]
    t = schema['type']
    if t == 'bool':
        if raw.lower() in ('1', 'true', 'yes', 'on'):
            return True
        if raw.lower() in ('0', 'false', 'no', 'off'):
            return False
        raise ValueError(f"'{raw}' is not a valid boolean — use true/false")
    if t == 'int':
        v = int(raw)
        if not (1 <= v <= 10):
            raise ValueError(f"depth must be 1–10, got {v}")
        return v
    # path — store as string, expand ~ at read time
    return raw


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------

def cmd_config(action: Optional[str], key: Optional[str], value: Optional[str]) -> int:
    if action is None:
        _print_all()
        return 0

    if action == 'set':
        return _do_set(key, value)

    if action == 'reset':
        return _do_reset()

    print(f"Unknown config action '{action}'. Use: smt config | smt config set KEY VALUE | smt config reset")
    return 1


def _print_all() -> None:
    env = _read_env()
    gcfg = _read_global_config()

    # --- Neo4j / container (.env) ---
    print(f"\n{'Neo4j / container settings'}  (.env)")
    print(f"  {'KEY':<28} {'CURRENT':<22} {'DEFAULT':<22} DESCRIPTION")
    print('  ' + '-' * 95)
    for k, (default, desc) in _ENV_KEYS.items():
        current = env.get(k, '')
        display = current if current else f'(default: {default})'
        print(f"  {k:<28} {display:<22} {default:<22} {desc}")

    # --- User preferences (~/.smt/config.json) ---
    print(f"\n{'User preferences'}  (~/.smt/config.json)")
    print(f"  {'KEY':<20} {'CURRENT':<22} {'DEFAULT':<12} DESCRIPTION")
    print('  ' + '-' * 85)
    for k, meta in _GLOBAL_CONFIG_SCHEMA.items():
        current = gcfg.get(k)
        default = meta['default']
        cur_str = str(current) if current is not None else '(not set)'
        def_str = str(default) if default is not None else '(none)'
        print(f"  {k:<20} {cur_str:<22} {def_str:<12} {meta['desc']}")

    print()
    print("Usage:")
    print("  smt config set SMT_NEO4J_HEAP_MAX 2g")
    print("  smt config set models_dir ~/.smt/models")
    print("  smt config set default_depth 3")
    print("  smt config set compact true")
    print("  smt config reset")
    print()


def _do_set(key: Optional[str], value: Optional[str]) -> int:
    if not key or value is None:
        print("Usage: smt config set <KEY> <VALUE>")
        return 1

    # Global preference key (lowercase)
    if key in _GLOBAL_CONFIG_SCHEMA:
        try:
            coerced = _coerce_global_value(key, value)
        except ValueError as e:
            print(f"Invalid value for '{key}': {e}")
            return 1
        _write_global_config(key, coerced)
        print(f"[global] {key} = {coerced}  ({_GLOBAL_CONFIG_SCHEMA[key]['desc']})")
        if key == 'models_dir':
            print("         Model will be downloaded there on next 'smt search'.")
        return 0

    # .env key (uppercase)
    upper = key.upper()
    if upper in _ENV_KEYS:
        _write_env_key(upper, value)
        _, desc = _ENV_KEYS[upper]
        print(f"[env]    {upper} = {value}  ({desc})")
        if upper.startswith('SMT_NEO4J_'):
            print("         Restart Neo4j for the change to take effect:  smt stop && smt start")
        return 0

    known = ', '.join(list(_ENV_KEYS) + list(_GLOBAL_CONFIG_SCHEMA))
    print(f"Unknown key '{key}'. Configurable keys: {known}")
    return 1


def _do_reset() -> int:
    # Reset .env keys
    for k, (default, _) in _ENV_KEYS.items():
        if k in _read_env():
            _write_env_key(k, default)
    # Reset global prefs
    gcfg = _read_global_config()
    for k in list(_GLOBAL_CONFIG_SCHEMA):
        if k in gcfg:
            _write_global_config(k, None)
    print("Reset all SMT config keys to defaults.")
    print("Restart Neo4j if you changed container settings:  smt stop && smt start")
    return 0
