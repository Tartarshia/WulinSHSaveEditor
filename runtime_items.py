"""Validated, read-only fallback for reading books missing from ModEditor exports."""
from functools import lru_cache
from pathlib import Path
import re
import struct


def marker(tag: int, name: str) -> bytes:
    return bytes((tag, 1)) + struct.pack("<i", len(name)) + name.encode("utf-16-le")


def read_string(data: bytes, offset: int) -> tuple[str, int]:
    if offset + 5 > len(data): raise ValueError("Truncated string")
    encoding, size = data[offset], struct.unpack_from("<i", data, offset + 1)[0]
    if encoding not in (0, 1) or not 0 <= size <= 100_000: raise ValueError("Unsupported string")
    end = offset + 5 + size * (2 if encoding else 1)
    if end > len(data): raise ValueError("Truncated string payload")
    return data[offset + 5:end].decode("utf-16-le" if encoding else "latin1"), end


def string_list(data: bytes, field: str) -> list[str]:
    start = data.index(marker(1, field)) + len(marker(1, field))
    # ConsumeEffect contains a nested refNames array; do not stop at that field.
    tail = data[start:]
    if field == "ConsumeEffect": tail = tail[:tail.index(marker(39, "ConsumeExp"))]
    result = []
    for match in re.finditer(re.escape(b"\x28\x01"), tail):
        value, _ = read_string(tail, match.start() + 1)
        result.append(value)
    return result


def read_item_records(raw: bytes) -> dict[int, dict]:
    uid = marker(23, "Uid")
    starts = list(re.finditer(re.escape(uid), raw))
    result = {}
    for index, match in enumerate(starts):
        block = raw[match.start():starts[index + 1].start() if index + 1 < len(starts) else len(raw)]
        try:
            item_id = struct.unpack_from("<i", block, len(uid))[0]
            offset = len(uid) + 4
            if block[offset:offset + len(marker(39, "UName"))] != marker(39, "UName"): continue
            name, _ = read_string(block, offset + len(marker(39, "UName")))
            def field(tag, key): return block.index(marker(tag, key)) + len(marker(tag, key))
            rarity = struct.unpack_from("<i", block, field(23, "Rarity"))[0]
            type_id = struct.unpack_from("<q", block, field(29, "Type"))[0]
            stackable = block[field(43, "IsStackable")]
            if item_id <= 0 or not name or rarity not in range(4) or stackable not in (0, 1): continue
            record = dict(name=name, rarity=rarity, type_id=type_id, stackable=bool(stackable),
                          tags=string_list(block, "FavTags"), effects=string_list(block, "ConsumeEffect"))
            if item_id in result: raise ValueError("Duplicate runtime item ID")
            result[item_id] = record
        except (ValueError, IndexError, struct.error, UnicodeError):
            continue
    return result


def read_integer_effects(raw: bytes, names: set[str]) -> dict[str, list[str]]:
    """Decode only verified one-int effects; never reuse a same-name legacy ID."""
    name_marker = marker(39, "UName")
    starts = list(re.finditer(re.escape(name_marker), raw))
    result = {}
    for index, match in enumerate(starts):
        try:
            name, _ = read_string(raw, match.end())
            if name not in names: continue
            block = raw[match.start():starts[index + 1].start() if index + 1 < len(starts) else len(raw)]
            block = block[block.index(marker(1, "InstantEffect")):]
            effects = []
            for key_match in re.finditer(re.escape(marker(39, "key")), block):
                key, end = read_string(block, key_match.end())
                values = marker(1, "values")
                if block[end:end + len(values)] != values: raise ValueError("Unsupported effect values")
                pos = end + len(values)
                if block[pos] != 48 or block[pos + 9] != 6: raise ValueError("Unsupported effect array")
                if struct.unpack_from("<q", block, pos + 10)[0] != 1 or block[pos + 18] != 24:
                    raise ValueError("Not a single integer effect")
                value = struct.unpack_from("<i", block, pos + 19)[0]
                effects.append(f"{key}|{value}")
            if effects: result[name] = effects
        except (ValueError, IndexError, struct.error, UnicodeError):
            continue
    return result


def load_reading_books(game_root: Path, known_catalog: dict) -> dict[int, dict]:
    bundle = game_root / "Wulin_Data/StreamingAssets/aa/StandaloneWindows64/config_assets_all.bundle"
    if not bundle.is_file(): return {}
    reading_ids = frozenset(uid for uid, (_, category) in known_catalog.items() if category == "消耗品")
    return _load_reading_books(str(bundle), bundle.stat().st_mtime_ns, frozenset(known_catalog), reading_ids)


@lru_cache(maxsize=2)
def _load_reading_books(bundle: str, modified: int, known_ids: frozenset[int], reading_ids: frozenset[int]) -> dict[int, dict]:
    import UnityPy
    env = UnityPy.load(bundle)
    data = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour": continue
        name = obj.peek_name()
        if name in {"ItemData", "BuffData"}: data[name] = obj.get_raw_data()
    if "ItemData" not in data: return {}
    records = read_item_records(data["ItemData"])
    known_types = {row["type_id"] for uid, row in records.items() if uid in reading_ids and "典籍" in row["tags"]}
    books = {uid: row for uid, row in records.items() if uid not in known_ids and row["type_id"] in known_types
             and "典籍" in row["tags"] and row["stackable"]}
    effects = read_integer_effects(data.get("BuffData", b""), {name for row in books.values() for name in row["effects"]})
    for row in books.values():
        row["direct_effects"] = [effect for name in row["effects"] for effect in effects.get(name, [])]
    return books
