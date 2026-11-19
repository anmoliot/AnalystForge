"""Linux syscall policy for an initialized, compute-only strategy process."""

import errno
import importlib
from collections.abc import Callable


def prepare_strategy_filter() -> Callable[[], None]:
    seccomp = importlib.import_module("pyseccomp")
    policy = seccomp.SyscallFilter(defaction=seccomp.ERRNO(errno.EPERM))
    policy.set_attr(seccomp.Attr.CTL_TSYNC, 1)
    # Inputs and the fixed output buffer are already in memory. No file descriptors
    # are needed, including for returning the result to the parent.
    for syscall in (
        "brk",
        "munmap",
        "mremap",
        "mprotect",
        "madvise",
        "futex",
        "sched_yield",
        "getpid",
        "gettid",
        "clock_gettime",
        "gettimeofday",
        "getrandom",
        "rt_sigaction",
        "rt_sigprocmask",
        "rt_sigreturn",
        "sigaltstack",
        "exit",
        "exit_group",
    ):
        policy.add_rule(seccomp.ALLOW, syscall)
    anonymous = importlib.import_module("mmap").MAP_ANONYMOUS
    policy.add_rule(seccomp.ALLOW, "mmap", seccomp.Arg(3, seccomp.MASKED_EQ, anonymous, anonymous))

    def install() -> None:
        policy.load()

    return install
