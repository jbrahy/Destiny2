from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    GOD_ROLL = "god_roll"
    GOOD = "good"
    MASTERWORK = "masterwork"
    NO_DATA = "no_data"
    DISMANTLE = "dismantle"


@dataclass
class OwnedWeapon:
    instance_id: str
    item_hash: int
    name: str
    weapon_type: str
    element: str
    is_masterworked: bool
    is_random_roll: bool
    perks: frozenset[int]
    location: str
    power: int = 0
    ammo_type: str = ""
    frame: str = ""
    perk_names: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    icon: str = ""
    equipped: bool = False
    is_exotic: bool = False
    bucket_hash: int = 0
    is_locked: bool = False
    is_crafted: bool = False
    # Trait perks this weapon can be shaped into, one list per column. Populated
    # only for crafted weapons -- resolving it for every weapon would cost a
    # manifest walk per item for data that cannot be acted on.
    trait_pool: list[list[str]] = field(default_factory=list)


@dataclass
class ArmorPiece:
    instance_id: str
    item_hash: int
    name: str
    slot: str
    class_name: str
    power: int
    is_exotic: bool
    is_masterworked: bool
    stats: dict[str, int]
    location: str
    icon: str = ""
    equipped: bool = False
    set_name: str = ""
    set_hash: int | None = None
