"""
Tree configuration loader
Reads trees_config.json and returns the tree structure
"""

import json
import os


def load_trees_config() -> dict:
    """Load decision tree configuration from JSON"""
    config_path = os.path.join(os.path.dirname(__file__), 'trees_config.json')

    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"trees_config.json not found at {config_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in trees_config.json: {e}")


if __name__ == "__main__":
    config = load_trees_config()
    print(f"✓ Trees config loaded successfully")
    print(f"Trees available: {list(config.keys())}")
