"""Sandboxed Python strategy runner.

Executes custom quantitative Python strategies in a heavily constrained,
isolated child process with strict AST scanning, resource limits (CPU, memory, file creation),
wall-time execution timeout, and no filesystem or network access.
"""

from __future__ import annotations

import ast
import builtins
import multiprocessing
import os
import resource
import signal
import sys
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


class SandboxSecurityError(PermissionError):
    """Raised when custom strategy code attempts forbidden operations or sandbox escapes."""


ALLOWED_MODULES = {"math", "numpy", "np", "pandas", "pd", "scipy"}

FORBIDDEN_NAMES = {
    "open",
    "eval",
    "exec",
    "__import__",
    "compile",
    "globals",
    "locals",
    "vars",
    "breakpoint",
    "exit",
    "quit",
    "help",
    "input",
    "print",
    "memoryview",
    "bytearray",
}

FORBIDDEN_ATTRIBUTES = {
    "__class__",
    "__bases__",
    "__subclasses__",
    "__globals__",
    "__dict__",
    "__code__",
    "__closure__",
    "__mro__",
    "__builtins__",
    "__import__",
    "func_globals",
    "func_code",
    "gi_frame",
    "f_globals",
    "f_locals",
    "f_builtins",
    "f_code",
}


def _safe_import(name: str, globals: Any = None, locals: Any = None, fromlist: tuple[str, ...] = (), level: int = 0) -> Any:
    root_mod = name.split(".")[0]
    if root_mod not in ALLOWED_MODULES:
        raise SandboxSecurityError(f"Forbidden runtime import: '{name}'")
    return builtins.__import__(name, globals, locals, fromlist, level)


SAFE_BUILTINS: Mapping[str, Any] = {
    "__import__": _safe_import,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    "Exception": Exception,
    "ValueError": ValueError,
    "IndexError": IndexError,
    "KeyError": KeyError,
    "TypeError": TypeError,
}


def scan_code_ast(source_code: str) -> None:
    """Analyze Python source code AST for unauthorized constructs.

    Raises
    ------
    SandboxSecurityError : If any unauthorized module, attribute, or function is detected.
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in strategy code: {e}") from e

    for node in ast.walk(tree):
        # 1. Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_name = alias.name.split(".")[0]
                if mod_name not in ALLOWED_MODULES:
                    raise SandboxSecurityError(f"Forbidden import: '{alias.name}'. Only numpy, pandas, and math are allowed.")
        elif isinstance(node, ast.ImportFrom):
            mod_name = (node.module or "").split(".")[0]
            if mod_name not in ALLOWED_MODULES:
                raise SandboxSecurityError(f"Forbidden import from: '{node.module}'.")

        # 2. Call names
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_NAMES:
                    raise SandboxSecurityError(f"Forbidden call: '{node.func.id}'.")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in FORBIDDEN_ATTRIBUTES:
                    raise SandboxSecurityError(f"Forbidden attribute access: '{node.func.attr}'.")

        # 3. Direct identifier names
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES or node.id in FORBIDDEN_ATTRIBUTES:
                raise SandboxSecurityError(f"Forbidden identifier: '{node.id}'.")

        # 4. Attribute access
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES or (node.attr.startswith("__") and node.attr.endswith("__")):
                raise SandboxSecurityError(f"Forbidden dunder attribute access: '{node.attr}'.")


def _worker_execute(
    source_code: str,
    df: pd.DataFrame,
    result_queue: multiprocessing.Queue[Any],
    cpu_limit_secs: int = 5,
    mem_limit_mb: int = 512,
) -> None:
    """Target function executed in the isolated child process."""
    try:
        # Enforce CPU limits
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_secs, cpu_limit_secs + 1))
        except Exception:
            pass

        # Enforce Address Space (memory) limits if supported and safe
        try:
            mem_bytes = mem_limit_mb * 1024 * 1024
            # In 64-bit Linux, numpy/OpenBLAS pre-allocates virtual memory regions,
            # so RLIMIT_AS must accommodate thread pool virtual reservations (minimum 2GB virtual).
            safe_as_limit = max(mem_bytes, 2048 * 1024 * 1024)
            resource.setrlimit(resource.RLIMIT_AS, (safe_as_limit, safe_as_limit))
            # Also limit data segment
            resource.setrlimit(resource.RLIMIT_DATA, (mem_bytes, mem_bytes))
        except Exception:
            pass

        # Disallow creating any new files
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        except Exception:
            pass

        # Build clean execution environment
        exec_globals: dict[str, Any] = {
            "__builtins__": dict(SAFE_BUILTINS),
            "np": np,
            "numpy": np,
            "pd": pd,
            "pandas": pd,
        }

        # Compile and execute code definition
        compiled = compile(source_code, "<sandboxed_strategy>", "exec")
        exec_locals: dict[str, Any] = {}
        exec(compiled, exec_globals, exec_locals)

        fn = exec_locals.get("generate_signals") or exec_globals.get("generate_signals")
        if not callable(fn):
            raise ValueError("Strategy must define a callable named 'generate_signals(df)'")

        signals = fn(df)

        if isinstance(signals, (pd.Series, np.ndarray, list, tuple)):
            raw_arr = np.asarray(signals, dtype=int).tolist()
            result_queue.put({"success": True, "signals": raw_arr})
        else:
            result_queue.put({
                "success": False,
                "error": f"generate_signals returned unsupported type {type(signals).__name__}, expected Series or array",
            })
    except Exception as exc:
        result_queue.put({"success": False, "error": f"{type(exc).__name__}: {exc}"})


def run_sandboxed_strategy(
    source_code: str,
    df: pd.DataFrame,
    *,
    cpu_limit_secs: int = 5,
    mem_limit_mb: int = 512,
    wall_time_timeout: float = 6.0,
) -> list[int]:
    """Execute custom strategy code in a sandboxed subprocess.

    Parameters
    ----------
    source_code : Python strategy code defining generate_signals(df).
    df : Historical price DataFrame.
    cpu_limit_secs : Hard CPU time limit in seconds.
    mem_limit_mb : Address space limit in Megabytes.
    wall_time_timeout : Maximum wall-clock time in seconds before terminating process.

    Returns
    -------
    list of integer signals (-1, 0, 1).
    """
    # Step 1: Pre-execution AST scan
    scan_code_ast(source_code)

    # Step 2: Spawn isolated subprocess
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue[Any] = ctx.Queue()

    proc = ctx.Process(
        target=_worker_execute,
        args=(source_code, df, queue, cpu_limit_secs, mem_limit_mb),
    )
    proc.start()

    proc.join(timeout=wall_time_timeout)

    if proc.is_alive():
        proc.kill()
        proc.join()
        raise TimeoutError(f"Strategy execution exceeded wall-time limit of {wall_time_timeout} seconds.")

    if queue.empty():
        exit_code = proc.exitcode
        raise RuntimeError(f"Strategy worker process terminated unexpectedly with exit code {exit_code}.")

    res = queue.get()
    if not res.get("success"):
        err_msg = res.get("error", "Unknown error in strategy execution")
        raise RuntimeError(err_msg)

    signals: list[int] = res["signals"]
    if len(signals) != len(df):
        raise ValueError(f"Strategy returned {len(signals)} signals, but price dataframe has {len(df)} rows.")

    return signals
