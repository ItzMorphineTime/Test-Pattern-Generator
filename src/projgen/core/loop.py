"""Seamless-loop timing helpers.

A loop of ``N`` frames animates a phase across ``[0, (N-1)/N]``; the hypothetical
frame ``N`` would sit at phase ``1.0``, which is identical to phase ``0.0`` once
wrapped.  Keeping every animated quantity a function of ``frame_index / N`` (with
integer cycle counts) guarantees the exported video loops without a visible seam.
"""

from __future__ import annotations


def phase(frame_index: int, total_frames: int) -> float:
    """Return the loop phase in ``[0, 1)`` for ``frame_index`` of ``total_frames``."""
    if total_frames <= 0:
        return 0.0
    return (frame_index % total_frames) / float(total_frames)
