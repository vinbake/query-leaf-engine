"""
Trees Config Loader — The Query Leaf
Loads trees_config.json from the same directory.
"""

import json
import os


def load_trees_config() -> dict:
    """Load and return the trees configuration JSON."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trees_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_tree_names(config: dict) -> list:
    """Return list of available tree names."""
    return list(config.keys())


def get_node(config: dict, tree: str, node_id: str) -> dict:
    """Return a specific node from a tree, or raise KeyError."""
    tree_data = config.get(tree.lower())
    if not tree_data:
        raise KeyError(f"Unknown tree: {tree}")
    node = tree_data.get(node_id)
    if not node:
        raise KeyError(f"Unknown node: {node_id} in tree: {tree}")
    return node
