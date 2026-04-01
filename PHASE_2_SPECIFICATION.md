# Phase 2 Specification - Detailed Engineering Plan

**Document Date:** April 1, 2026  
**Status:** Ready for Implementation  
**Timeline:** 18 weeks (4.5 months)  
**Team:** 1 Backend + 1 ML/Analytics + 0.5 DevOps

---

## Executive Summary

Phase 2 adds four production capabilities on top of Phase 1's solid foundation. This document provides engineering-grade specs for each feature: detailed implementation approach, failure modes, test strategies, and measurable success criteria.

**Key Principle:** All Phase 2 features are **additive, not disruptive**. No breaking changes to Phase 1 APIs.

---

## Phase 1 Baseline Metrics (For Comparison)

These are actual Phase 1 results to establish baselines for Phase 2 targets:

| Metric | Phase 1 Actual | Phase 2 Target | Notes |
|--------|---|---|---|
| Symbol extraction rate | >98% | ≥95% per language | Python/TS validated; Go/Rust/Java new |
| Query latency (p99) | <10ms | <50ms | Incremental updates may add overhead |
| Graph consistency | 100% | >99.5% | Must validate after incremental mutations |
| Parser + Index time per 1K LOC | ~5ms | <10ms | Incremental should be <100ms per file |
| Token efficiency vs naive | 96.9% | ≥96% | Maintain Phase 1 achievement |
| Test coverage | 85%+ | ≥85% | Add new feature tests |
| CI/CD time | ~2min | <3min | Keep fast iteration |

---

## Feature 1: Incremental Updates (Weeks 1-4)

**Goal:** Support git-based incremental parsing without full re-parse. Enable agents to work on evolving codebases efficiently.

### 1.1 Git Diff Parsing

**Input:** Git diff output from two commits/branches

**Implementation:**

```python
class DiffParser:
    """Parse git diffs to identify symbol-level changes."""
    
    def parse_diff(self, diff_text: str) -> DiffSummary:
        """Returns files added/modified/deleted"""
        
    def identify_changed_files(self) -> Set[str]:
        """Return only .py/.ts files that changed"""
        
    def is_structural_change(self, file_path: str) -> bool:
        """Heuristic: did the file's AST structure change, or just content?"""
        # Simple: parse file before/after, compare top-level symbols
```

**Scope Clarification:**
- **Phase 2 Focus:** Python only (existing parser is mature)
- TypeScript support in Phase 2.5 (after Python validation)
- Simple heuristic: if function/class list changed, re-parse

**Success Criteria:**
- Parse git diff in <10ms
- Correctly identify 100% of files with structural changes
- False positive rate <5% (re-parse unnecessary files)

**Test Scenarios:**
1. Single function added
2. Function signature changed (parameter added)
3. Function renamed (semantic change detection?)
4. Import statement added
5. Large refactor (many files changed)

---

### 1.2 Incremental Symbol Updates

**Process:**
1. Run DiffParser on git diff → list of changed files
2. For each changed file:
   - Re-parse with PythonParser
   - Generate delta: new symbols, deleted symbols, modified symbols
   - Update SymbolIndex in-memory
   - Queue Neo4j mutations

**Symbol Delta Format:**

```python
@dataclass
class SymbolDelta:
    file: str
    added: List[Symbol]      # New symbols
    deleted: List[str]       # Symbol names removed
    modified: List[Symbol]   # Changed definitions
    timestamp: datetime      # When this delta was created
```

**Implementation Details:**

```python
class IncrementalSymbolUpdater:
    def __init__(self, symbol_index: SymbolIndex, neo4j_client: Neo4jClient):
        self.index = symbol_index
        self.neo4j = neo4j_client
        self.delta_history: List[SymbolDelta] = []
    
    def apply_delta(self, delta: SymbolDelta) -> UpdateResult:
        """Apply symbol changes to index and Neo4j.
        
        Guarantees: All-or-nothing (transactional).
        Rollback on any error.
        """
        try:
            # 1. Update in-memory index (fast)
            for sym in delta.added:
                self.index.add(sym)
            for sym_name in delta.deleted:
                self.index.remove(sym_name)
            
            # 2. Update Neo4j (transactional)
            tx = self.neo4j.begin_transaction()
            self._update_nodes(tx, delta)
            self._update_edges(tx, delta)
            tx.commit()
            
            # 3. Record delta for consistency verification
            self.delta_history.append(delta)
            
            return UpdateResult(success=True, delta=delta)
        except Exception as e:
            # Rollback on failure
            self.index.rollback_to_last_valid()
            self.neo4j.abort_transaction()
            return UpdateResult(success=False, error=str(e))
    
    def _update_nodes(self, tx, delta: SymbolDelta):
        """Create new symbol nodes, delete old ones"""
        # For each added symbol: CREATE (n:Symbol) SET n += symbol_data
        # For each deleted symbol: MATCH (n:Symbol {id: ...}) DELETE n
    
    def _update_edges(self, tx, delta: SymbolDelta):
        """Update edges: remove edges for deleted symbols,
        rebuild edges for modified symbols"""
        # For each deleted symbol's edges: MATCH (...)-[r]-(...) DELETE r
        # For each modified symbol: re-analyze calls + imports
```

**Failure Modes & Recovery:**

| Mode | Cause | Detection | Recovery |
|------|-------|-----------|----------|
| Partial update | Neo4j connection loss mid-transaction | Exception + tx.rollback() | Retry from clean state |
| Symbol conflict | Same symbol in delta + existing index | Duplicate key error | Abort, report to user |
| Dangling edges | Deleted symbol still referenced | Referential integrity violation | Cleanup edges before deleting node |
| Version skew | Delta applies to wrong baseline | Hash mismatch on expected symbols | Require explicit base commit hash |

**Consistency Validation:**

After each delta, run:

```python
def validate_graph_consistency(neo4j_client):
    """Post-update validation"""
    
    # 1. Check referential integrity
    # Every edge's source/target nodes must exist
    orphaned = neo4j_client.query("""
        MATCH (s)-[r]-(t)
        WHERE NOT EXISTS((s)) OR NOT EXISTS((t))
        RETURN count(r)
    """)
    assert orphaned == 0, f"Found {orphaned} orphaned edges"
    
    # 2. Check symbol uniqueness per file
    # No two symbols with same name in same file
    duplicates = neo4j_client.query("""
        MATCH (s1:Symbol)--(f:File), (s2:Symbol)--(f)
        WHERE s1.name = s2.name AND s1.id <> s2.id
        RETURN count(*)
    """)
    assert duplicates == 0, f"Found {duplicates} duplicate symbols"
    
    # 3. Check edge types are valid
    # All edge types must be in EdgeType enum
    invalid = neo4j_client.query("""
        MATCH ()-[r]->()
        WHERE r.type NOT IN ['IMPORTS', 'CALLS', 'DEFINES', 'INHERITS', 'DEPENDS_ON', 'TYPE_OF', 'IMPLEMENTS']
        RETURN count(r)
    """)
    assert invalid == 0, f"Found {invalid} invalid edge types"
```

**Performance Targets:**

| Operation | Target | Baseline | Assumption |
|-----------|--------|----------|-----------|
| Parse single file (500 LOC) | <20ms | ~2ms per 100 LOC | Parsing is fast |
| Update SymbolIndex (100 symbols) | <5ms | O(1) per symbol | Dict-based, no scanning |
| Neo4j transaction (10 symbols, 50 edges) | <50ms | Actual Phase 1 varies | Depends on Neo4j indexing |
| Full incremental update (5 changed files, ~1K LOC) | <100ms | — | Goal: 10x faster than full parse |

**Test Plan:**

```python
def test_incremental_update():
    # Scenario: add one function, modify one, delete one
    
    # Setup: Flask repo in Neo4j
    builder = GraphBuilder('tests/fixtures/test_repos/flask')
    builder.build()
    initial_count = builder.symbol_index.count()
    
    # Apply delta
    delta = SymbolDelta(
        file='src/api.py',
        added=[Symbol(name='new_func', ...)],
        deleted=['old_func'],
        modified=[Symbol(name='updated_func', ...)]
    )
    updater = IncrementalSymbolUpdater(...)
    result = updater.apply_delta(delta)
    
    # Verify
    assert result.success
    assert builder.symbol_index.count() == initial_count + 1 - 1  # +1 -1
    assert validate_graph_consistency(neo4j_client)
    
    # Performance: <100ms total
    assert result.duration_ms < 100

def test_incremental_failure_rollback():
    # Simulate Neo4j failure mid-transaction
    # Verify: symbol index and Neo4j both rollback to pre-delta state
    
    # Setup
    initial_symbols = index.get_all()
    initial_neo4j_nodes = count(neo4j.nodes)
    
    # Apply delta with simulated failure
    with patch('neo4j_client.commit') as mock:
        mock.side_effect = ConnectionError()
        result = updater.apply_delta(delta)
    
    # Verify rollback
    assert not result.success
    assert index.get_all() == initial_symbols
    assert count(neo4j.nodes) == initial_neo4j_nodes
```

**Success Criteria:**
- ✓ Incremental parse <100ms for typical changes (<10% of codebase)
- ✓ Graph consistency validated post-update (no orphaned edges)
- ✓ Rollback on failure (no partial updates)
- ✓ 100+ successive deltas without corruption
- ✓ Phase 1 query latency unchanged (<50ms p99)

---

## Feature 2: Contract Extraction & Validation (Weeks 5-8)

**Goal:** Detect breaking changes automatically before executing parallel tasks.

### 2.1 Contract Extraction Strategy

**Definition:** Contract = extractable guarantees about function behavior

**What We Extract:**

```python
@dataclass
class FunctionContract:
    symbol: Symbol
    signature: SignatureInfo      # Parameters, return type
    docstring_contract: Optional[str]   # Pre/post conditions from docstring
    type_hints: Dict[str, str]    # Extracted type annotations
    preconditions: List[str]      # Heuristic: "requires X", "assumes Y"
    return_type: str
    
@dataclass
class SignatureInfo:
    parameters: List[str]         # Parameter names
    parameter_types: List[str]    # From type hints
    return_type: str
    is_optional: Dict[str, bool]  # Which params are optional?
```

**Extraction Approach:**

```python
class ContractExtractor:
    """Extract implicit and explicit contracts from code."""
    
    def extract_function_contract(self, symbol: Symbol, source: str) -> FunctionContract:
        """Extract contract from function definition + docstring."""
        
        # 1. Parse signature (AST)
        ast_node = self._find_ast_node(source, symbol)
        signature = self._extract_signature(ast_node)
        
        # 2. Extract docstring (Google format only, Phase 2)
        docstring = ast.get_docstring(ast_node) or ""
        contract_lines = self._parse_google_docstring(docstring)
        
        # 3. Build contract
        return FunctionContract(
            symbol=symbol,
            signature=signature,
            docstring_contract=self._summarize_contract(contract_lines),
            type_hints=self._extract_type_hints(ast_node),
            preconditions=self._extract_preconditions(docstring),
            return_type=self._extract_return_type(ast_node)
        )
    
    def _parse_google_docstring(self, docstring: str) -> Dict[str, str]:
        """Parse Google-style docstring sections.
        
        Format:
            Args:
                param (type): description
            
            Returns:
                type: description
            
            Raises:
                ExceptionType: when...
        """
        sections = {}
        current_section = None
        
        for line in docstring.split('\n'):
            if line.strip().endswith(':') and line.strip()[:-1] in ['Args', 'Returns', 'Raises', 'Note']:
                current_section = line.strip()[:-1]
                sections[current_section] = []
            elif current_section:
                sections[current_section].append(line)
        
        return sections
```

**Scope Clarification:**
- **Phase 2 Focus:** Google-style docstrings only
  - Reason: Most common in modern Python
  - Fallback: If no docstring, use type hints only
  - Future: Support NumPy/Sphinx in Phase 2.5
- Type hints are **required** for contract validation (Python 3.11+)

**Supported Contracts:**
1. **Signature changes** (parameter added/removed/renamed)
2. **Type changes** (parameter type, return type)
3. **Preconditions** (extracted from "Args" section, e.g., "non-negative integer")
4. **Exceptions** (extracted from "Raises" section)

**NOT Supported (Out of scope):**
- Semantic behavior changes (detected manually)
- Complex type hierarchies (generics, unions—too fragile)
- Implicit contracts (magic side effects, global state)

---

### 2.2 Breaking Change Detection

**Breaking Change Definition:**

A change is **breaking** if it violates assumptions about an existing function.

```python
class BreakingChangeDetector:
    def detect_breaking_changes(self, 
                               old_contract: FunctionContract,
                               new_contract: FunctionContract) -> List[BreakingChange]:
        """Compare contracts, return breaking changes."""
        
        changes = []
        
        # 1. Parameter removal (breaking)
        old_params = {p.name for p in old_contract.signature.parameters}
        new_params = {p.name for p in new_contract.signature.parameters}
        
        removed = old_params - new_params
        if removed:
            changes.append(BreakingChange(
                type="PARAMETER_REMOVED",
                severity="HIGH",
                parameters=removed,
                impact="All callers passing this parameter will fail"
            ))
        
        # 2. Return type narrowed (breaking for some usages)
        if self._return_type_narrowed(old_contract.return_type, new_contract.return_type):
            changes.append(BreakingChange(
                type="RETURN_TYPE_NARROWED",
                severity="MEDIUM",
                old_type=old_contract.return_type,
                new_type=new_contract.return_type,
                impact="Callers expecting old return type may fail"
            ))
        
        # 3. Exception added (generally not breaking, but notable)
        old_exceptions = set(old_contract.exceptions)
        new_exceptions = set(new_contract.exceptions)
        added = new_exceptions - old_exceptions
        
        if added:
            changes.append(BreakingChange(
                type="EXCEPTION_ADDED",
                severity="LOW",
                exceptions=added,
                impact="Callers may need updated error handling"
            ))
        
        return changes

@dataclass
class BreakingChange:
    type: str              # PARAMETER_REMOVED, RETURN_TYPE_NARROWED, etc.
    severity: str          # HIGH, MEDIUM, LOW
    impact: str            # Human-readable explanation
    # ... other fields
```

**Test Scenarios:**

```python
def test_breaking_change_parameter_removed():
    old = FunctionContract(
        symbol=Symbol(name='process'),
        signature=SignatureInfo(parameters=['data', 'validate']),
        ...
    )
    new = FunctionContract(
        symbol=Symbol(name='process'),
        signature=SignatureInfo(parameters=['data']),  # 'validate' removed
        ...
    )
    
    detector = BreakingChangeDetector()
    changes = detector.detect_breaking_changes(old, new)
    
    assert len(changes) == 1
    assert changes[0].type == 'PARAMETER_REMOVED'
    assert 'validate' in changes[0].parameters
    assert changes[0].severity == 'HIGH'

def test_non_breaking_optional_parameter_added():
    old = FunctionContract(..., signature=SignatureInfo(parameters=['data']))
    new = FunctionContract(..., signature=SignatureInfo(
        parameters=['data', 'validate'],
        is_optional={'validate': True}  # Optional = not breaking
    ))
    
    detector = BreakingChangeDetector()
    changes = detector.detect_breaking_changes(old, new)
    
    assert len(changes) == 0  # No breaking changes
```

---

### 2.3 Conflict Detection v2 (Contract-Based)

**Input:** List of tasks with modifications to symbols

**Output:** Conflict report with breaking changes

```python
def validate_task_conflicts(tasks: List[Task], 
                           contracts: Dict[str, FunctionContract]) -> ConflictReport:
    """Detect if tasks conflict via contract violations."""
    
    conflicts = []
    
    for i, task_a in enumerate(tasks):
        for task_b in tasks[i+1:]:
            # Check if task_a modifies symbols that task_b depends on
            for symbol in task_a.modifications:
                if symbol in task_b.dependencies:
                    # Potential conflict: task_a changes what task_b needs
                    
                    old_contract = contracts.get(symbol)
                    new_contract = task_a.proposed_changes.get(symbol)
                    
                    if old_contract and new_contract:
                        breaking = BreakingChangeDetector().detect_breaking_changes(
                            old_contract, new_contract
                        )
                        
                        if breaking:
                            conflicts.append(Conflict(
                                task_a=task_a.id,
                                task_b=task_b.id,
                                symbol=symbol,
                                breaking_changes=breaking,
                                can_parallelize=False
                            ))
    
    return ConflictReport(
        conflicts=conflicts,
        can_parallelize_all=len(conflicts) == 0
    )
```

**Success Criteria:**
- ✓ >95% precision (few false positives)
- ✓ >90% recall (catch most real conflicts)
- ✓ <500ms to validate 100-task batch
- ✓ All test scenarios pass

**Test Plan:**

```python
def test_contract_validation_100_tasks():
    # Load contracts for Flask (18.4K LOC)
    contracts = ContractExtractor().extract_all_contracts(repo_path)
    
    # Generate 100 synthetic tasks
    tasks = [...]
    
    # Measure validation time
    start = time.time()
    report = validate_task_conflicts(tasks, contracts)
    elapsed = time.time() - start
    
    assert elapsed < 0.5  # <500ms
    assert report.conflicts_detected == expected_conflicts
```

---

## Feature 3: Multi-Language Support (Weeks 9-11)

**Goal:** Extract symbols from Go, Rust, and Java codebases.

### 3.1 Language Support Priority

| Language | Priority | Complexity | Effort | Success Target |
|----------|----------|-----------|--------|-----------------|
| **Python** | Phase 1 ✓ | Simple | Done | 98%+ |
| **TypeScript** | Phase 1 ✓ | Medium | Done | 95%+ |
| **Go** | Phase 2 | Low-Medium | 1.5 weeks | ≥95% |
| **Rust** | Phase 2 | Medium-High | 2 weeks | ≥90% |
| **Java** | Phase 2 | Medium | 1.5 weeks | ≥95% |

### 3.2 Go Parser

**Strategy:** Tree-sitter grammar (already available)

```python
class GoParser(BaseParser):
    """Extract symbols from Go source code."""
    
    LANGUAGE = "go"
    
    def _extract_symbols(self, tree, source_code: str, file_path: str) -> List[Symbol]:
        """Extract top-level functions, types, interfaces, methods."""
        
        symbols = []
        
        # 1. Top-level function declarations
        for node in self._find_nodes(tree, 'function_declaration'):
            symbols.append(Symbol(
                name=node.child_by_field_name('name').text.decode(),
                type='function',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
        
        # 2. Type declarations (struct, interface)
        for node in self._find_nodes(tree, 'type_declaration'):
            type_name = node.child_by_field_name('name').text.decode()
            
            # Type itself
            symbols.append(Symbol(
                name=type_name,
                type='type',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
            
            # Methods on type (receiver)
            for method in self._find_methods_on_type(tree, type_name):
                symbols.append(Symbol(
                    name=f"{type_name}.{method.name}",
                    type='method',
                    file=file_path,
                    line=method.line,
                    column=method.column,
                    parent=type_name
                ))
        
        # 3. Interface declarations
        for node in self._find_nodes(tree, 'interface_type'):
            interface_name = self._get_interface_name(node)
            symbols.append(Symbol(
                name=interface_name,
                type='interface',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
        
        return symbols
    
    def extract_imports(self, tree, file_path: str) -> List[Import]:
        """Extract import statements."""
        imports = []
        
        for node in self._find_nodes(tree, 'import_declaration'):
            # Handle: import "package/name"
            #         import alias "package/name"
            package = node.child_by_field_name('path').text.decode().strip('"')
            alias = node.child_by_field_name('alias')
            
            imports.append(Import(
                module=package,
                alias=alias.text.decode() if alias else None,
                line=node.start_point[0] + 1
            ))
        
        return imports
```

**What NOT to Extract (Scope):**
- Goroutines (runtime concept, not static symbol)
- Channel types (implicit in signatures, not separate symbols)
- Interfaces implemented by types (inferred dynamically)

**Test Repo:** stdlib or small production Go project (10K LOC)

**Success Criteria:**
- ✓ Extract 100% of functions, types, interfaces
- ✓ Extract 95%+ of imports
- ✓ <50ms parse per 1K LOC
- ✓ 100% accuracy on method discovery

---

### 3.3 Rust Parser

**Strategy:** Tree-sitter grammar (available)

```python
class RustParser(BaseParser):
    """Extract symbols from Rust source code."""
    
    LANGUAGE = "rust"
    
    def _extract_symbols(self, tree, source_code: str, file_path: str) -> List[Symbol]:
        """Extract functions, structs, traits, impls, enums."""
        
        symbols = []
        
        # 1. Function declarations
        for node in self._find_nodes(tree, 'function_item'):
            symbols.append(Symbol(
                name=node.child_by_field_name('name').text.decode(),
                type='function',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
        
        # 2. Struct declarations
        for node in self._find_nodes(tree, 'struct_item'):
            symbols.append(Symbol(
                name=node.child_by_field_name('name').text.decode(),
                type='struct',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
        
        # 3. Trait declarations
        for node in self._find_nodes(tree, 'trait_item'):
            symbols.append(Symbol(
                name=node.child_by_field_name('name').text.decode(),
                type='trait',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
        
        # 4. Impl blocks (methods on structs/traits)
        for node in self._find_nodes(tree, 'impl_item'):
            struct_name = self._get_impl_target(node)
            
            for method in self._find_methods_in_impl(node):
                symbols.append(Symbol(
                    name=f"{struct_name}.{method.name}",
                    type='method',
                    file=file_path,
                    line=method.line,
                    column=method.column,
                    parent=struct_name
                ))
        
        # 5. Enum declarations
        for node in self._find_nodes(tree, 'enum_item'):
            symbols.append(Symbol(
                name=node.child_by_field_name('name').text.decode(),
                type='enum',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
        
        return symbols
    
    def extract_imports(self, tree, file_path: str) -> List[Import]:
        """Extract use statements."""
        imports = []
        
        for node in self._find_nodes(tree, 'use_declaration'):
            module = self._get_use_path(node)
            imports.append(Import(
                module=module,
                alias=None,
                line=node.start_point[0] + 1
            ))
        
        return imports
```

**What NOT to Extract (Scope):**
- Macro invocations (compile-time, hard to analyze)
- Lifetime parameters (type system detail)
- Trait bounds (inferred from context)

**Test Repo:** Small Rust crate (5K-10K LOC)

**Success Criteria:**
- ✓ Extract 95%+ of functions, structs, traits, impls
- ✓ Extract 90%+ of imports
- ✓ <50ms parse per 1K LOC
- ✓ Handle generics correctly

---

### 3.4 Java Parser

**Strategy:** Tree-sitter grammar (available)

```python
class JavaParser(BaseParser):
    """Extract symbols from Java source code."""
    
    LANGUAGE = "java"
    
    def _extract_symbols(self, tree, source_code: str, file_path: str) -> List[Symbol]:
        """Extract classes, interfaces, methods, fields."""
        
        symbols = []
        
        # 1. Class declarations
        for node in self._find_nodes(tree, 'class_declaration'):
            class_name = node.child_by_field_name('name').text.decode()
            
            symbols.append(Symbol(
                name=class_name,
                type='class',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
            
            # Methods in class
            for method in self._find_methods_in_class(node):
                symbols.append(Symbol(
                    name=f"{class_name}.{method.name}",
                    type='method',
                    file=file_path,
                    line=method.line,
                    column=method.column,
                    parent=class_name
                ))
        
        # 2. Interface declarations
        for node in self._find_nodes(tree, 'interface_declaration'):
            interface_name = node.child_by_field_name('name').text.decode()
            
            symbols.append(Symbol(
                name=interface_name,
                type='interface',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
            
            # Interface methods
            for method in self._find_methods_in_interface(node):
                symbols.append(Symbol(
                    name=f"{interface_name}.{method.name}",
                    type='method',
                    file=file_path,
                    line=method.line,
                    column=method.column,
                    parent=interface_name
                ))
        
        # 3. Enum declarations
        for node in self._find_nodes(tree, 'enum_declaration'):
            symbols.append(Symbol(
                name=node.child_by_field_name('name').text.decode(),
                type='enum',
                file=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1]
            ))
        
        return symbols
    
    def extract_imports(self, tree, file_path: str) -> List[Import]:
        """Extract import statements."""
        imports = []
        
        for node in self._find_nodes(tree, 'import_declaration'):
            package = self._get_import_path(node)
            imports.append(Import(
                module=package,
                alias=None,
                line=node.start_point[0] + 1
            ))
        
        return imports
```

**What NOT to Extract (Scope):**
- Annotations (compile-time metadata, complex to parse)
- Generics parameters (Java's type erasure makes them complex)
- Inner classes (nested symbols, can add later)

**Test Repo:** Small Java project (10K LOC)

**Success Criteria:**
- ✓ Extract 95%+ of classes, interfaces, methods
- ✓ Extract 90%+ of imports
- ✓ <50ms parse per 1K LOC

---

### 3.5 Multi-Language Integration

```python
class UnifiedParser:
    """Auto-detect language and dispatch to appropriate parser."""
    
    def __init__(self):
        self.parsers = {
            'py': PythonParser(),
            'ts': TypeScriptParser(),
            'go': GoParser(),
            'rs': RustParser(),
            'java': JavaParser(),
        }
    
    def parse_file(self, file_path: str) -> List[Symbol]:
        """Auto-detect language, parse, return symbols."""
        ext = file_path.split('.')[-1]
        
        parser = self.parsers.get(ext)
        if not parser:
            logger.warning(f"Unsupported language: {ext}")
            return []
        
        return parser.parse_file(file_path)
    
    def build_graph(self, repo_path: str) -> GraphBuilder:
        """Build unified graph from multi-language repo."""
        builder = GraphBuilder(repo_path)
        
        for file_path in self._find_source_files(repo_path):
            symbols = self.parse_file(file_path)
            for sym in symbols:
                builder.symbol_index.add(sym)
        
        builder._build_call_graph()  # Handles all languages
        return builder
```

**Test Plan:**

```python
def test_multi_language_repo():
    """Test mixed Python/Go/Rust repo."""
    repo = create_test_repo_with({
        'main.py': 100,
        'utils.go': 50,
        'lib.rs': 50,
    })
    
    parser = UnifiedParser()
    symbols = parser.build_graph(repo).symbol_index.get_all()
    
    # Verify all symbols extracted
    assert len(symbols) >= 180  # 100+50+50 (some may be nested)
    
    # Verify language tagging
    py_symbols = [s for s in symbols if s.file.endswith('.py')]
    go_symbols = [s for s in symbols if s.file.endswith('.go')]
    rs_symbols = [s for s in symbols if s.file.endswith('.rs')]
    
    assert len(py_symbols) > 0
    assert len(go_symbols) > 0
    assert len(rs_symbols) > 0
```

**Success Criteria:**
- ✓ Support 5 languages (Python, TypeScript, Go, Rust, Java)
- ✓ All languages reach ≥90% extraction rate
- ✓ Unified symbol interface (no language-specific quirks exposed)
- ✓ No performance regression vs Phase 1

---

## Feature 4: Automated Agent Scheduling (Weeks 12-14)

**Goal:** Schedule and execute multiple tasks in optimal order, respecting dependencies and conflicts.

### 4.1 Task Dependency Graph

**Input:** List of tasks with symbols they modify/depend on

**Output:** DAG (directed acyclic graph) + execution plan

```python
@dataclass
class Task:
    id: str
    description: str
    target_symbols: List[str]      # Symbols to modify
    dependency_symbols: List[str]  # Symbols we read (inferred from target)
    
@dataclass
class TaskDependency:
    task_a: str
    task_b: str
    type: str  # 'DEPENDS_ON', 'CONFLICTS_WITH', 'SAFE_PARALLEL'
    reason: str

class TaskDAGBuilder:
    """Build task dependency graph."""
    
    def __init__(self, conflict_detector):
        self.conflict_detector = conflict_detector
    
    def build_dag(self, tasks: List[Task]) -> TaskDAG:
        """Create task dependency graph."""
        
        edges = []
        
        for i, task_a in enumerate(tasks):
            for task_b in tasks[i+1:]:
                # Check for conflicts
                conflict = self.conflict_detector.detect(task_a, task_b)
                
                if conflict:
                    edges.append(TaskDependency(
                        task_a=task_a.id,
                        task_b=task_b.id,
                        type='CONFLICTS_WITH',
                        reason=conflict.reason
                    ))
                    # Task A must complete before Task B
                    edges.append(TaskDependency(
                        task_a=task_a.id,
                        task_b=task_b.id,
                        type='DEPENDS_ON',
                        reason='Conflict avoidance'
                    ))
                else:
                    edges.append(TaskDependency(
                        task_a=task_a.id,
                        task_b=task_b.id,
                        type='SAFE_PARALLEL',
                        reason='No conflicts detected'
                    ))
        
        return TaskDAG(tasks=tasks, edges=edges)
    
    def detect_cycles(self, dag: TaskDAG) -> List[List[str]]:
        """Detect circular dependencies."""
        # DFS from each node, check for back edges
        cycles = []
        for cycle in self._find_all_cycles(dag):
            cycles.append(cycle)
        return cycles
```

**Failure Modes:**

| Mode | Cause | Detection | Recovery |
|------|-------|-----------|----------|
| Circular dependency | Task A depends on B, B depends on A | Cycle detection in DAG | Report error, suggest manual ordering |
| Task timeout | Task takes >30s | Timeout handler | Kill task, mark failed, continue |
| Conflicting modifications | Task A modifies X, Task B modifies X | Conflict detector | Serialize (run A then B) |
| Agent crash | Agent process exits unexpectedly | Exit code monitoring | Retry task (max 3 times) |

---

### 4.2 Task Scheduler

```python
class TaskScheduler:
    """Execute tasks in optimal order."""
    
    def __init__(self, conflict_detector, execution_engine):
        self.conflict_detector = conflict_detector
        self.executor = execution_engine
        self.max_parallel = 4  # Configurable
        self.task_timeout = 30  # seconds
    
    def schedule(self, tasks: List[Task]) -> SchedulingPlan:
        """Generate execution plan: which tasks can run in parallel."""
        
        dag = TaskDAGBuilder(self.conflict_detector).build_dag(tasks)
        
        # Detect cycles (fatal)
        cycles = dag.detect_cycles()
        if cycles:
            raise ValueError(f"Circular task dependencies: {cycles}")
        
        # Compute topological sort
        execution_phases = self._compute_execution_phases(dag)
        
        return SchedulingPlan(
            phases=execution_phases,
            total_tasks=len(tasks),
            parallelizable_pairs=self._count_parallelizable_pairs(dag)
        )
    
    def _compute_execution_phases(self, dag: TaskDAG) -> List[List[str]]:
        """Partition tasks into sequential phases.
        
        Each phase contains tasks that can run in parallel.
        Phases must execute sequentially.
        """
        phases = []
        visited = set()
        
        while len(visited) < len(dag.tasks):
            # Find all tasks with no unvisited dependencies
            phase = []
            for task in dag.tasks:
                if task.id in visited:
                    continue
                
                dependencies_met = all(
                    dep.task_a in visited
                    for dep in dag.edges
                    if dep.task_b == task.id and dep.type == 'DEPENDS_ON'
                )
                
                if dependencies_met:
                    phase.append(task.id)
            
            if not phase:
                # Deadlock (shouldn't happen if cycle detection works)
                raise RuntimeError("Deadlock detected in task scheduling")
            
            phases.append(phase)
            visited.update(phase)
        
        return phases
    
    def execute(self, plan: SchedulingPlan) -> ExecutionResult:
        """Execute tasks according to plan."""
        
        results = []
        
        for phase_idx, phase in enumerate(plan.phases):
            logger.info(f"Executing phase {phase_idx + 1}/{len(plan.phases)}: {phase}")
            
            # Execute tasks in phase in parallel (up to max_parallel)
            phase_results = self.executor.execute_parallel(
                phase,
                max_workers=self.max_parallel,
                timeout=self.task_timeout
            )
            
            results.extend(phase_results)
            
            # Check for failures
            failed = [r for r in phase_results if not r.success]
            if failed:
                logger.error(f"Phase {phase_idx + 1} had {len(failed)} failures")
                # Decision: continue or abort? (configurable)
                if self.fail_fast:
                    return ExecutionResult(
                        status='FAILED',
                        completed_tasks=len([r for r in results if r.success]),
                        failed_tasks=failed,
                        results=results
                    )
        
        return ExecutionResult(
            status='SUCCESS',
            completed_tasks=len(results),
            results=results
        )
```

**Success Criteria:**
- ✓ Schedule 1000-task batch in <100ms
- ✓ Detect all cycles and deadlocks
- ✓ Maximize parallelization (minimize phases)
- ✓ 99%+ execution reliability

**Test Plan:**

```python
def test_scheduling_no_conflicts():
    # 10 tasks, no conflicts → can run in parallel
    tasks = [Task(id=f't{i}', target_symbols=[f'sym_{i}']) for i in range(10)]
    
    scheduler = TaskScheduler(NoConflictDetector())
    plan = scheduler.schedule(tasks)
    
    # Should be 1 phase (all parallel)
    assert len(plan.phases) == 1
    assert len(plan.phases[0]) == 10

def test_scheduling_with_conflicts():
    # Task A modifies sym1, Task B reads sym1 → B depends on A
    task_a = Task(id='a', target_symbols=['sym1'])
    task_b = Task(id='b', dependency_symbols=['sym1'])
    
    scheduler = TaskScheduler(ConflictDetector())
    plan = scheduler.schedule([task_a, task_b])
    
    # Should be 2 phases
    assert len(plan.phases) == 2
    assert plan.phases[0] == ['a']
    assert plan.phases[1] == ['b']

def test_scheduling_cycle_detection():
    # Task A depends on B, B depends on A
    task_a = Task(id='a', dependency_symbols=['sym_b'])
    task_b = Task(id='b', dependency_symbols=['sym_a'])
    
    scheduler = TaskScheduler(ConflictDetector())
    
    with pytest.raises(ValueError, match="Circular"):
        scheduler.schedule([task_a, task_b])
```

---

## Risk Mitigation

| Risk | Probability | Severity | Mitigation |
|------|---|---|---|
| Incremental updates corrupt graph | Medium | Critical | Transactional updates + consistency checks post-update |
| Contract extraction misses edge cases | High | Medium | Start with Google-style only, test heavily, fallback to type hints |
| Multi-language parser incomplete | Medium | Low | Accept ≥90% extraction, plan Phase 2.5 improvements |
| Scheduler deadlock | Low | Critical | Cycle detection + timeout handling |
| Performance regression | Medium | Medium | Benchmark each feature, regression tests in CI |
| Agent timeout during execution | Medium | Medium | Timeout handler + retry logic (max 3 retries) |

---

## Timeline & Dependencies

| Week | Feature | Dependency | Effort |
|------|---------|-----------|--------|
| 1-4 | Incremental Updates | Phase 1 ✓ | 4 weeks (Backend) |
| 5-8 | Contract Extraction | Phase 1 ✓ | 4 weeks (ML/Analytics) |
| 9-11 | Multi-Language Parsers | Incremental ✓ | 3 weeks (Backend) |
| 12-14 | Agent Scheduling | Multi-Lang ✓, Contracts ✓ | 3 weeks (Backend) |
| 15-16 | Integration + Buffer | All | 2 weeks (All) |

**Critical Path:** Incremental Updates → Multi-Language → Scheduling

**Total:** 18 weeks (4.5 months)

---

## Resource Allocation

**Team:**
- **1x Backend Engineer (12 weeks):** Incremental updates (4) + Multi-language (3) + Scheduling (3) + integration (2)
- **1x ML/Analytics Engineer (6 weeks):** Contract extraction (4) + integration (2)
- **0.5x DevOps (6 weeks):** Benchmarking, regression tests, monitoring (throughout)

**Infrastructure:**
- Neo4j Cloud: $500/month (indexed, production-grade)
- Redis (optional, for caching): $50/month
- Monitoring (DataDog or Prometheus): $100/month
- CI/CD (GitHub Actions): Included
- **Total: ~$650/month**

---

## Success Metrics

**Phase 2 Exit Criteria (Must All Pass):**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Incremental parse speedup | 10x faster than full parse | Benchmark: 5 successive 10% diffs on 50K LOC repo |
| Contract extraction accuracy | 95% precision, 90% recall | Test suite: 50+ known contracts vs extracted |
| Multi-language coverage | ≥90% per language | Parser tests on language-specific test repos |
| Scheduling time | <100ms for 1000 tasks | Benchmark: generate random DAG, measure schedule() |
| Agent execution reliability | 99%+ task completion | Execute 100-task suite, measure success rate |
| Performance maintained | Phase 1 latency <50ms p99 | Query latency regression tests |
| Graph consistency | 100% post-update | Consistency validation after 1000+ updates |

---

## Next Steps

1. **Approve this specification** (executive review, 1 day)
2. **Prepare development environment** (set up branches, CI, monitoring) (1 day)
3. **Start Feature 1: Incremental Updates** (Week 1, Monday)
4. **Weekly sync:** Review progress, identify blockers, adjust as needed

---

**Prepared by:** Claude Code  
**Date:** April 1, 2026  
**Next Review:** End of Week 4 (Incremental Updates completion)
