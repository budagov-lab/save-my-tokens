"""Re-export shim — analysis commands split into focused sub-modules."""

from src.cli.code_intel import (
    cmd_breaking_changes,
    cmd_changes,
    cmd_layer,
    cmd_unused,
)
from src.cli.graph_analysis import (
    cmd_bottleneck,
    cmd_complexity,
    cmd_cycles,
    cmd_hot,
    cmd_modules,
)
from src.cli.navigation import (
    cmd_list,
    cmd_path,
    cmd_scope,
)

__all__ = [
    "cmd_bottleneck",
    "cmd_breaking_changes",
    "cmd_changes",
    "cmd_complexity",
    "cmd_cycles",
    "cmd_hot",
    "cmd_layer",
    "cmd_list",
    "cmd_modules",
    "cmd_path",
    "cmd_scope",
    "cmd_unused",
]
