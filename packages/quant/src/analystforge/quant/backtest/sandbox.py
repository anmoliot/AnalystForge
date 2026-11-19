"""Sandboxed Python strategy runner.

Executes custom quantitative Python strategies in a heavily constrained,
isolated child process with strict AST scanning, resource limits (CPU, memory, file creation),
wall-time execution timeout, and no filesystem or network access.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import json
import multiprocessing
import os
from collections.abc import Mapping
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

from .isolation import prepare_strategy_filter

resource: ModuleType | None
try:
    resource = importlib.import_module("resource")
except ImportError:
    resource = None


class SandboxSecurityError(PermissionError):
    """Raised when custom strategy code attempts forbidden operations or sandbox escapes."""


class SandboxUnavailableError(RuntimeError):
    """Raised when sandbox execution is attempted on an unsupported platform (e.g. Windows)."""


class _ResultBuffer:
    """A bounded, shared byte array. The child cannot supply a pickle to the parent."""

    def __init__(self, rows: int) -> None:
        self.buffer = multiprocessing.RawArray("c", 4096 + rows * 24)

    def put(self, result: dict[str, Any]) -> None:
        encoded = json.dumps(result, separators=(",", ":")).encode()
        if len(encoded) >= len(self.buffer):
            encoded = b'{"success":false,"error":"Strategy output exceeded the buffer limit."}'
        self.buffer.value = encoded

    def empty(self) -> bool:
        return bool(self.buffer[0] == b"\x00")

    def get(self) -> dict[str, Any]:
        result = json.loads(self.buffer.value)
        if not isinstance(result, dict):
            raise ValueError("Invalid strategy response.")
        return result


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


def _safe_import(
    name: str,
    globals: Any = None,
    locals: Any = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
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
                    raise SandboxSecurityError(
                        f"Forbidden import: '{alias.name}'. Only numpy, pandas, and math are allowed."
                    )
        elif isinstance(node, ast.ImportFrom):
            mod_name = (node.module or "").split(".")[0]
            if mod_name not in ALLOWED_MODULES:
                raise SandboxSecurityError(f"Forbidden import from: '{node.module}'.")

        # 2. Call names
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_NAMES:
                    raise SandboxSecurityError(f"Forbidden call: '{node.func.id}'.")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRIBUTES:
                raise SandboxSecurityError(f"Forbidden attribute access: '{node.func.attr}'.")

        # 3. Direct identifier names
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES or node.id in FORBIDDEN_ATTRIBUTES:
                raise SandboxSecurityError(f"Forbidden identifier: '{node.id}'.")

        # 4. Attribute access
        elif isinstance(node, ast.Attribute) and (
            node.attr in FORBIDDEN_ATTRIBUTES
            or (node.attr.startswith("__") and node.attr.endswith("__"))
        ):
            raise SandboxSecurityError(f"Forbidden dunder attribute access: '{node.attr}'.")


def _worker_execute(
    source_code: str,
    df: pd.DataFrame,
    result_buffer: _ResultBuffer,
    cpu_limit_secs: int = 5,
    mem_limit_mb: int = 512,
) -> None:
    """Target function executed in the isolated child process."""
    try:
        if resource is None:
            raise SandboxUnavailableError("Unix resource limits are unavailable.")
        try:
            install_filter = prepare_strategy_filter()
        except (ImportError, OSError, RuntimeError, ValueError, AttributeError) as exc:
            raise SandboxUnavailableError(
                "Required Linux syscall isolation is unavailable."
            ) from exc
        try:
            mem_bytes = mem_limit_mb * 1024 * 1024
            # NumPy reserves virtual address space beyond the private data segment.
            address_limit = max(mem_bytes, 2048 * 1024 * 1024)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_secs, cpu_limit_secs + 1))
            resource.setrlimit(resource.RLIMIT_AS, (address_limit, address_limit))
            resource.setrlimit(resource.RLIMIT_DATA, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        except (AttributeError, OSError, ValueError) as exc:
            raise SandboxUnavailableError(
                "Required Unix resource limits could not be installed."
            ) from exc

        # Apply the filter only after Python, dependencies and shared memory are initialized.
        try:
            install_filter()
        except (ImportError, OSError, RuntimeError, ValueError, AttributeError) as exc:
            raise SandboxUnavailableError(
                "Required Linux syscall isolation could not be installed."
            ) from exc

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
        exec(compiled, exec_globals, exec_locals)  # noqa: S102 - isolated strategy subprocess

        fn = exec_locals.get("generate_signals") or exec_globals.get("generate_signals")
        if not callable(fn):
            raise ValueError("Strategy must define a callable named 'generate_signals(df)'")

        signals = fn(df)

        if isinstance(signals, (pd.Series, np.ndarray, list, tuple)):
            raw_arr = np.asarray(signals, dtype=int).tolist()
            result_buffer.put({"success": True, "signals": raw_arr})
        else:
            result_buffer.put(
                {
                    "success": False,
                    "error": f"generate_signals returned unsupported type {type(signals).__name__}, expected Series or array",
                }
            )
    except SandboxUnavailableError as exc:
        result_buffer.put({"success": False, "unavailable": True, "error": str(exc)})
    except Exception as exc:
        result_buffer.put({"success": False, "error": f"{type(exc).__name__}: {exc}"})


def _strategy_child(
    source: str, df: pd.DataFrame, result: _ResultBuffer, cpu: int, memory: int
) -> None:
    os.environ.clear()
    # Load the approved top-level scientific modules before filesystem access is closed.
    importlib.import_module("scipy")
    _worker_execute(source, df, result, cpu, memory)


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

    # Check for platform capability (resource module and Unix subprocess controls)
    if resource is None:
        raise SandboxUnavailableError(
            "Sandboxed strategy execution requires Unix resource limits (RLIMIT_CPU, RLIMIT_AS, RLIMIT_DATA, RLIMIT_FSIZE) "
            "and is not supported on Windows."
        )

    # Step 2: Spawn isolated subprocess
    ctx = multiprocessing.get_context("spawn")
    result_buffer = _ResultBuffer(len(df))

    proc = ctx.Process(
        target=_strategy_child,
        args=(source_code, df, result_buffer, cpu_limit_secs, mem_limit_mb),
    )
    proc.start()

    proc.join(timeout=wall_time_timeout)

    if proc.is_alive():
        proc.kill()
        proc.join()
        raise TimeoutError(
            f"Strategy execution exceeded wall-time limit of {wall_time_timeout} seconds."
        )

    if result_buffer.empty():
        exit_code = proc.exitcode
        raise RuntimeError(
            f"Strategy worker process terminated unexpectedly with exit code {exit_code}."
        )

    res = result_buffer.get()
    if not res.get("success"):
        err_msg = res.get("error", "Unknown error in strategy execution")
        if res.get("unavailable"):
            raise SandboxUnavailableError(err_msg)
        raise RuntimeError(err_msg)

    signals: list[int] = res["signals"]
    if not isinstance(signals, list) or any(type(value) is not int for value in signals):
        raise ValueError("Strategy must return a list of integer signals.")
    if len(signals) != len(df):
        raise ValueError(
            f"Strategy returned {len(signals)} signals, but price dataframe has {len(df)} rows."
        )

    return signals
