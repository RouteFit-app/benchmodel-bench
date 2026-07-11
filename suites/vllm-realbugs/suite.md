# Suite: vllm-realbugs (real regressions)

**Status:** `authored, runs pending` — extends the AI-framework-CVE track to
**vLLM**, the most-installed LLM inference server (76k★). Reverses **CVE-2025-62164
(High, CVSS 8.8)**, the `prompt_embeds` deserialization RCE. No synthetic bugs. The
find was verified to match current `main` exactly once and the reversal compiles
and reproduces the buggy state. Groups under the **AI Frameworks** tab.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | embed_utils.py · safe_load_prompt_embeds | CVE-2025-62164 (PR #27204, fixed 0.11.1) | high | removes `with torch.sparse.check_sparse_tensor_invariants():` around the user-tensor `torch.load` + `to_dense()`, reopening an out-of-bounds write / RCE on attacker-controlled sparse tensors |

## Why this one is hard

This is the most deceptive deserialization bug on the board. The load uses
`torch.load(..., weights_only=True)` — the textbook "safe `torch.load`" pattern —
and that line is **unchanged**. What the regression strips is the
`torch.sparse.check_sparse_tensor_invariants()` wrapper that the fix added,
because PyTorch 2.8 turned off sparse-tensor integrity checks by default, so a
crafted sparse tensor slips past bounds checks and triggers an OOB write in
`to_dense()`. A reviewer who pattern-matches on `weights_only=True` concludes
"this is safe" and moves on. The catch requires knowing the sparse-tensor caveat,
and the removed comment ("prevent out-of-bounds writes from maliciously crafted
tensors") is the fair tell for a reviewer who reads what protection was deleted.

## Method

The reversal removes the comment + `with` line and de-indents the body 4 spaces,
restoring the exact pre-fix path. `check_sparse_tensor_invariants` no longer
appears in the file after the patch. Verified find-once against `main`; compiles.

## Running (from `benchmark/`)

```
# 0. clone vLLM (huge; blobless + sparse keeps it light)
git clone --filter=blob:none --sparse https://github.com/vllm-project/vllm.git vllm-repo
git -C vllm-repo sparse-checkout set vllm/renderers

# 1. fresh buggy branch off clean main, then inject (expect 1 applied block)
git -C vllm-repo checkout -b benchmark/real-regression
python apply_bugs.py vllm-repo --bug-index suites/vllm-realbugs/bug_index.json
git -C vllm-repo add -A && git -C vllm-repo commit -m "benchmark vllm real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = AI Frameworks)
python runner.py vllm-repo --bug-index suites/vllm-realbugs/bug_index.json \
    --results-dir results-vllm/ --project-id <ai-frameworks-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-vllm/ \
    --bug-index suites/vllm-realbugs/bug_index.json --out-dir results-vllm/scored/
python publish_leaderboard.py --scoreboard results-vllm/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `main` drifted on this block, ping me and
I'll re-anchor.
