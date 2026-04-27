"""SMT config command: read/write .env settings."""

from typing import Optional

from src.cli._helpers import SMT_DIR

_CONFIG_KEYS = {
    'SMT_NEO4J_HEAP_INIT': ('512m', 'Neo4j JVM heap initial size  (e.g. 256m, 512m, 1g)'),
    'SMT_NEO4J_HEAP_MAX':  ('1g',   'Neo4j JVM heap max size       (e.g. 512m, 1g, 2g)'),
    'SMT_NEO4J_PAGECACHE': ('512m', 'Neo4j page-cache size         (e.g. 256m, 512m, 1g)'),
    'NEO4J_PASSWORD':      ('password', 'Neo4j auth password'),
    'NEO4J_URI':           ('bolt://localhost:7687', 'Neo4j bolt URI'),
}


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


def cmd_config(action: Optional[str], key: Optional[str], value: Optional[str]) -> int:
    env = _read_env()

    if action is None:
        print(f"\n{'KEY':<30} {'CURRENT':<20} {'DEFAULT':<20} DESCRIPTION")
        print('-' * 95)
        for k, (default, desc) in _CONFIG_KEYS.items():
            current = env.get(k, '')
            display = current if current else f'(default: {default})'
            print(f"  {k:<28} {display:<20} {default:<20} {desc}")
        print()
        print("To change a setting:")
        print("  smt config set SMT_NEO4J_HEAP_MAX 1g")
        print("  smt config set SMT_NEO4J_PAGECACHE 512m")
        print()
        print("After changing Neo4j memory, restart the container:")
        print("  smt stop && smt start")
        return 0

    if action == 'set':
        if not key or value is None:
            print("Usage: smt config set <KEY> <VALUE>")
            print("Example: smt config set SMT_NEO4J_HEAP_MAX 1g")
            return 1
        key = key.upper()
        if key not in _CONFIG_KEYS:
            known = ', '.join(_CONFIG_KEYS)
            print(f"Unknown key '{key}'. Configurable keys: {known}")
            return 1
        _write_env_key(key, value)
        _, desc = _CONFIG_KEYS[key]
        print(f"Set {key}={value}  ({desc})")
        if key.startswith('SMT_NEO4J_'):
            print("Restart Neo4j for the change to take effect:  smt stop && smt start")
        return 0

    if action == 'reset':
        for k, (default, _) in _CONFIG_KEYS.items():
            if k in _read_env():
                _write_env_key(k, default)
        print("Reset all SMT config keys to defaults.")
        print("Restart Neo4j:  smt stop && smt start")
        return 0

    print(f"Unknown config action '{action}'. Use: smt config | smt config set KEY VALUE | smt config reset")
    return 1
