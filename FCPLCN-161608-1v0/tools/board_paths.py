"""Filesystem identities; Upper/Lower remain stable logical and BOM keys."""
from pathlib import Path

BOARD_NAMES = {
    "Upper": "FCPLCN-CPU-08-1v0",
    "Lower": "FCPLCN-RLY-1616-1v0",
}


def board_name(side):
    return BOARD_NAMES[side]


def board_dir(root, side):
    return Path(root) / board_name(side)


def board_file(root, side, suffix):
    return board_dir(root, side) / (board_name(side) + suffix)


def scene_name(scene):
    return BOARD_NAMES.get(scene, scene)
