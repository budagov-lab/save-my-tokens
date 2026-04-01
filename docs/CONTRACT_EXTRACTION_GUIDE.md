# Feature 2: Contract Extraction & Validation Implementation Guide

**Status:** Complete  
**Implemented:** April 1, 2026  
**Module:** `src/contracts/`  

## Overview

Contract extraction automatically detects breaking changes in function signatures and behavior. This enables agents to safely parallelize tasks by ensuring changes don't violate existing caller assumptions.

### Key Capability
Compare two versions of a function and identify:
- **Breaking changes** that will fail existing callers (HIGH severity)
- **Non-breaking changes** that are safe (e.g., added optional parameters)
- **Compatibility score** (0-1) indicating how safe the change is

## Architecture

### Core Components

#### 1. Contract Models (`src/contracts/contract_models.py`)

**FunctionContract:** Represents a complete contract for a function.

```python
@dataclass
class FunctionContract:
    symbol: Symbol                         # Function identity
    signature: SignatureInfo              # Parameters, return type
    docstring: Optional[str]              # Full docstring text
    type_hints: Dict[str, str]            # param -> type mappings
    preconditions: List[str]              # Requirements from Args section
    postconditions: List[str]             # Guarantees from Returns section
    version: str                          # Contract version
```

**SignatureInfo:** Function signature with type information.

```python
@dataclass
class SignatureInfo:
    parameters: List[ParameterInfo]       # All parameters
    return_type: Optional[str]            # Return type (if annotated)
    raises: List[str]                     # Exception types from Raises section
```

**ParameterInfo:** Individual parameter details.

```python
@dataclass
class ParameterInfo:
    name: str
    type_hint: Optional[str]              # From annotation
    is_optional: bool                     # Has default value?
    default_value: Optional[str]          # Default if optional
```

#### 2. ContractExtractor (`src/contracts/extractor.py`)

Parses Python source code to extract contracts from functions.

**Key Methods:**
- `extract_function_contract(symbol) -> FunctionContract`: Extract contract from a function
- `_extract_signature(func_node) -> SignatureInfo`: Parse function signature
- `_extract_type_hints(func_node) -> Dict[str, str]`: Extract type annotations
- `_extract_preconditions(docstring) -> List[str]`: Parse requirements from docstring

**Docstring Support:**
- **Format:** Google-style docstrings (most common in Python)
- **Sections:** Args, Returns, Raises, Note
- **Fallback:** If no docstring, uses type hints only

**Example:**
```python
from src.contracts import ContractExtractor
from src.parsers.symbol import Symbol

source = """
def process(data: str, validate: bool = True) -> dict:
    '''Process data with optional validation.
    
    Args:
        data: Input data string
        validate: Whether to validate (default: True)
    
    Returns:
        dict: Processed result
    
    Raises:
        ValueError: If data is invalid
    '''
    ...
"""

extractor = ContractExtractor(source)
symbol = Symbol(name="process", type="function", file="api.py", line=1, column=0)
contract = extractor.extract_function_contract(symbol)

print(contract.signature.parameters)  # [ParameterInfo(name='data', ...), ...]
print(contract.signature.raises)      # ['ValueError']
```

#### 3. BreakingChangeDetector (`src/contracts/breaking_change_detector.py`)

Compares contracts to identify breaking changes.

**Key Methods:**
- `detect_breaking_changes(old, new) -> ContractComparison`: Compare contracts
- `_is_type_narrowed(old_type, new_type) -> bool`: Heuristic type narrowing check

**Breaking Change Types:**
- `PARAMETER_REMOVED` (HIGH) - Parameter deleted from signature
- `PARAMETER_REQUIRED_NOW` (HIGH) - Optional parameter became required
- `PARAMETER_TYPE_CHANGED` (HIGH) - Type narrowed/changed
- `RETURN_TYPE_NARROWED` (MEDIUM) - Return type became more specific
- `PRECONDITION_ADDED` (MEDIUM) - New requirement added
- `EXCEPTION_ADDED` (LOW) - New exception may be raised
- `EXCEPTION_REMOVED` (not breaking) - Fewer exceptions raised

**Example:**
```python
from src.contracts import BreakingChangeDetector

detector = BreakingChangeDetector()
comparison = detector.detect_breaking_changes(old_contract, new_contract)

print(comparison.is_compatible)        # bool
print(comparison.compatibility_score)  # 0.0 to 1.0
print(comparison.breaking_changes)     # List[BreakingChange]
print(comparison.non_breaking_changes) # List[str]
```

## API Endpoints

### 1. Extract Contract
```
POST /api/contracts/extract
Content-Type: application/json

{
  "symbol_name": "process_data",
  "file_path": "src/api.py",
  "source_code": "def process_data(data: str) -> dict: ..."
}

Response (200):
{
  "symbol_name": "process_data",
  "file": "src/api.py",
  "signature": {
    "parameters": [
      {
        "name": "data",
        "type_hint": "str",
        "is_optional": false
      }
    ],
    "return_type": "dict",
    "raises": []
  },
  "docstring": "Process data...",
  "preconditions": [],
  "postconditions": [],
  "version": "1.0"
}
```

### 2. Compare Contracts
```
POST /api/contracts/compare
Content-Type: application/json

{
  "old_source": "def func(a: int, b: int) -> int: ...",
  "new_source": "def func(a: int) -> int: ...",
  "symbol_name": "func"
}

Response (200):
{
  "symbol": "func",
  "old_version": "1.0",
  "new_version": "1.1",
  "is_compatible": false,
  "compatibility_score": 0.7,
  "breaking_changes": [
    {
      "type": "PARAMETER_REMOVED",
      "severity": "HIGH",
      "impact": "Parameters removed: b. All callers passing these parameters will fail.",
      "affected_elements": ["b"]
    }
  ],
  "non_breaking_changes": []
}
```

## Usage Scenarios

### Scenario 1: Pre-Change Validation

Before deploying a code change, validate it won't break callers:

```python
# Old code
old_source = """
def calculate(value: int, precision: int = 2) -> float:
    '''Calculate with optional precision.
    
    Args:
        value: Input value
        precision: Decimal places (default: 2)
    
    Returns:
        Calculated result as float
    '''
    return round(value / 10, precision)
"""

# New code
new_source = """
def calculate(value: int, precision: int) -> float:  # Now required!
    '''Calculate with required precision.
    
    Args:
        value: Input value
        precision: Decimal places (required)
    
    Returns:
        Calculated result as float
    '''
    return round(value / 10, precision)
"""

# Compare
detector = BreakingChangeDetector()
old_extractor = ContractExtractor(old_source)
new_extractor = ContractExtractor(new_source)

old = old_extractor.extract_function_contract(symbol)
new = new_extractor.extract_function_contract(symbol)

comparison = detector.detect_breaking_changes(old, new)

if not comparison.is_compatible:
    print(f"⚠️ Breaking changes detected!")
    for change in comparison.breaking_changes:
        print(f"  {change.type}: {change.impact}")
else:
    print(f"✓ Safe to deploy (compatibility: {comparison.compatibility_score:.0%})")
```

### Scenario 2: Parallel Task Validation

Agent scheduler uses contracts to determine if tasks can run in parallel:

```python
# Task 1: Modify function signature
# Task 2: Update all callers

# Check if changes conflict
task1_changes = extract_contracts_from_changes(task1_diff)
task2_changes = extract_contracts_from_changes(task2_diff)

detector = BreakingChangeDetector()

for func, new_contract in task1_changes.items():
    old_contract = get_current_contract(func)
    comparison = detector.detect_breaking_changes(old_contract, new_contract)
    
    if comparison.breaking_changes:
        # Task 1 must run before Task 2
        mark_dependency(task1, task2)
    else:
        # Safe to run in parallel
        allow_parallel(task1, task2)
```

## Performance Characteristics

### Target Metrics

| Operation | Target | Notes |
|-----------|--------|-------|
| Extract contract (simple function) | <10ms | AST parsing + docstring extraction |
| Detect breaking changes | <5ms | Type comparison + signature analysis |
| End-to-end comparison | <20ms | Extract + detect |

### Measured Performance (April 1, 2026)

Based on test runs:
- Contract extraction: ~1-3ms for typical functions
- Breaking change detection: <1ms for comparison
- End-to-end: ~5-10ms

## Docstring Format Support

### Phase 2: Google-Style (Implemented)

```python
def function(param1: str, param2: int = 5) -> bool:
    """Brief description.

    Longer description if needed.

    Args:
        param1: Description of param1
        param2: Description of param2 (default: 5)

    Returns:
        Description of return value

    Raises:
        ValueError: When inputs invalid
        TypeError: When type mismatch
    """
```

### Not Yet Supported (Phase 2.5+)
- NumPy style docstrings
- Sphinx style docstrings
- RST docstrings

## Type Hint Support

### Supported (Python 3.11+)

```python
# Basic types
def func(a: int, b: str) -> bool: ...

# Optional/Union
def func(a: Optional[int]) -> Union[str, int]: ...

# Generics
def func(a: List[str]) -> Dict[str, int]: ...

# Custom types
class MyType: ...
def func(a: MyType) -> MyType: ...
```

### Heuristic Type Narrowing

Simple heuristics for detecting type narrowing:
- `Any` → specific type = narrowing
- `Union[A, B]` → A = narrowing
- `Optional[T]` → T = narrowing

Note: Not a complete type system; just heuristics for common patterns.

## Testing

### Unit Tests
- ContractExtractor: Parsing various function signatures
- BreakingChangeDetector: Detecting each breaking change type
- Type narrowing heuristics

### Integration Tests
- End-to-end: Extract → Compare → Validate
- Multiple parameter changes
- Complex type changes

### Location
`tests/integration/test_contract_extraction.py`

**Run Tests:**
```bash
pytest tests/integration/test_contract_extraction.py -v
```

**Coverage:** 80.65% (BreakingChangeDetector), 82.71% (ContractExtractor)

## Known Limitations

### Phase 2 Scope
1. **Python only:** TypeScript support in Phase 2.5
2. **Google docstrings only:** Other formats in Phase 2.5
3. **Simple type narrowing:** Heuristic-based, not complete type analysis
4. **No semantic analysis:** Can't detect logic changes, only signature/docstring

### Edge Cases
1. **Renamed parameters:** Detected as removed + added (not recognized as rename)
2. **Type aliases:** Not fully resolved (e.g., `MyInt = int`)
3. **Generic types:** Simple pattern matching only
4. **Complex unions:** May miss narrowing in complex Union types

## Future Enhancements

### Phase 2.5
- TypeScript contract extraction
- NumPy/Sphinx docstring support
- Better type narrowing detection

### Phase 3
- Behavioral contract extraction (from assertions/examples)
- Semantic change detection (code diff analysis)
- Contract versioning and history

## Integration with Phase 2 Features

### With Incremental Updates (Feature 1)
- When delta applies, extract new contracts
- Compare against old contracts
- If breaking changes, flag for approval

### With Multi-Language Support (Feature 3)
- Contract extraction for Go, Rust, Java
- Different docstring formats per language

### With Agent Scheduling (Feature 4)
- Pre-validate task compatibility
- Prevent parallel execution of breaking changes

## Troubleshooting

### Issue: "Function not found in source"
**Cause:** Extractor couldn't locate the function AST node  
**Fix:** Verify function name and class name match exactly

### Issue: "Contract extraction failed"
**Cause:** Syntax error in source code or unsupported pattern  
**Fix:** Check source code is valid Python; review error message

### Issue: "Type narrowing not detected"
**Cause:** Heuristic doesn't cover this type pattern  
**Fix:** This is a known limitation; use breaking_changes[0].impact for manual review

## Related Documentation
- [PHASE_2_SPECIFICATION.md](../PHASE_2_SPECIFICATION.md) - Feature 2 detailed spec
- [API Reference](./API_REFERENCE.md) - Full endpoint documentation
- [INCREMENTAL_UPDATES_GUIDE.md](./INCREMENTAL_UPDATES_GUIDE.md) - Feature 1 integration
