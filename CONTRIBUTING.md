# Contributing to Save My Tokens

Thanks for your interest in improving SMT! Here's how to contribute.

## Setup for Development

```bash
git clone https://github.com/budagov-lab/save-my-tokens
cd save-my-tokens
pip install -e ".[dev]"
```

This installs dev dependencies: `pytest`, `black`, `mypy`, `ruff`, `isort`.

## Running Tests

```bash
pytest tests/ -v              # Run all tests
pytest tests/unit/ -v         # Run unit tests only
pytest --cov=src              # With coverage report
```

We aim for >80% coverage on new code.

## Code Style

We enforce:
- **Black** for formatting (line length: 100)
- **isort** for import sorting
- **mypy strict** for type checking
- **ruff** for linting

Run all checks:
```bash
black src/ --line-length 100
isort src/
mypy src/ --ignore-missing-imports
ruff check src/
```

Or use the pre-commit hook:
```bash
pre-commit install
pre-commit run --all-files
```

## Project Structure

```
src/
├── graph/
│   ├── cycle_detector.py     # SCC detection
│   ├── compressor.py         # Bridge removal
│   ├── validator.py          # Git freshness checks
│   ├── neo4j_client.py       # Neo4j driver
│   ├── graph_builder.py      # Main pipeline
│   └── ...
├── parsers/
│   ├── python_parser.py
│   ├── typescript_parser.py
│   └── ...
└── smt_cli.py                # CLI commands
```

## Key Modules

### `cycle_detector.py`
Detects cycles using Tarjan's SCC algorithm. Main function:
```python
acyclic_nodes, cycle_groups = detect_cycles(node_names, edges)
```

### `compressor.py`
Removes bridge functions (1-in, 1-out nodes). Main function:
```python
result = compress_subgraph(root, nodes, edges, cycle_members)
```

### `validator.py`
Checks git freshness. Main function:
```python
validation = validate_graph(neo4j_client, repo_path)
```

### `smt_cli.py`
Three query modes: `cmd_definition`, `cmd_context`, `cmd_impact`

## Adding a New Feature

1. **Start with a test** — Write the test case first
2. **Implement** — Add code to pass the test
3. **Check style** — Run black, mypy, ruff
4. **Document** — Add docstrings + update README if user-facing
5. **Commit** — Include all test + implementation changes

### Example: Add a new retrieval mode

```python
# 1. Add test in tests/unit/test_new_mode.py
def test_new_mode():
    assert new_mode(...) == expected

# 2. Implement in src/graph/new_mode.py
def new_mode(symbol, depth):
    """Query for X"""
    ...

# 3. Add CLI command in src/smt_cli.py
def cmd_new_mode(symbol):
    ...

# 4. Register in argparse (main function)
p_new = sub.add_parser('new-mode', help='...')

# 5. Test everything
pytest tests/
black src/ --line-length 100
mypy src/

# 6. Commit
git commit -m "feat: Add new-mode query type"
```

## Extending Language Support

To add a new language (e.g., Go, Rust):

1. **Find/write Tree-sitter parser** — https://tree-sitter.github.io/tree-sitter/
2. **Create parser class** — `src/parsers/go_parser.py`
3. **Extract symbols** — Implement `parse()` method
4. **Add to GraphBuilder** — Register in `_parse_all_files()`
5. **Test** — Add parser tests

See `src/parsers/typescript_parser.py` for example.

## Debugging

### Check graph contents
```python
from src.graph.neo4j_client import Neo4jClient
from src.config import settings

client = Neo4jClient()
stats = client.get_stats()
print(stats)  # node_count, edge_count
```

### Neo4j Browser
Visit http://localhost:7475 to browse the graph interactively.

Query example:
```cypher
MATCH (f:Function {name: "my_function"})
RETURN f, labels(f)
```

### Enable debug logging
```bash
PYTHONIOENCODING=utf-8 python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
# ... run your code
"
```

## Performance Notes

- **Connection pooling** — CLI reuses single Neo4j connection
- **Query optimization** — See OPTIMIZATION_FINDINGS.md for Cypher tuning
- **Cycle detection** — Tarjan's is O(V+E), fast even for 10k+ nodes
- **Large graphs** — Tested up to 40k+ nodes, sub-30ms queries

## Commit Messages

Follow conventional commits:
```
feat: Add new query mode
fix: Correct cycle detection edge case
perf: Optimize Neo4j traversal query
docs: Update README with examples
refactor: Extract cycle logic to module
test: Add comprehensive SCC tests
```

Include context in the message body if the change is non-obvious.

## PR Process

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Write tests + implementation
4. Run full test suite (`pytest tests/ -v`)
5. Ensure code style (`black`, `mypy`, `ruff`)
6. Push and create a PR with detailed description
7. Wait for CI checks to pass
8. Address review feedback

## Questions?

- Check [FINAL_SUMMARY.md](FINAL_SUMMARY.md) for architecture
- Check [README.md](README.md) for usage examples
- Open an issue on GitHub for help

Happy contributing! 🚀
