"""Shared YAML mapping reader for research and world configuration files."""
from pathlib import Path

import yaml


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ValueError("configuration keys must be strings")
        if key in result:
            raise ValueError(f"duplicate configuration key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_yaml_mapping(path: str | Path) -> dict:
    """Read UTF-8 YAML (or JSON), rejecting duplicate keys and non-mapping roots."""
    try:
        value = yaml.load(Path(path).read_text(encoding="utf-8-sig"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML configuration: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("configuration root must be a mapping")
    return value
