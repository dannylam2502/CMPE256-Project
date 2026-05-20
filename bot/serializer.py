"""
Maps poke-env's `AbstractBattle` to the JSON wire format the Svelte UI expects.

The shape must match `src/lib/types.ts` in the UI. If you change the UI's
types, mirror the change here.

Defensive everywhere — the bot keeps running even if a field is missing or
shaped differently across poke-env versions.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from poke_env.battle.abstract_battle import AbstractBattle
from poke_env.battle.field import Field
from poke_env.battle.move import Move
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.pokemon import Pokemon
from poke_env.battle.pokemon_type import PokemonType
from poke_env.battle.side_condition import SideCondition
from poke_env.battle.status import Status
from poke_env.battle.weather import Weather

from recommender import ScoredAction


# ---------------------------------------------------------------------------
# Enum maps (poke-env → UI string codes)
# ---------------------------------------------------------------------------

_STATUS_MAP = {
    Status.BRN: "brn",
    Status.PAR: "par",
    Status.SLP: "slp",
    Status.FRZ: "frz",
    Status.PSN: "psn",
    Status.TOX: "tox",
    Status.FNT: "fnt",
}

_CATEGORY_MAP = {
    MoveCategory.PHYSICAL: "physical",
    MoveCategory.SPECIAL: "special",
    MoveCategory.STATUS: "status",
}

_WEATHER_MAP = {
    Weather.SUNNYDAY: "sun",
    Weather.RAINDANCE: "rain",
    Weather.SANDSTORM: "sand",
    Weather.SNOW: "snow",
    Weather.HAIL: "hail",
    Weather.DESOLATELAND: "sun",
    Weather.PRIMORDIALSEA: "rain",
}

_TERRAIN_MAP = {
    Field.ELECTRIC_TERRAIN: "electric",
    Field.GRASSY_TERRAIN: "grassy",
    Field.MISTY_TERRAIN: "misty",
    Field.PSYCHIC_TERRAIN: "psychic",
}

_HAZARDS = {
    SideCondition.STEALTH_ROCK: "stealthrock",
    SideCondition.SPIKES: "spikes",
    SideCondition.TOXIC_SPIKES: "toxicspikes",
    SideCondition.STICKY_WEB: "stickyweb",
}

_SCREENS = {
    SideCondition.REFLECT: "reflect",
    SideCondition.LIGHT_SCREEN: "lightscreen",
    SideCondition.AURORA_VEIL: "auroraveil",
}


def _type(t: Optional[PokemonType]) -> Optional[str]:
    return t.name.lower() if t else None


def _species_display(species: str) -> str:
    return "-".join(part.capitalize() for part in species.split("-"))


def _move_name(m: Move) -> str:
    try:
        return m.entry["name"]
    except (KeyError, AttributeError, TypeError):
        return m.id.replace("_", " ").title()


def _serialize_move(m: Move) -> dict[str, Any]:
    acc = m.accuracy
    if isinstance(acc, bool) or acc is None:
        accuracy = 100
    elif acc <= 1:
        accuracy = int(round(acc * 100))
    else:
        accuracy = int(acc)

    # `m.priority` raises KeyError when the dex entry has no `priority` key,
    # which is the case for the majority of moves (priority 0 is implicit).
    try:
        priority = m.priority
    except KeyError:
        priority = 0

    return {
        "id": m.id,
        "name": _move_name(m),
        "type": _type(m.type),
        "category": _CATEGORY_MAP.get(m.category, "status"),
        "basePower": m.base_power or 0,
        "accuracy": accuracy,
        "pp": {"current": m.current_pp, "max": m.max_pp},
        "priority": priority,
    }


def _serialize_pokemon(p: Pokemon, own_side: bool) -> dict[str, Any]:
    types = [_type(t) for t in (p.types or []) if t]

    if own_side:
        cur = p.current_hp or 0
        mx = p.max_hp or 1
        frac = (cur / mx) if mx else 0.0
    else:
        # Opponent: only the fraction is reliable.
        frac = p.current_hp_fraction if p.current_hp_fraction is not None else 1.0
        cur = int(round(frac * 100))
        mx = 100

    moves_dict = p.moves or {}
    moves = [_serialize_move(m) for m in moves_dict.values()]

    status_key = "fnt" if p.fainted else _STATUS_MAP.get(p.status, "healthy") if p.status else "healthy"

    return {
        "species": _species_display(p.species),
        "level": p.level or 100,
        "hp": {"current": cur, "max": mx, "fraction": frac},
        "status": status_key,
        "types": types,
        "ability": p.ability,
        "item": p.item,
        "teraType": _type(getattr(p, "tera_type", None)),
        "terastallized": getattr(p, "terastallized", False),
        "moves": moves,
        "isActive": p.active,
        "fainted": p.fainted,
        "boosts": dict(p.boosts) if (p.boosts and p.active) else None,
        "revealed": True,
    }


def _serialize_side(battle: AbstractBattle, perspective: str) -> dict:
    if perspective == "player":
        team_dict = battle.team or {}
        active = battle.active_pokemon
        name = getattr(battle, "player_username", None) or "You"
    else:
        team_dict = battle.opponent_team or {}
        active = battle.opponent_active_pokemon
        name = getattr(battle, "opponent_username", None) or "Opponent"

    own = perspective == "player"
    team = [_serialize_pokemon(p, own) for p in team_dict.values()]
    return {
        "name": name,
        "team": team,
        "active": _serialize_pokemon(active, own) if active else None,
    }


def _serialize_side_conditions(conds: dict) -> dict:
    hazards: list[str] = []
    screens: list[str] = []
    spikes_layers = 0
    tspikes_layers = 0

    for sc, val in (conds or {}).items():
        if sc in _HAZARDS:
            hazards.append(_HAZARDS[sc])
            if sc == SideCondition.SPIKES:
                spikes_layers = val if isinstance(val, int) else 1
            elif sc == SideCondition.TOXIC_SPIKES:
                tspikes_layers = val if isinstance(val, int) else 1
        elif sc in _SCREENS:
            screens.append(_SCREENS[sc])

    out: dict[str, Any] = {"hazards": hazards, "screens": screens}
    if spikes_layers:
        out["spikesLayers"] = spikes_layers
    if tspikes_layers:
        out["toxicSpikesLayers"] = tspikes_layers
    return out


def _serialize_field(battle: AbstractBattle) -> dict:
    weather = None
    try:
        if battle.weather:
            w = next(iter(battle.weather.keys()))
            weather = _WEATHER_MAP.get(w)
    except (AttributeError, StopIteration):
        pass

    terrain = None
    trick_room = False
    try:
        for f in (battle.fields or {}):
            if f in _TERRAIN_MAP:
                terrain = _TERRAIN_MAP[f]
            if f == Field.TRICK_ROOM:
                trick_room = True
    except AttributeError:
        pass

    return {
        "weather": weather,
        "terrain": terrain,
        "trickRoom": trick_room,
        "player": _serialize_side_conditions(getattr(battle, "side_conditions", None) or {}),
        "opponent": _serialize_side_conditions(getattr(battle, "opponent_side_conditions", None) or {}),
    }


def _serialize_action(action) -> dict:
    if isinstance(action, Move):
        return {"type": "move", "move": _serialize_move(action)}
    # else: Pokemon (switch)
    return {"type": "switch", "pokemon": _serialize_pokemon(action, own_side=True)}


def _serialize_recommendation(s: ScoredAction) -> dict:
    return {
        "action": _serialize_action(s.action),
        "score": max(0.0, min(1.0, float(s.score))),
        "reasoning": s.reasoning or None,
    }


def serialize_battle(battle: AbstractBattle, scored: list[ScoredAction]) -> dict:
    """Build a `BattleUpdate` dict matching `src/lib/types.ts` in the UI."""
    available = [_serialize_action(m) for m in battle.available_moves]
    available.extend(_serialize_action(p) for p in battle.available_switches)

    state: dict[str, Any] = {
        "turn": battle.turn,
        "format": battle.format or "unknown",
        "player": _serialize_side(battle, "player"),
        "opponent": _serialize_side(battle, "opponent"),
        "field": _serialize_field(battle),
        "availableActions": available,
        "finished": battle.finished,
    }
    if battle.finished:
        if battle.won is True:
            state["winner"] = "player"
        elif battle.won is False:
            state["winner"] = "opponent"
        else:
            state["winner"] = "tie"

    return {
        "state": state,
        "recommendations": [_serialize_recommendation(s) for s in scored],
        "timestamp": int(time.time() * 1000),
    }
