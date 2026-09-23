from tools.spug_tools import _clean

RAW_OUTPUT = (
    "\r\n\x1b[36m### Executing ...\x1b[0m\r\n"
    "\x1b[?2004l  PID COMMAND         %CPU\r\n"
    "  344 stress-ng        100\r\n"
    "\r\n\x1b[32m** 执行结束，总耗时：0.5秒 **\x1b[0m"
)


def test_strips_ansi_and_spug_decoration():
    assert _clean(RAW_OUTPUT) == "  PID COMMAND         %CPU\n  344 stress-ng        100"


def test_plain_output_is_unchanged():
    assert _clean("load average: 0.1, 0.2, 0.3") == "load average: 0.1, 0.2, 0.3"
