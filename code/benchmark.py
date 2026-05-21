import asyncio
from poke_env.player import Player, RandomPlayer ,MaxBasePowerPlayer, SimpleHeuristicsPlayer
import hashlib
import torch
import torch.nn as nn
import argparse

class FeatureMLP(nn.Module):
    def __init__(self, in_features, out_features, dropout_p=0.1):
        super().__init__()
        self.proj = nn.Linear(in_features, out_features)
        self.res = nn.Sequential(
            nn.Linear(out_features, out_features * 2),
            nn.LayerNorm(out_features * 2),
            nn.GELU(),
            nn.Dropout(dropout_p),
            nn.Linear(out_features * 2, out_features),
            nn.LayerNorm(out_features)
        )

    def forward(self, x):
        projected = self.proj(x)
        return projected + self.res(projected)

class PokemonTransformerAI(nn.Module):
    def __init__(self, vocab_sizes, embed_dim=64, num_heads=8, num_layers=4, dropout_p=0.1):
        super().__init__()
        self.embed_dim = embed_dim

        self.poke_embed = nn.Embedding(vocab_sizes['pokemon'], embed_dim)
        self.move_embed = nn.Embedding(vocab_sizes['moves'], embed_dim)
        self.status_embed = nn.Embedding(vocab_sizes['status'], embed_dim)
        self.item_embed = nn.Embedding(vocab_sizes['items'], embed_dim)
        self.weather_embed = nn.Embedding(vocab_sizes['weather'], embed_dim)
        self.cond_embed = nn.Embedding(vocab_sizes['conditions'], embed_dim)
        self.ability_embed = nn.Embedding(vocab_sizes['ability'], embed_dim)
        self.effect_embed = nn.Embedding(vocab_sizes['effect'], embed_dim)

        self.move_numeric_proj = nn.Linear(1, embed_dim)
        self.poke_combiner = FeatureMLP(embed_dim * 5 + 8, embed_dim, dropout_p)

        self.global_cat_proj = FeatureMLP(embed_dim * 3, embed_dim, dropout_p)
        self.global_proj = FeatureMLP(embed_dim + 2, embed_dim, dropout_p)

        self.type_embed = nn.Embedding(7, embed_dim)

        self.pos_embed = nn.Parameter(torch.zeros(1, 21, embed_dim))
        nn.init.trunc_normal_(self.pos_embed, std=0.02)
        self.embedding_dropout = nn.Dropout(p=dropout_p)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=num_heads,
            dim_feedforward=embed_dim * 4,
            dropout=dropout_p,
            activation='gelu',
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        self.unified_score_head = nn.Sequential(
            nn.Linear(embed_dim * 3, embed_dim),
            nn.SiLU(),
            nn.Dropout(dropout_p),
            nn.Linear(embed_dim, 1)
        )

    def _embed_base_pokemon(self, p_id, status_id, item_id, ability_id, effect_id, numeric_feats):
        p_emb = self.poke_embed(p_id)
        s_emb = self.status_embed(status_id)
        i_emb = self.item_embed(item_id)
        a_emb = self.ability_embed(ability_id)
        e_emb = self.effect_embed(effect_id) 

        concat_base = torch.cat([p_emb, s_emb, i_emb, a_emb, e_emb, numeric_feats], dim=-1)
        return self.poke_combiner(concat_base)

    def forward(self, batch):
        batch_size = batch['active_poke_id'].size(0)
        device = batch['active_poke_id'].device

        forced_switch = batch['global_numeric'][:, 1:2] 

        active_p_emb = self._embed_base_pokemon(
            batch['active_poke_id'], batch['active_status_id'], batch['active_item_id'], 
            batch['active_ability_id'], batch['active_effect_id'], batch['active_numeric']
        ).unsqueeze(1) 

        opp_active_emb = self._embed_base_pokemon(
            batch['opp_poke_id'], batch['opp_status_id'], batch['opp_item_id'], 
            batch['opp_ability_id'], batch['opp_effect_id'], batch['opp_numeric']
        ).unsqueeze(1) 

        move_action_embs = self.move_embed(batch['active_moves']) + self.move_numeric_proj(batch['active_move_pp']) 

        opp_move_embs = self.move_embed(batch['opp_moves']) + self.move_numeric_proj(batch['opp_move_pp'])

        bench_embs = self._embed_base_pokemon(
            batch['bench_ids'], batch['bench_status'], batch['bench_items'], 
            batch['bench_abilities'], batch['bench_effects'], batch['bench_numeric']
        ) 

        opp_bench_embs = self._embed_base_pokemon(
            batch['opp_bench_ids'], batch['opp_bench_status'], batch['opp_bench_items'], 
            batch['opp_bench_abilities'], batch['opp_bench_effects'], batch['opp_bench_numeric']
        )

        w_emb = self.weather_embed(batch['weather'])
        pc_emb = self.cond_embed(batch['p_cond'])
        oc_emb = self.cond_embed(batch['o_cond'])
        global_cat = self.global_cat_proj(torch.cat([w_emb, pc_emb, oc_emb], dim=-1))
        global_emb = self.global_proj(torch.cat([global_cat, batch['global_numeric']], dim=-1)).unsqueeze(1) 

        t_global    = self.type_embed(torch.tensor([0], device=device)).expand(batch_size, 1, -1)
        t_active    = self.type_embed(torch.tensor([1], device=device)).expand(batch_size, 1, -1)
        t_opp       = self.type_embed(torch.tensor([2], device=device)).expand(batch_size, 1, -1)
        t_moves     = self.type_embed(torch.tensor([3], device=device)).expand(batch_size, 4, -1)
        t_opp_moves = self.type_embed(torch.tensor([4], device=device)).expand(batch_size, 4, -1)
        t_bench     = self.type_embed(torch.tensor([5], device=device)).expand(batch_size, 5, -1)
        t_opp_bench = self.type_embed(torch.tensor([6], device=device)).expand(batch_size, 5, -1)

        tokens = torch.cat([
            global_emb, active_p_emb, opp_active_emb, 
            move_action_embs, opp_move_embs, 
            bench_embs, opp_bench_embs
        ], dim=1)
        
        type_markers = torch.cat([
            t_global, t_active, t_opp, 
            t_moves, t_opp_moves, 
            t_bench, t_opp_bench
        ], dim=1)

        tokens = tokens + type_markers + self.pos_embed[:, :tokens.size(1), :]
        tokens = self.embedding_dropout(tokens)

        transformed_tokens = self.transformer(tokens)

        transformed_global = transformed_tokens[:, 0:1, :]  
        transformed_opp    = transformed_tokens[:, 2:3, :]  
        transformed_moves  = transformed_tokens[:, 3:7, :]   
        transformed_bench  = transformed_tokens[:, 11:16, :] 

        global_ctx_moves = transformed_global.expand(-1, 4, -1)
        opp_ctx_moves = transformed_opp.expand(-1, 4, -1)
        moves_matchup_vectors = torch.cat([transformed_moves, opp_ctx_moves, global_ctx_moves], dim=-1)
        move_logits = self.unified_score_head(moves_matchup_vectors).squeeze(-1)

        global_ctx_bench = transformed_global.expand(-1, 5, -1)
        opp_ctx_bench = transformed_opp.expand(-1, 5, -1)
        bench_matchup_vectors = torch.cat([transformed_bench, opp_ctx_bench, global_ctx_bench], dim=-1)
        switch_logits = self.unified_score_head(bench_matchup_vectors).squeeze(-1)

        forced_mask = forced_switch.expand(-1, 4) * -1e9
        move_logits = move_logits + forced_mask

        final_logits = torch.cat([move_logits, switch_logits], dim=1)

        invalid_moves_mask = (batch['active_moves'] == 0)
        invalid_bench_mask = (batch['bench_ids'] == 0)
        full_illegal_mask = torch.cat([invalid_moves_mask, invalid_bench_mask], dim=1)

        final_logits = final_logits.masked_fill(full_illegal_mask, -1e9)

        return final_logits



HASH_LIMITS = {
    'pokemon': 1000,
    'ability': 200,
    'moves': 2000,
    'status': 20,
    'effect': 20,
    'items': 200,
    'weather': 20,
    'conditions': 50
}

def hash_string(text, limit):
    if not text:
        return 0
    hash_bytes = hashlib.md5(str(text).encode('utf-8')).digest()
    hash_int = int.from_bytes(hash_bytes, byteorder='big')
    return (hash_int % (limit - 1)) + 1


def process_pokemon(poke_dict):
    """Processes a single Pokémon, wrapping its profile, ability, effect, and moves."""
    if not poke_dict:
        return (0, 0, 0, 0, 0, torch.zeros(8), torch.zeros(4, dtype=torch.long), torch.zeros(4, 1))

    hp = poke_dict.get('hp_pct', 0.0)
    boosts = poke_dict.get('boosts', [0.0]*7)
    if isinstance(boosts, torch.Tensor):
        boosts = boosts.tolist()

    boosts_normalized = [b / 6.0 for b in boosts]
    numeric_feats = torch.tensor([hp] + boosts_normalized, dtype=torch.float32)

    poke_id = hash_string(poke_dict.get('name'), HASH_LIMITS['pokemon'])
    status_id = hash_string(poke_dict.get('status'), HASH_LIMITS['status'])
    item_id = hash_string(poke_dict.get('item'), HASH_LIMITS['items'])
    ability_id = hash_string(poke_dict.get('ability'), HASH_LIMITS['ability'])
    effect_id = hash_string(poke_dict.get('effect'), HASH_LIMITS['effect']) 

    moves_list = poke_dict.get('moves', [])
    sorted_moves = sorted(moves_list, key=lambda x: x.get('name', ''))

    move_ids = []
    move_pps = []
    for m in sorted_moves:
        move_ids.append(hash_string(m.get('name'), HASH_LIMITS['moves']))
        move_pps.append([m.get('current_pp', 0.0)])

    while len(move_ids) < 4:
        move_ids.append(0)
        move_pps.append([0.0])

    return (
        poke_id,
        status_id,
        item_id,
        ability_id,
        effect_id,
        numeric_feats,
        torch.tensor(move_ids, dtype=torch.long),
        torch.tensor(move_pps, dtype=torch.float32)
    )

def process_bench(bench_list):
    """Helper to process and pad a bench side to exactly 5 slots."""
    sorted_bench = sorted(bench_list, key=lambda x: x.get('name', ''))

    ids, status, items, abilities, effects, numeric = [], [], [], [], [], []
    moves, pps = [], []

    for p in sorted_bench:
        b_id, b_stat, b_itm, b_ability, b_eff, b_num, b_mvs, b_p = process_pokemon(p)
        ids.append(b_id)
        status.append(b_stat)
        items.append(b_itm)
        abilities.append(b_ability)
        effects.append(b_eff)
        numeric.append(b_num)
        moves.append(b_mvs)
        pps.append(b_p)

    while len(ids) < 5:
        ids.append(0)
        status.append(0)
        items.append(0)
        abilities.append(0)
        effects.append(0)
        numeric.append(torch.zeros(8))
        moves.append(torch.zeros(4, dtype=torch.long))
        pps.append(torch.zeros(4, 1))

    return {
        'ids': torch.tensor(ids),
        'status': torch.tensor(status),
        'items': torch.tensor(items),
        'abilities': torch.tensor(abilities),
        'effects': torch.tensor(effects),
        'numeric': torch.stack(numeric),
        'moves': torch.stack(moves),
        'pps': torch.stack(pps)
        }

def get_tensors(row):
    p_id, p_status, p_item, p_ability, p_effect, p_num, p_moves, p_pps = process_pokemon(row['player_active_pokemon'])
    o_id, o_status, o_item, o_ability, o_effect, o_num, o_opp_moves, o_opp_pps = process_pokemon(row['opponent_active_pokemon'])

    player_bench = process_bench(row['available_switches'])
    opp_bench = process_bench(row['opponent_switches'])

    weather_id = hash_string(row['weather'], HASH_LIMITS['weather'])
    p_cond_id = hash_string(row['player_conditions'], HASH_LIMITS['conditions'])
    o_cond_id = hash_string(row['opponent_conditions'], HASH_LIMITS['conditions'])

    global_numeric = torch.tensor([
        float(row['opponents_remaining']),
        1.0 if row['forced_switch'] else 0.0
    ], dtype=torch.float32)

    return {
        'active_poke_id': torch.tensor(p_id),
        'active_status_id': torch.tensor(p_status),
        'active_item_id': torch.tensor(p_item),
        'active_ability_id': torch.tensor(p_ability),
        'active_effect_id': torch.tensor(p_effect),
        'active_numeric': p_num,
        'active_moves': p_moves,
        'active_move_pp': p_pps,

        'opp_poke_id': torch.tensor(o_id),
        'opp_status_id': torch.tensor(o_status),
        'opp_item_id': torch.tensor(o_item),
        'opp_ability_id': torch.tensor(o_ability),
        'opp_effect_id': torch.tensor(o_effect),
        'opp_numeric': o_num,
        'opp_moves': o_opp_moves,       
        'opp_move_pp': o_opp_pps,       

        'bench_ids': player_bench['ids'],
        'bench_status': player_bench['status'],
        'bench_items': player_bench['items'],
        'bench_abilities': player_bench['abilities'],
        'bench_effects': player_bench['effects'],
        'bench_numeric': player_bench['numeric'],
        'bench_moves': player_bench['moves'],
        'bench_pps': player_bench['pps'],

        'opp_bench_ids': opp_bench['ids'],
        'opp_bench_status': opp_bench['status'],
        'opp_bench_items': opp_bench['items'],
        'opp_bench_abilities': opp_bench['abilities'],
        'opp_bench_effects': opp_bench['effects'],
        'opp_bench_numeric': opp_bench['numeric'],
        'opp_bench_moves': opp_bench['moves'],
        'opp_bench_pps': opp_bench['pps'],

        'weather': torch.tensor(weather_id),
        'p_cond': torch.tensor(p_cond_id),
        'o_cond': torch.tensor(o_cond_id),
        'global_numeric': global_numeric,

    }

model = PokemonTransformerAI(HASH_LIMITS)
model.load_state_dict(torch.load('New20Epoch.pt', map_location=torch.device('cpu')))
model.eval()

class DetailedObserverPlayer(Player):
    def choose_move(self, battle):
        with torch.no_grad():
            tensors = get_tensors(self.get_full_state(battle))
            dummy_batch = {k: v.unsqueeze(0) if isinstance(v, torch.Tensor) else v for k, v in tensors.items()}
            tensor = (torch.softmax(model(dummy_batch), dim=1))
            action_rank = torch.argsort(tensor.squeeze(), descending=True).tolist()
        
        sorted_moves = [x for x in battle.active_pokemon.moves.values()]
        sorted_moves.sort(key=lambda x: x.id)
        legal_moves = [x.id for x in battle.available_moves]
        for i in range(len(sorted_moves)):
            if sorted_moves[i].id not in legal_moves:
                sorted_moves[i] = None

        battle.available_switches.sort(key=lambda x: x.name)
        sorted_switches = [x for x in battle.available_switches]
        sorted_switches += [None] * (5 - len(sorted_switches))
        actions = sorted_moves + sorted_switches
        try:
            for i in range(9):
                if actions[action_rank[i]] is not None:
                    return self.create_order(actions[action_rank[i]])
        except:
            return self.choose_random_move(battle)
        
        return self.choose_random_move(battle)

    def get_full_state(self, battle):

        available_switches = [self.parse_pokemon(pokemon) for pokemon in battle.available_switches]
        available_switches.sort(key = lambda x: x['name'])

        opponent_switches = [pokemon for pokemon in battle.opponent_team.values() if pokemon.active == False and pokemon.fainted == False]
        opponent_switches = [self.parse_pokemon(pokemon) for pokemon in opponent_switches]
        opponent_switches.sort(key = lambda x: x['name'])

        if len(battle.weather) < 1:
            weather = 'noweather'
        else:
           weather =  "".join(char for char in list(battle.weather.keys())[0].name.lower() if char.isalnum())

        if len(battle.side_conditions) < 1:
            player_condition = 'noconditions'
        else:
           player_condition =  "".join(char for char in list(battle.side_conditions.keys())[0].name.lower() if char.isalnum())

        if len(battle.opponent_side_conditions) < 1:
            opponent_conditions = 'noconditions'
        else:
           opponent_conditions =  "".join(char for char in list(battle.opponent_side_conditions.keys())[0].name.lower() if char.isalnum())

        return {
            'player_active_pokemon': self.parse_pokemon(battle.active_pokemon),
            'opponent_active_pokemon': self.parse_pokemon(battle.opponent_active_pokemon),
            'available_switches' : available_switches,
            'opponent_switches': opponent_switches,
            'weather': weather,
            'player_conditions': player_condition,
            'opponent_conditions': opponent_conditions,
            'forced_switch': battle.force_switch,
            'opponents_remaining' : len(opponent_switches) + 1

        }

    def parse_pokemon(self, pokemon):
        moves = [{'name': pokemon.moves[name].id, 'current_pp': pokemon.moves[name].current_pp} for name in pokemon.moves]
        moves.sort(key = lambda x: x['name'])
        status = pokemon.status
        if status is None:
            status = 'nostatus'
        else:
            status = status.name.lower()

        if len(pokemon.effects) < 1:
            effect = 'noeffect'
        else:
           effect =  "".join(char for char in list(pokemon.effects.keys())[0].name.lower() if char.isalnum())
        return {
            'ability': pokemon.ability,
            'boosts': [boost for boost in pokemon.boosts.values()],
            'hp_pct': pokemon. current_hp_fraction,
            'effect': effect,
            'status': status,
            'name': pokemon.name,
            'item': pokemon.item,
            'moves': moves
        }



async def main():
    
    parser = argparse.ArgumentParser(description="Model Benchmarking")
    
    parser.add_argument(
        "-o", "--opponent", 
        choices=["r", "m", "h"], 
        default='r',
        help="Type of opponent: 'r' for Random, 'm' for MaxBasePower, 'h' for SimpleHeuristics"
    )
    parser.add_argument(
        "-n", "--games", 
        type=int, 
        default=100, 
        help="Number of battles to play (default: 100)"
    )
    
    args = parser.parse_args()

    opponent_mapping = {
        "r": RandomPlayer,
        "m": MaxBasePowerPlayer,
        "h": SimpleHeuristicsPlayer
    }
    OpponentClass = opponent_mapping[args.opponent]

    player_1 = DetailedObserverPlayer(battle_format="gen3randombattle", max_concurrent_battles=args.games)
    player_2 = OpponentClass(battle_format="gen3randombattle", max_concurrent_battles=args.games)

    
    await player_1.battle_against(player_2, n_battles=args.games)
    total_games = player_1.n_finished_battles
    wins = player_1.n_won_battles

    print("\n=== Battle Results ===")
    print(f"Enemy type: {args.opponent}")
    print(f"Total Battles Played: {total_games}")
    print(f"Win Rate: {(wins / total_games) * 100:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())