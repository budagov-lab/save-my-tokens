# SYT Phase 1 MVP - Comprehensive Testing Plan

**Objective:** Validate Graph API Foundation against success criteria  
**Scope:** 3 test repositories, 2 independent evaluation methods  
**Timeline:** Single execution run  
**Metrics:** Token efficiency, success rate, accuracy, latency

---

## Test Repositories

### Repository 1: Small (10K LOC)
**Purpose:** Fast baseline validation  
**Characteristics:**
- ~10,000 lines of Python code
- ~50 Python files
- ~200 functions/classes
- Simple dependency structure
- Expected parse time: <2s

**Content Types:**
- Utility functions
- Data processing
- Config management
- Unit tests

### Repository 2: Medium (50K LOC)
**Purpose:** Primary evaluation target  
**Characteristics:**
- ~50,000 lines of Python + TypeScript
- ~150 files (mix of languages)
- ~800 functions/classes
- Complex dependencies
- Expected parse time: <5s

**Content Types:**
- Web API endpoints
- Data models
- Middleware
- Client libraries
- Service layers

### Repository 3: Large (200K LOC - Optional)
**Purpose:** Scalability stress test  
**Characteristics:**
- ~200,000 lines of mixed languages
- ~500 files
- ~3000+ functions/classes
- Very complex dependencies
- Expected parse time: <20s

**Content Types:**
- Multiple services
- Legacy code
- Cross-service dependencies
- Complex type hierarchies

---

## Test Tasks (Exam-Style)

Each repository will be given identical task categories to test different scenarios.

### Task Set A: Simple Modifications (3 tasks)

**Task A1: Update Single Function**
```json
{
  "id": "A1",
  "description": "Modify the main entry point to add new parameter",
  "target_symbols": ["main", "parse_arguments"],
  "expected_difficulty": "easy",
  "success_criteria": [
    "Identify both target symbols",
    "Find all callers of main()",
    "Locate argument parsing logic"
  ]
}
```

**Task A2: Update Data Structure**
```json
{
  "id": "A2",
  "description": "Add new field to primary data model",
  "target_symbols": ["DataModel", "serialize"],
  "expected_difficulty": "easy",
  "success_criteria": [
    "Locate class definition",
    "Find all usages in codebase",
    "Identify serialization method"
  ]
}
```

**Task A3: Add Logging**
```json
{
  "id": "A3",
  "description": "Add logging to critical path",
  "target_symbols": ["process", "execute"],
  "expected_difficulty": "easy",
  "success_criteria": [
    "Find target functions",
    "Identify control flow",
    "Locate where to insert logging"
  ]
}
```

### Task Set B: Dependency-Heavy Modifications (3 tasks)

**Task B1: Update API Endpoint**
```json
{
  "id": "B1",
  "description": "Modify endpoint to use new service",
  "target_symbols": ["get_user_endpoint", "UserService"],
  "expected_difficulty": "medium",
  "success_criteria": [
    "Find endpoint definition",
    "Locate service dependency",
    "Identify all service methods used",
    "Detect breaking changes"
  ]
}
```

**Task B2: Refactor Shared Utility**
```json
{
  "id": "B2",
  "description": "Refactor utility function that's used widely",
  "target_symbols": ["validate_input", "common.utils"],
  "expected_difficulty": "medium",
  "success_criteria": [
    "Locate utility definition",
    "Find all call sites (5+)",
    "Identify parameter usage patterns",
    "Detect backward compatibility risks"
  ]
}
```

**Task B3: Update Core Algorithm**
```json
{
  "id": "B3",
  "description": "Optimize sorting algorithm in data processor",
  "target_symbols": ["sort_data", "compare_func", "DataProcessor"],
  "expected_difficulty": "medium",
  "success_criteria": [
    "Locate algorithm implementation",
    "Find all callers",
    "Identify performance-sensitive paths",
    "Check for side effects"
  ]
}
```

### Task Set C: Parallel/Conflict Testing (3 tasks)

**Task C1 & C2: Parallel Modifications (Non-conflicting)**
```json
{
  "id": "C1",
  "description": "Modify UserService",
  "target_symbols": ["UserService.get_user"],
  "parallel_with": "C2"
}
```
```json
{
  "id": "C2",
  "description": "Modify PaymentService",
  "target_symbols": ["PaymentService.process_payment"],
  "parallel_with": "C1"
}
```

**Task C3: Conflicting Modification**
```json
{
  "id": "C3",
  "description": "Modify shared configuration",
  "target_symbols": ["config.settings", "load_config"],
  "expected_conflict": "with C1 and C2",
  "success_criteria": [
    "Correctly identify conflict",
    "Detect shared dependency",
    "Recommend sequential execution"
  ]
}
```

### Task Set D: Search & Discovery (3 tasks)

**Task D1: Find Similar Patterns**
```json
{
  "id": "D1",
  "description": "Find all error handling patterns",
  "search_query": "error handling exception",
  "expected_difficulty": "medium",
  "success_criteria": [
    "Return top-5 matching functions",
    "Identify try-except patterns",
    "Find error recovery logic"
  ]
}
```

**Task D2: Semantic Search**
```json
{
  "id": "D2",
  "description": "Find all authentication-related code",
  "search_query": "user authentication login credentials",
  "expected_difficulty": "medium",
  "success_criteria": [
    "Rank by relevance",
    "Include auth functions, classes",
    "Find related utilities"
  ]
}
```

**Task D3: Complex Dependency Search**
```json
{
  "id": "D3",
  "description": "Find all code that touches database",
  "search_query": "database connection query transaction",
  "expected_difficulty": "hard",
  "success_criteria": [
    "Return all DB-related code",
    "Rank by criticality",
    "Group by service/module"
  ]
}
```

---

## Evaluation Methods

### Method 1: Graph API Agent
**Approach:** Use QueryService to retrieve minimal context  
**Expected Behavior:**
- Queries `/api/context` for symbol info
- Gets `/api/subgraph` for dependencies
- Uses `/api/search` for discovery
- Validates with `/api/validate-conflicts`
- Measures: token usage, latency, accuracy

**Metrics Collected:**
- Tokens used per task
- API call count
- Response latency
- Context completeness
- Conflict detection accuracy

### Method 2: Baseline Agent
**Approach:** Use raw file access (entire files)  
**Expected Behavior:**
- Reads complete source files
- Text search for dependencies
- No structured analysis
- Measures: token usage, latency, accuracy

**Metrics Collected:**
- Total bytes retrieved
- Tokens used (estimated)
- Search accuracy
- False positive rate
- Context bloat

---

## Success Metrics

### Primary Metrics

| Metric | Target | Method | How to Measure |
|--------|--------|--------|---|
| Parser Coverage | 98%+ | Both | Extract symbols, compare to manual count |
| Token Efficiency | 15%+ improvement | Graph API vs Baseline | avg_tokens_graph_api / avg_tokens_baseline |
| Query Latency | <500ms p99 | Graph API | measure time per API call |
| Conflict Detection | >90% recall | Both | validate against known conflicts |
| Search Precision | >80% top-5 | Graph API | check relevance of results |

### Secondary Metrics

| Metric | Target | How to Measure |
|--------|--------|---|
| Success Rate | >90% | % tasks completed correctly |
| Context Accuracy | >95% | % correct symbols identified |
| False Positives | <5% | % incorrect findings |
| Execution Time | <2s per task | measure end-to-end time |
| Scalability | <5s for 50K LOC | measure on medium repo |

---

## Testing Procedure

### Phase 1: Setup (Automated)
1. Initialize Symbol Index for each repository
2. Build Neo4j graph for each repository
3. Prepare 12 tasks (4 sets × 3 repos)
4. Initialize both agents

### Phase 2: Execution (Independent)
**For Each Repository:**

1. **Graph API Evaluation**
   - Execute tasks A1-D3 sequentially
   - Record: tokens used, latency, accuracy
   - Collect context sizes
   - Measure API response times

2. **Baseline Evaluation**
   - Execute same tasks A1-D3 sequentially
   - Record: bytes retrieved, tokens used, accuracy
   - Measure file read times
   - Track search effectiveness

3. **Conflict Testing**
   - Execute C1, C2 in parallel (should succeed)
   - Execute C3 (should detect conflict)
   - Verify conflict detection accuracy

### Phase 3: Analysis (Automated)
1. Aggregate metrics across all repositories
2. Calculate improvements (Graph API vs Baseline)
3. Generate comparison report
4. Validate against success criteria
5. Make Go/No-Go recommendation

---

## Expected Outcomes

### Best Case Scenario
```
Graph API Agent:
  ✅ 98%+ parser coverage
  ✅ <100ms query latency
  ✅ 20%+ token reduction vs baseline
  ✅ >95% task success rate
  ✅ >85% conflict detection accuracy
  
Baseline Agent:
  ✅ 98%+ parser coverage (file reading)
  ✅ 50-200ms file read latency
  ✅ Higher token usage (full files)
  ✅ >95% task success rate
  ✅ Limited conflict detection
  
Comparison:
  ✅ Graph API 15-30% more token efficient
  ✅ Graph API 2-3x faster for context retrieval
  ✅ Equivalent success rates
  ✅ Graph API better parallelization
  
Decision: ✅ GO
```

### Acceptable Scenario
```
Graph API Agent:
  ✅ >95% parser coverage
  ✅ <200ms query latency
  ✅ 12-15% token reduction
  ✅ >85% task success rate
  ✅ >80% conflict detection

Comparison:
  ✅ Graph API meets 15% token target
  ✅ Similar success rates
  
Decision: ✅ GO
```

### Failure Scenario
```
Results:
  ❌ Parser coverage <95%
  ❌ Query latency >500ms
  ❌ Token efficiency <10%
  ❌ Success rate <80%
  ❌ Conflict detection <70%

Decision: ❌ NO-GO (Phase 1.5 extension)
```

---

## Test Execution Blueprint

### Repository 1 (10K LOC)
```
Time: 2-5 minutes
Tasks: All 12 (A1-D3)
Graph API Agent:
  - Parse repo: <2s
  - Execute 12 tasks: ~30s
  - Collect metrics: ~10s
Baseline Agent:
  - Read files: <3s
  - Execute 12 tasks: ~30s
  - Collect metrics: ~10s
Total: ~5 minutes per method
```

### Repository 2 (50K LOC)
```
Time: 10-15 minutes
Tasks: All 12
Graph API Agent:
  - Parse repo: <5s
  - Execute 12 tasks: ~1m
  - Collect metrics: ~20s
Baseline Agent:
  - Read files: <10s
  - Execute 12 tasks: ~1.5m
  - Collect metrics: ~20s
Total: ~12 minutes per method
```

### Repository 3 (200K LOC - Optional)
```
Time: 30-40 minutes
Tasks: All 12
Graph API Agent:
  - Parse repo: <20s
  - Execute 12 tasks: ~3m
  - Collect metrics: ~30s
Baseline Agent:
  - Read files: <30s
  - Execute 12 tasks: ~5m
  - Collect metrics: ~30s
Total: ~30 minutes per method
```

**Total Testing Time: 40-60 minutes (with all repos)**

---

## Output & Reporting

### Metrics Output
- Success rate per task
- Token usage per method
- Latency measurements
- Conflict detection accuracy
- Search precision/recall

### Comparison Report
- Graph API vs Baseline
- Token efficiency improvement %
- Success rate delta
- Latency comparison
- Scalability analysis

### Go/No-Go Decision
Based on:
1. All parser coverage ≥95%
2. Token efficiency ≥15%
3. Success rate ≥85%
4. Conflict detection ≥90%
5. Query latency <500ms

---

## Notes

- Tasks are designed to be independent of repo size
- Same tasks on all repos enables comparison
- Metrics are quantitative and measurable
- No human judgment needed for pass/fail
- Results feed directly into decision matrix
