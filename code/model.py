import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset
import hashlib

HASH_LIMITS = {
    'pokemon': 1000,
    'moves': 2000,
    'status': 20,
    'items': 500,
    'weather': 20,
    'conditions': 50
}

def hash_string(text, limit):

    if not text:
        return 0
    hash_bytes = hashlib.md5(str(text).encode('utf-8')).digest()
    hash_int = int.from_bytes(hash_bytes, byteorder='big')
    return (hash_int % (limit - 1)) + 1


class PokemonHashDataset(Dataset):
    def __init__(self, df):
        self.df = df

    def __len__(self):
        return len(self.df)

    def _process_pokemon(self, poke_dict):
        """Processes a single Pokémon, wrapping its move-set profile tightly."""
        if not poke_dict:
            # Return empty/padded structures if Pokémon doesn't exist (e.g., empty bench slot)
            return (0, 0, 0, torch.zeros(8), torch.zeros(4, dtype=torch.long), torch.zeros(4, 1))

        # 1. Continuous Features (HP + 7 Stats Boosts)
        hp = poke_dict.get('hp_pct', 0.0)
        boosts = poke_dict.get('boosts', [0.0]*7)
        if isinstance(boosts, torch.Tensor):
            boosts = boosts.tolist()

        # Normalize boosts from [-6, 6] down to [-1, 1]
        boosts_normalized = [b / 6.0 for b in boosts]
        numeric_feats = torch.tensor([hp] + boosts_normalized, dtype=torch.float32)

        # 2. Categorical Features via Deterministic Hashing Trick
        poke_id = hash_string(poke_dict.get('name'), HASH_LIMITS['pokemon'])
        status_id = hash_string(poke_dict.get('status'), HASH_LIMITS['status'])
        item_id = hash_string(poke_dict.get('item'), HASH_LIMITS['items'])

        # 3. Process Moves
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
            numeric_feats,
            torch.tensor(move_ids, dtype=torch.long),
            torch.tensor(move_pps, dtype=torch.float32)
        )

    def __getitem__(self, idx):
        row = self.df.iloc[idx]

        # --- 1. Active Pokémon & Opponent ---
        p_id, p_status, p_item, p_num, p_moves, p_pps = self._process_pokemon(row['player_active_pokemon'])
        o_id, o_status, o_item, o_num, o_moves, o_opp_pps = self._process_pokemon(row['opponent_active_pokemon'])

        # --- 2. Bench / Switches ---
        bench_list = row['available_switches']
        sorted_bench = sorted(bench_list, key=lambda x: x.get('name', ''))

        bench_ids, bench_status, bench_items, bench_numeric = [], [], [], []
        bench_moves, bench_pps = [], []

        for p in sorted_bench:
            b_id, b_stat, b_itm, b_num, b_mvs, b_p = self._process_pokemon(p)
            bench_ids.append(b_id)
            bench_status.append(b_stat)
            bench_items.append(b_itm)
            bench_numeric.append(b_num)
            bench_moves.append(b_mvs)
            bench_pps.append(b_p)

        # Pad missing bench slots to exactly 5 slots
        while len(bench_ids) < 5:
            bench_ids.append(0)
            bench_status.append(0)
            bench_items.append(0)
            bench_numeric.append(torch.zeros(8))
            bench_moves.append(torch.zeros(4, dtype=torch.long))
            bench_pps.append(torch.zeros(4, 1))

        # --- 3. Global Environmental State ---
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
            'active_numeric': p_num,
            'active_moves': p_moves,
            'active_move_pp': p_pps,

            'opp_poke_id': torch.tensor(o_id),
            'opp_status_id': torch.tensor(o_status),
            'opp_item_id': torch.tensor(o_item),
            'opp_numeric': o_num,
            'opp_moves': o_moves,
            'opp_move_pp': o_opp_pps,

            'bench_ids': torch.tensor(bench_ids),
            'bench_status': torch.tensor(bench_status),
            'bench_items': torch.tensor(bench_items),
            'bench_numeric': torch.stack(bench_numeric),
            'bench_moves': torch.stack(bench_moves),
            'bench_pps': torch.stack(bench_pps),

            'weather': torch.tensor(weather_id),
            'p_cond': torch.tensor(p_cond_id),
            'o_cond': torch.tensor(o_cond_id),
            'global_numeric': global_numeric,

            'label': torch.tensor(row['action'], dtype=torch.long)
        }

class FeatureMLP(nn.Module):
    """
    Upgraded projection layer utilizing a linear bottleneck projection 
    and a non-linear residual block to eliminate state information bottlenecks.
    """
    def __init__(self, in_features, out_features, dropout_p=0.1):
        super().__init__()
        # Direct projection to match target dimensions
        self.proj = nn.Linear(in_features, out_features)
        
        # Residual non-linear processing block
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

        # --- Embeddings ---
        self.poke_embed = nn.Embedding(vocab_sizes['pokemon'], embed_dim)
        self.move_embed = nn.Embedding(vocab_sizes['moves'], embed_dim)
        self.status_embed = nn.Embedding(vocab_sizes['status'], embed_dim)
        self.item_embed = nn.Embedding(vocab_sizes['items'], embed_dim)
        self.weather_embed = nn.Embedding(vocab_sizes['weather'], embed_dim)
        self.cond_embed = nn.Embedding(vocab_sizes['conditions'], embed_dim)

        # --- Enhanced Non-Linear Projections ---
        self.move_numeric_proj = nn.Linear(1, embed_dim)
        
        # Blends IDs + 8 continuous traits tightly
        self.poke_combiner = FeatureMLP(embed_dim * 3 + 8, embed_dim, dropout_p)
        
        # FIX 2 REMOVAL: self.move_flatten_proj and self.poke_move_merger are removed 
        # as we no longer collapse moves into the Pokemon profile.

        # Environment Combiners
        self.global_cat_proj = FeatureMLP(embed_dim * 3, embed_dim, dropout_p)
        self.global_proj = FeatureMLP(embed_dim + 2, embed_dim, dropout_p)

        # Structural Semantic Type Tokens (0: Global, 1: Active, 2: Opponent, 3: Moves, 4: Bench)
        self.type_embed = nn.Embedding(5, embed_dim)
        
        # Sequence layout remains 12 tokens, but moves are now natively exposed sequence tokens
        # Layout: 1 global + 1 active + 1 opp + 4 active moves + 5 bench slots = 12 tokens
        self.pos_embed = nn.Parameter(torch.zeros(1, 12, embed_dim))
        nn.init.trunc_normal_(self.pos_embed, std=0.02)

        self.embedding_dropout = nn.Dropout(p=dropout_p)

        # --- Transformer Core ---
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=num_heads,
            dim_feedforward=embed_dim * 4,
            dropout=dropout_p,
            activation='gelu',
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # --- Unified Matchup-Conditioned Decision Head ---
        self.unified_score_head = nn.Sequential(
            nn.Linear(embed_dim * 3, embed_dim),
            nn.SiLU(),
            nn.Dropout(dropout_p),
            nn.Linear(embed_dim, 1)
        )

    def _embed_base_pokemon(self, p_id, status_id, item_id, numeric_feats):
        """Combines base stats, status, items and continuous metrics into a clean entity vector."""
        p_emb = self.poke_embed(p_id)
        s_emb = self.status_embed(status_id)
        i_emb = self.item_embed(item_id)
        
        concat_base = torch.cat([p_emb, s_emb, i_emb, numeric_feats], dim=-1)
        return self.poke_combiner(concat_base) 

    def forward(self, batch):
        batch_size = batch['active_poke_id'].size(0)
        device = batch['active_poke_id'].device

        # Extractions
        forced_switch = batch['global_numeric'][:, 1:2] # [Batch, 1]

        # 1. Embed Active Unit and Opponent Unit (Pure state vectors, no embedded moves inside)
        active_p_emb = self._embed_base_pokemon(
            batch['active_poke_id'], batch['active_status_id'], batch['active_item_id'], batch['active_numeric']
        ).unsqueeze(1) # [Batch, 1, embed_dim]

        opp_active_emb = self._embed_base_pokemon(
            batch['opp_poke_id'], batch['opp_status_id'], batch['opp_item_id'], batch['opp_numeric']
        ).unsqueeze(1) # [Batch, 1, embed_dim]

        # 2. FIX 2 & 5: Embed Active Move Choices cleanly as distinct sequence tokens
        # Combined ID + continuous current PP without arbitrary addition of active_p_emb
        move_action_embs = self.move_embed(batch['active_moves']) + self.move_numeric_proj(batch['active_move_pp']) # [Batch, 4, embed_dim]

        # 3. Embed Benched Units natively
        bench_embs = self._embed_base_pokemon(
            batch['bench_ids'], batch['bench_status'], batch['bench_items'], batch['bench_numeric']
        ) # [Batch, 5, embed_dim]

        # 4. Embed Global Environmental Context
        w_emb = self.weather_embed(batch['weather'])
        pc_emb = self.cond_embed(batch['p_cond'])
        oc_emb = self.cond_embed(batch['o_cond'])
        global_cat = self.global_cat_proj(torch.cat([w_emb, pc_emb, oc_emb], dim=-1))
        global_emb = self.global_proj(torch.cat([global_cat, batch['global_numeric']], dim=-1)).unsqueeze(1) # [Batch, 1, embed_dim]

        # 5. Initialize Structural Semantic Type Tokens
        t_global = self.type_embed(torch.tensor([0], device=device)).expand(batch_size, 1, -1)
        t_active = self.type_embed(torch.tensor([1], device=device)).expand(batch_size, 1, -1)
        t_opp    = self.type_embed(torch.tensor([2], device=device)).expand(batch_size, 1, -1)
        t_moves  = self.type_embed(torch.tensor([3], device=device)).expand(batch_size, 4, -1)
        t_bench  = self.type_embed(torch.tensor([4], device=device)).expand(batch_size, 5, -1)

        # 6. Sequence Layout Assembly 
        # Moves are now standalone contextual channels passing through the Transformer block
        tokens = torch.cat([global_emb, active_p_emb, opp_active_emb, move_action_embs, bench_embs], dim=1)
        type_markers = torch.cat([t_global, t_active, t_opp, t_moves, t_bench], dim=1)

        # --- Apply Structural Type Markers & Positional Embeddings ---
        tokens = tokens + type_markers + self.pos_embed[:, :tokens.size(1), :]
        tokens = self.embedding_dropout(tokens)
        
        transformed_tokens = self.transformer(tokens)

        # 7. Extract Target Slices & Context Elements
        transformed_global = transformed_tokens[:, 0:1, :]  # Global Context representation [Batch, 1, embed_dim]
        transformed_opp    = transformed_tokens[:, 2:3, :]  # Opponent representation [Batch, 1, embed_dim]
        transformed_moves  = transformed_tokens[:, 3:7, :]  # Natively cross-examined moves [Batch, 4, embed_dim]
        transformed_bench  = transformed_tokens[:, 7:12, :] # Natively cross-examined bench units [Batch, 5, embed_dim]

        # 8. Unify Matchup Context Evaluations Across Shared Head Weights
        global_ctx_moves = transformed_global.expand(-1, 4, -1)
        opp_ctx_moves = transformed_opp.expand(-1, 4, -1)
        moves_matchup_vectors = torch.cat([transformed_moves, opp_ctx_moves, global_ctx_moves], dim=-1)
        move_logits = self.unified_score_head(moves_matchup_vectors).squeeze(-1)

        global_ctx_bench = transformed_global.expand(-1, 5, -1)
        opp_ctx_bench = transformed_opp.expand(-1, 5, -1)
        bench_matchup_vectors = torch.cat([transformed_bench, opp_ctx_bench, global_ctx_bench], dim=-1)
        switch_logits = self.unified_score_head(bench_matchup_vectors).squeeze(-1)

        # 9. Forced Switch Adjustments
        forced_mask = forced_switch.expand(-1, 4) * -1e9
        move_logits = move_logits + forced_mask

        final_logits = torch.cat([move_logits, switch_logits], dim=1)

        # 10. Hard Masking Illegal Selections
        invalid_moves_mask = (batch['active_moves'] == 0)
        invalid_bench_mask = (batch['bench_ids'] == 0)
        full_illegal_mask = torch.cat([invalid_moves_mask, invalid_bench_mask], dim=1)

        final_logits = final_logits.masked_fill(full_illegal_mask, -1e9)

        return final_logits