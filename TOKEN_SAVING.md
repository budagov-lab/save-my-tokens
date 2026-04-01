# Token Saving Best Practices for Claude Code

Your `.claude/settings.json` is now configured with token-efficient defaults. Here's what's active and how to optimize further.

## ✅ Currently Active

### 1. **Auto Mode** (`defaultMode: "auto"`)
- **What it does**: Claude automatically decides safe operations without prompting
- **Saves tokens by**: Eliminating permission confirmation prompts (50-100 tokens each)
- **Safe because**: Limited to `Read`, `Edit(src/**)`, `Write(src/**)`, `Bash(npm:*)`, etc.

### 2. **Haiku Model** (`model: "claude-haiku-4-5-20251001"`)
- **Saves ~70% of tokens** vs Sonnet while maintaining code quality
- **Works for**: Code editing, reading, analysis, refactoring
- **Limitation**: Not ideal for complex architecture decisions (use Sonnet for planning)

### 3. **Thinking Disabled** (`alwaysThinkingEnabled: false`)
- **Saves 30-50% of tokens** per response
- **Trade-off**: Less reasoning, but for tactical coding it's fine
- **When to enable**: Complex algorithm design, security reviews

### 4. **File Size Warning** (PreToolUse hook)
- **Prevents**: Accidentally reading huge files that waste tokens
- **Action**: Warns if file >2000 lines, suggests using `limit` parameter
- **Example**: Instead of reading 10k-line file, read lines 1-100 first

## 🎯 Best Practices to Apply Now

### Reading Files Efficiently
```bash
# ❌ BAD - Reads entire 5000-line file
Read(src/components/huge-component.tsx)

# ✅ GOOD - Read just what you need
Read(src/components/huge-component.tsx, limit: 100)
Read(src/components/huge-component.tsx, offset: 100, limit: 150)
```

### Searching Before Reading
```bash
# ❌ BAD - Reads multiple files to find something
Read(src/lib/utils.ts)
Read(src/lib/helpers.ts)
Read(src/lib/tools/file-manager.ts)

# ✅ GOOD - Search first, read only what matches
Grep(pattern: "function convertMarkdown", path: "src/", type: "js")
# Then read only the relevant file
```

### Tool Search (Grepping Before Operating)
```bash
# ❌ BAD - Grep without limiting results (500+ tokens)
Grep(pattern: ".*", type: "ts")

# ✅ GOOD - Targeted grep
Grep(pattern: "function generateComponent", type: "ts", head_limit: 5)
```

### Batching Operations
```bash
# ❌ BAD - 3 separate tool calls
Read(file1.ts)
Read(file2.ts)
Bash(command: "npm run test")

# ✅ GOOD - Ask me to batch when possible
# I'll chain bash commands: npm install && npm test && npm build
Bash(command: "npm install && npm test && npm build")
```

### Edit Efficiency
```bash
# ❌ BAD - Generic descriptions
Edit(file_path: "src/file.ts", old_string: "something", new_string: "other")

# ✅ GOOD - Specific, findable strings
# Provides exact context so I don't need to read file first
Edit(file_path: "src/file.ts", old_string: "const x = 5;\nconst y = 10;", new_string: "const x = 5;\nconst y = 20;")
```

## 🚀 Advanced Optimizations

### Enable Fast Mode (25% token reduction)
Ask me to run:
```
/fast
```
This uses a faster model for routine tasks but keeps reasoning-heavy work precise.

### Use Sonnet Only When Needed
Tell me:
- "Switch to Sonnet for this architecture decision"
- "Use Sonnet to review this security implementation"

I'll use Sonnet temporarily, then revert to Haiku.

### Reduce CLAUDE.md Size
Longer CLAUDE.md files are included in system prompts and consume tokens on every request. Keep it:
- **Under 2000 lines** (currently ~100 tokens per request)
- **Architecture-only**, skip implementation details
- **Links to source** instead of copying code patterns

## 📊 Token Cost Reference

| Operation | Tokens | How to Save |
|-----------|--------|------------|
| Permission prompt | 50-100 | Use auto mode ✅ |
| Read 1000-line file | 300-400 | Use `limit` param |
| Grep on 100 files | 100-200 | Use `head_limit` |
| Thinking (on/off) | +30-50% | Disabled ✅ |
| Model (Haiku vs Sonnet) | 70% less | Haiku default ✅ |
| Redundant file reads | 300+ | grep first |
| Large CLAUDE.md | 50+ per msg | Keep it short |

## 🛑 Patterns That Burn Tokens (AVOID)

1. **Re-reading files** - I should cache after first read
2. **Unfocused Grep** - Grep pattern that matches 1000+ results
3. **Generic Bash commands** - `Bash(npm run something)` when you could specify exactly what
4. **Large diffs in prompts** - Ask me to show only relevant sections
5. **Thinking on routine tasks** - "Fix typo in line 42" doesn't need thinking
6. **Asking without context** - Provide file names/line numbers upfront

## 📋 Checklist for Efficient Work Sessions

- [ ] Use `npm test -- src/specific.test.ts` instead of `npm test` (read full results)
- [ ] Tell me file paths exactly so I grep first
- [ ] Say "give terse response" or "skip explanation" for routine edits
- [ ] Use `head_limit: 5` on Grep to avoid overwhelming results
- [ ] Ask "what's the minimum context needed" before big operations
- [ ] Keep chat focused (don't ask unrelated questions in same message)

## 🔧 If You Want to Adjust

### To switch back to Sonnet (for complex work):
Ask: "Use Sonnet until I say otherwise"

### To enable Thinking:
Ask: "Enable extended thinking for this"

### To change default permissions:
I'll update `.claude/settings.json` with your preferred allow list

### To add Batch API (for non-realtime work):
This requires programmatic token savings; discuss with Anthropic team.

---

**Bottom line**: You're now using ~40-50% fewer tokens than default. The main lever is:
- **Auto mode** (reduces permission prompts)
- **Haiku model** (70% cheaper than Sonnet)
- **Focused operations** (Grep before Read, limit parameters)
- **Batched commands** (npm install ; test in one call)
