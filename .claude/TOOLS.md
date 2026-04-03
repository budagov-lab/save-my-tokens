# SMT CLI — Quick Reference

Use `smt` commands via Bash instead of reading/grepping source files.

---

## Decision Table

| You want to...                          | Run this                              |
|-----------------------------------------|---------------------------------------|
| Understand what a function does         | `smt context <symbol>`                |
| See what a function depends on          | `smt context <symbol> --depth 2`      |
| See who calls a function                | `smt callers <symbol>`                |
| Find code by meaning / topic            | `smt search "description"`            |
| Check graph health                      | `smt status`                          |
| Build graph from source                 | `smt build`                           |
| Wipe and rebuild                        | `smt build --clear`                   |
| Sync graph after a commit               | `smt diff HEAD~1..HEAD`               |
| Start Neo4j                             | `smt docker up`                       |

---

## Session Start Checklist

```bash
smt status          # node count > 100? Graph is ready.
smt build           # if empty — build from src/
smt diff            # if stale — sync with recent commits
```

## Hard Restart (graph broken / corrupted)

```bash
smt build --clear   # wipes all nodes/edges and rebuilds from source
smt status          # confirm node count > 100
```
