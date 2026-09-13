"""Streamlit helpers: SI number_input with live US customary caption.

Dimensional / force / stress / moment / line-load inputs are whole numbers
(integer widgets). Exceptions kept as decimals: dimensionless ratios (x/L),
K factor, modular ratio n override, and ASCE load factors.
"""

from __future__ import annotations

from typing import Callable, Optional, Union

import streamlit as st


def si_number_input(
    label: str,
    min_value: float,
    max_value: float,
    value: float,
    step: Optional[float] = None,
    *,
    key: str,
    dual: Callable[[float], str],
    help: Optional[str] = None,
    format: Optional[str] = None,
    disabled: bool = False,
) -> float:
    """number_input in SI units with a live dual-unit caption underneath.

    Prefer :func:`si_int_input` for dimensional / force / stress quantities.
    """
    kwargs = {
        "min_value": min_value,
        "max_value": max_value,
        "value": value,
        "key": key,
        "disabled": disabled,
    }
    if step is not None:
        kwargs["step"] = step
    if help is not None:
        kwargs["help"] = help
    if format is not None:
        kwargs["format"] = format
    v = st.number_input(label, **kwargs)
    st.caption(dual(float(v)))
    return float(v)


def si_int_input(
    label: str,
    min_value: int,
    max_value: int,
    value: int,
    step: int = 1,
    *,
    key: str,
    dual: Optional[Callable[[Union[int, float]], str]] = None,
    help: Optional[str] = None,
) -> int:
    """Integer SI number_input (step=1, format=%d) with optional dual US caption."""
    v = st.number_input(
        label,
        min_value=int(min_value),
        max_value=int(max_value),
        value=int(value),
        step=int(step),
        format="%d",
        key=key,
        help=help,
    )
    if dual is not None:
        st.caption(dual(int(v)))
    return int(v)


# Backwards-compatible alias
si_number_input_int = si_int_input
