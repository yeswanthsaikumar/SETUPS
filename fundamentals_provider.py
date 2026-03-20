#!/usr/bin/env python3
"""Compatibility wrapper for the relocated fundamentals provider module."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_IMPL_PATH = Path(__file__).resolve().parent / "apps" / "python" / "lib" / "fundamentals_provider.py"
_SPEC = spec_from_file_location("fundamentals_provider_impl", _IMPL_PATH)
_MODULE = module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MODULE)

FundamentalsProvider = _MODULE.FundamentalsProvider
format_fundamentals_display = _MODULE.format_fundamentals_display

if __name__ == "__main__":
    _MODULE.__dict__["__name__"] = "__main__"
    exec(_IMPL_PATH.read_text(), _MODULE.__dict__)

