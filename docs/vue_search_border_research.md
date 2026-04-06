# Vue Search & Border Research - User Workflow Simulation

**Date**: 2026-04-06  
**Task**: Simulate real user workflow testing SMT CLI with Vue project  
**Time Taken**: ~5 minutes  
**Status**: Completed with findings

## Workflow Steps Executed

### Step 1: Navigate to Project and Check SMT Status

**Command**: `cd /c/Users/LENOVO/Desktop/Projects/test_repos/vue && python -m src.smt_cli status`

**Outcome**: Module not found error
- SMT must be run from the save-my-tokens repo root, not from user project directories
- This is a UX issue in the current workflow

### Step 2: SMT Status Check (from save-my-tokens root)

**Command**: `python -m src.smt_cli status`

**Output**:
```
Neo4j:  OK  (http://localhost:7474)
Graph:  9895 nodes, 18684 edges
        Module: 4169
        Function: 4089
        Type: 861
        File: 318
        Interface: 316
        Class: 142
```

**Finding**: Graph is already built and healthy. Currently indexing AI_LEARN project (not Vue).

### Step 3: Semantic Search Attempts

#### Search "border"
**Command**: `python -m src.smt_cli search "border"`

**Output**: 
```
WARNING: SentenceTransformers not installed. Install with: pip install sentence-transformers
WARNING: FAISS index not built. Cannot search.
No results for 'border' (embeddings unavailable)
```

#### Search "input"
**Command**: `python -m src.smt_cli search "input"`

**Output**: Same embeddings unavailable warning

**Finding**: Semantic search requires `sentence-transformers` package. This is a critical dependency that should be installed or included by default.

### Step 4: Direct Database Query (Workaround)

Used Neo4j driver to query symbols containing "border", "input", or "search" patterns.

## Symbols Found

### Components Found in Graph (across projects)

**Input-related Functions**:
- `Input` (Function) - src/components/ui/input.tsx
- `MessageInput` (Function) - src/components/chat/MessageInput.tsx
- `CommandInput` (Function) - src/components/ui/command.tsx

**Input-related Types**:
- `InputHTMLAttributes` (Interface)
- `InputAutoCompleteAttribute` (Type)
- `InputTypeHTMLAttribute` (Type)

**Search-related Functions**:
- `search` (Function) - src/embeddings/embedding_service.py
- `cmd_search` (Function) - src/smt_cli.py
- `_fallback_search` (Function) - src/embeddings/embedding_service.py
- `search_by_prefix` (Function) - src/parsers/symbol_index.py

**Note**: Results mixed from multiple projects (AI_LEARN, save-my-tokens) due to shared Neo4j database.

## Key Findings & Observations

### Workflow Issues Discovered

1. **Directory Isolation Problem**: SMT CLI requires running from save-my-tokens repo root
   - User expects to run `python -m src.smt_cli` from their project directory
   - This fails silently with "module not found"
   - **Fix**: Documentation or wrapper script needed

2. **Missing Dependency**: Semantic search non-functional without sentence-transformers
   - CLI succeeds but search returns no results
   - Warning logged but not clear to user
   - **Fix**: Add to requirements.txt or install as part of setup

3. **Multi-Project Database**: All projects share same Neo4j database
   - Graph status doesn't indicate which project is indexed
   - No project isolation at database level
   - **Fix**: Add database name to status output

### Available SMT Commands

```bash
python -m src.smt_cli build              # Build/rebuild graph
python -m src.smt_cli build --check      # Check graph status
python -m src.smt_cli status             # Health check
python -m src.smt_cli search <query>     # Semantic search (requires embeddings)
python -m src.smt_cli context <symbol>   # Get symbol definition & callers
python -m src.smt_cli callers <symbol>   # Find who calls symbol
python -m src.smt_cli diff [range]       # Sync graph from commits
```

## Recommendations for Improved User Experience

1. **Install sentence-transformers as required dependency**
   - Add to pyproject.toml
   - Run `pip install sentence-transformers` during setup

2. **Allow SMT to work from user project directories**
   - Detect project root automatically
   - Or provide wrapper script in user PATH
   - Add validation/help if run from wrong location

3. **Improve graph status visibility**
   - Show which project/branch is indexed
   - Show if embeddings are available
   - Show embeddings model status

4. **Better error handling for missing embeddings**
   - Don't silently return empty results
   - Offer inline installation command
   - Suggest `context` command as workaround

## Summary

The SMT CLI workflow has a working graph database with good node coverage (9,895 nodes). However, the semantic search feature—which is key to discovering symbols like "border" in UI components—requires the sentence-transformers dependency that wasn't installed. The user experience could be significantly improved by addressing directory isolation and dependency visibility issues.

**Overall Assessment**: Core functionality works but needs UX polish for real user workflows.
