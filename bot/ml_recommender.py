"""
ML recommender: loads the trained PokemonTransformerAI and scores actions
from a live poke-env Battle.

THIS IS THE FILE TO TWEAK if predictions look random — every categorical
field (species, move, status, item, weather, conditions) goes through a
hash. The hash is deterministic but case-sensitive: "Earthquake" and
"earthquake" produce *different* embedding slots. Whatever string format
your training data used, this file MUST match.

The defaults below assume:
  - pokemon name : display form, e.g. "Tyranitar"
  - move name    : display form, e.g. "Earthquake"
  - status       : poke-env short code, e.g. "brn", "par"
  - item         : poke-env id, lowercase, e.g. "leftovers"
  - weather      : poke-env enum name, uppercase, e.g. "SUNNYDAY"
  - conditions   : comma-separated poke-env enum names

If your training data used a different convention, tweak the `_NAME`,
`_MOVE_NAME`, `_STATUS`, `_ITEM`, `_WEATHER`, `_CONDITIONS` helpers below.

Output mapping (logits → actions):
  indices 0..3 → active mon's moves SORTED ALPHABETICALLY BY DISPLAY NAME
  indices 4..8 → bench mons SORTED ALPHABETICALLY BY DISPLAY NAME
This must match the dataset's `sorted(..., key=lambda x: x.get('name', ''))`.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import torch
import torch.nn.functional as F

from poke_env.battle.abstract_battle import AbstractBattle
from poke_env.battle.move import Move
from poke_env.battle.pokemon import Pokemon

from model import HASH_LIMITS, PokemonTransformerAI
from recommender import ScoredAction

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# String-format adapters. EDIT THESE if predictions look like noise.
# ---------------------------------------------------------------------------

def _NAME(mon: Pokemon) -> str:
    """Pokémon name as the model expects it."""
    # poke-env's species is lowercase ('tyranitar'); convert to "Tyranitar".
    # For multi-word species like 'landorus-therian' you get 'Landorus-Therian'.
    return "-".join(part.capitalize() for part in (mon.species or "").split("-"))


def _MOVE_NAME(m: Move) -> str:
    """Move name as the model expects it."""
    try:
        return m.entry["name"]
    except (KeyError, AttributeError, TypeError):
        return m.id.replace("_", " ").title()


def _STATUS(mon: Pokemon) -> str:
    if mon.fainted:
        return "fnt"
    return mon.status.name.lower() if mon.status else ""


def _ITEM(mon: Pokemon) -> str:
    return (mon.item or "").lower()


def _WEATHER(battle: AbstractBattle) -> str:
    try:
        if battle.weather:
            return next(iter(battle.weather.keys())).name
    except (StopIteration, AttributeError):
        pass
    return ""


def _CONDITIONS(side_conditions: dict) -> str:
    if not side_conditions:
        return ""
    return ",".join(sorted(c.name for c in side_conditions.keys()))


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

# Standard Showdown stat-boost order. The dataset uses 7 entries — the same
# order Showdown ships boosts in: atk, def, spa, spd, spe, accuracy, evasion.
_BOOST_KEYS = ("atk", "def", "spa", "spd", "spe", "accuracy", "evasion")


def _hash(text: str, limit: int) -> int:
    """Mirror of model.hash_string — kept inline so we don't drift from training."""
    import hashlib
    if not text:
        return 0
    b = hashlib.md5(str(text).encode("utf-8")).digest()
    return (int.from_bytes(b, "big") % (limit - 1)) + 1


def _mon_to_dict(mon: Optional[Pokemon], own_side: bool) -> dict:
    """Build the per-pokemon dict the dataset's _process_pokemon expects."""
    if mon is None:
        return {}

    if own_side:
        hp_pct = (mon.current_hp or 0) / (mon.max_hp or 1)
    else:
        hp_pct = mon.current_hp_fraction if mon.current_hp_fraction is not None else 1.0

    boosts = mon.boosts or {}
    boost_list = [float(boosts.get(k, 0)) for k in _BOOST_KEYS]

    moves_list = []
    for mv in (mon.moves or {}).values():
        moves_list.append({"name": _MOVE_NAME(mv), "current_pp": float(mv.current_pp)})

    return {
        "name": _NAME(mon),
        "hp_pct": float(hp_pct),
        "boosts": boost_list,
        "status": _STATUS(mon),
        "item": _ITEM(mon),
        "moves": moves_list,
    }


def _process_pokemon_tensors(pdict: dict) -> tuple:
    """1:1 mirror of PokemonHashDataset._process_pokemon, but returning unbatched tensors."""
    if not pdict:
        return (0, 0, 0, torch.zeros(8), torch.zeros(4, dtype=torch.long), torch.zeros(4, 1))

    hp = pdict.get("hp_pct", 0.0)
    boosts = pdict.get("boosts", [0.0] * 7)
    boosts_normalized = [b / 6.0 for b in boosts]
    numeric_feats = torch.tensor([hp] + boosts_normalized, dtype=torch.float32)

    poke_id = _hash(pdict.get("name"), HASH_LIMITS["pokemon"])
    status_id = _hash(pdict.get("status"), HASH_LIMITS["status"])
    item_id = _hash(pdict.get("item"), HASH_LIMITS["items"])

    moves_list = pdict.get("moves", [])
    sorted_moves = sorted(moves_list, key=lambda x: x.get("name", ""))

    move_ids, move_pps = [], []
    for m in sorted_moves:
        move_ids.append(_hash(m.get("name"), HASH_LIMITS["moves"]))
        move_pps.append([m.get("current_pp", 0.0)])

    while len(move_ids) < 4:
        move_ids.append(0)
        move_pps.append([0.0])

    return (
        poke_id,
        status_id,
        item_id,
        numeric_feats,
        torch.tensor(move_ids, dtype=torch.long),
        torch.tensor(move_pps, dtype=torch.float32),
    )


def _build_batch(battle: AbstractBattle) -> tuple[dict, list[str], list[Pokemon]]:
    """
    Returns (model_batch, ordered_move_names, ordered_bench_mons).
    The orders match the training-time sort, so model output index i maps to:
      i in 0..3 → ordered_move_names[i]      (skip if "")
      i in 4..8 → ordered_bench_mons[i - 4]  (skip if None)
    """
    # ---- active sides ----
    active = battle.active_pokemon
    opp_active = battle.opponent_active_pokemon

    p_dict = _mon_to_dict(active, own_side=True)
    o_dict = _mon_to_dict(opp_active, own_side=False)

    p_id, p_status, p_item, p_num, p_moves, p_pps = _process_pokemon_tensors(p_dict)
    o_id, o_status, o_item, o_num, o_moves, o_pps = _process_pokemon_tensors(o_dict)

    # ---- ordered names for back-mapping ----
    # Same sort key as dataset; pad to length 4 with "".
    p_moves_sorted = sorted((m.get("name", "") for m in p_dict.get("moves", [])))
    while len(p_moves_sorted) < 4:
        p_moves_sorted.append("")

    # ---- bench ----
    bench_pokes = list(battle.available_switches)  # only switchable mons
    bench_dicts = [_mon_to_dict(p, own_side=True) for p in bench_pokes]
    bench_with_pokes = list(zip(bench_dicts, bench_pokes))
    bench_with_pokes.sort(key=lambda pair: pair[0].get("name", ""))

    bench_ids, bench_status, bench_items, bench_numeric, bench_moves, bench_pps = (
        [], [], [], [], [], []
    )
    ordered_bench_mons: list[Optional[Pokemon]] = []
    for bdict, bmon in bench_with_pokes:
        b_id, b_st, b_it, b_n, b_mv, b_p = _process_pokemon_tensors(bdict)
        bench_ids.append(b_id)
        bench_status.append(b_st)
        bench_items.append(b_it)
        bench_numeric.append(b_n)
        bench_moves.append(b_mv)
        bench_pps.append(b_p)
        ordered_bench_mons.append(bmon)

    while len(bench_ids) < 5:
        bench_ids.append(0)
        bench_status.append(0)
        bench_items.append(0)
        bench_numeric.append(torch.zeros(8))
        bench_moves.append(torch.zeros(4, dtype=torch.long))
        bench_pps.append(torch.zeros(4, 1))
        ordered_bench_mons.append(None)

    # ---- field / global ----
    weather_str = _WEATHER(battle)
    p_cond_str = _CONDITIONS(getattr(battle, "side_conditions", {}) or {})
    o_cond_str = _CONDITIONS(getattr(battle, "opponent_side_conditions", {}) or {})

    opponents_remaining = float(
        sum(1 for m in (battle.opponent_team or {}).values() if not m.fainted)
    )
    forced_switch = bool(getattr(battle, "force_switch", False))

    # ---- assemble (with batch dimension) ----
    batch = {
        "active_poke_id": torch.tensor([p_id]),
        "active_status_id": torch.tensor([p_status]),
        "active_item_id": torch.tensor([p_item]),
        "active_numeric": p_num.unsqueeze(0),
        "active_moves": p_moves.unsqueeze(0),
        "active_move_pp": p_pps.unsqueeze(0),
        "opp_poke_id": torch.tensor([o_id]),
        "opp_status_id": torch.tensor([o_status]),
        "opp_item_id": torch.tensor([o_item]),
        "opp_numeric": o_num.unsqueeze(0),
        "opp_moves": o_moves.unsqueeze(0),
        "opp_move_pp": o_pps.unsqueeze(0),
        "bench_ids": torch.tensor(bench_ids).unsqueeze(0),
        "bench_status": torch.tensor(bench_status).unsqueeze(0),
        "bench_items": torch.tensor(bench_items).unsqueeze(0),
        "bench_numeric": torch.stack(bench_numeric).unsqueeze(0),
        "bench_moves": torch.stack(bench_moves).unsqueeze(0),
        "bench_pps": torch.stack(bench_pps).unsqueeze(0),
        "weather": torch.tensor([_hash(weather_str, HASH_LIMITS["weather"])]),
        "p_cond": torch.tensor([_hash(p_cond_str, HASH_LIMITS["conditions"])]),
        "o_cond": torch.tensor([_hash(o_cond_str, HASH_LIMITS["conditions"])]),
        "global_numeric": torch.tensor([[opponents_remaining, 1.0 if forced_switch else 0.0]], dtype=torch.float32),
    }

    return batch, p_moves_sorted, ordered_bench_mons


# ---------------------------------------------------------------------------
# Recommender
# ---------------------------------------------------------------------------

class TransformerRecommender:
    """Loads the trained PokemonTransformerAI and scores legal actions."""
    name = "transformer"

    def __init__(self, weights_path: str, device: str = "cpu"):
        if not os.path.exists(weights_path):
            raise FileNotFoundError(f"Model weights not found: {weights_path}")
        self.device = torch.device(device)
        self.model = PokemonTransformerAI(HASH_LIMITS, embed_dim=64, num_heads=8, num_layers=4)
        state = torch.load(weights_path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(state)
        self.model.to(self.device)
        self.model.eval()
        log.info("Loaded transformer model from %s on %s", weights_path, self.device)

    @torch.no_grad()
    def score(self, battle: AbstractBattle) -> list[ScoredAction]:
        batch, ordered_move_names, ordered_bench_mons = _build_batch(battle)
        batch = {k: v.to(self.device) for k, v in batch.items()}

        logits = self.model(batch)[0]  # shape [9]
        # Softmax for [0,1] confidences. Illegal slots already at -1e9 → ≈0 after softmax.
        probs = F.softmax(logits, dim=-1).cpu().tolist()
        logits_list = logits.cpu().tolist()

        # Build name → Move and species → Pokemon maps for the legal options THIS turn.
        legal_moves_by_name = {_MOVE_NAME(m): m for m in battle.available_moves}
        legal_switch_by_species = {p.species: p for p in battle.available_switches}

        scored: list[ScoredAction] = []

        # Move logits (indices 0..3, sorted alphabetically by display name during build)
        for i, name in enumerate(ordered_move_names):
            if not name:  # padded slot
                continue
            if logits_list[i] < -1e8:  # illegal mask
                continue
            move = legal_moves_by_name.get(name)
            if move is None:
                # Edge case: model knows the move but poke-env doesn't list it as legal
                # right now (Choice item, Disable, etc). Skip.
                continue
            scored.append(ScoredAction(
                action=move,
                score=float(probs[i]),
                reasoning=f"model p={probs[i]:.2%}",
            ))

        # Switch logits (indices 4..8)
        for j, bmon in enumerate(ordered_bench_mons):
            idx = 4 + j
            if bmon is None:
                continue
            if logits_list[idx] < -1e8:
                continue
            legal = legal_switch_by_species.get(bmon.species)
            if legal is None:
                continue
            scored.append(ScoredAction(
                action=legal,
                score=float(probs[idx]),
                reasoning=f"model p={probs[idx]:.2%} · pivot",
            ))

        scored.sort(key=lambda s: s.score, reverse=True)

        # Fallback if everything got filtered (shouldn't happen, but be safe).
        if not scored:
            for m in battle.available_moves:
                scored.append(ScoredAction(action=m, score=0.0, reasoning="fallback"))
            for p in battle.available_switches:
                scored.append(ScoredAction(action=p, score=0.0, reasoning="fallback"))

        return scored
