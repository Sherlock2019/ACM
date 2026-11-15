"""Real-project mode (Phase 1): test ACFM on a local folder or a public GitHub repository.

ACFM works on a separate copy in the ACFM test workspace (never the user's folder), inspects it read-only,
saves testable predictions before anything runs, and runs only the exact human-approved patch and argv
commands: once before the patch (baseline) and once after. A workspace is NOT a sandbox.
"""
