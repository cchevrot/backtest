#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
                      OPTIMISATEUR DE PARAMÈTRES — VERSION PÉDAGOGIQUE
================================================================================

ARCHITECTURE GLOBALE
---------------------

┌──────────────────────────────────────────────────────────┐
│                    PARAM OPTIMIZER                       │
│   (chef d’orchestre : lit, optimise, sauvegarde)         │
└───────────────┬──────────────────────────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │ ParameterSpace      │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │ BestConfig          │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │ ResultCache         │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │ TradingSimulator    │  <── run(config)
    └─────────────────────┘

BOUCLE D'OPTIMISATION
----------------------

OPTIMIZE():
  1) charger paramètres
  2) charger best_config
  3) évaluer PnL initial
  4) pour i=1..max_iterations :
         pour chaque param actif :
             explorer valeurs autour du centre
             jusqu’aux bornes (centre ± n*step)
  5) sauvegarder best global
"""

import json
import csv
import os
import glob
from datetime import datetime, timedelta

# ⚠ Nécessaire : ton simulateur original
from multi_file_simulator import MultiFileSimulator


# =============================================================================
#                           CONFIG PAR DÉFAUT
# =============================================================================

DEFAULT_PARAMS = {
    "min_market_pnl": {
        "initial_value": 43.0,
        "min_value": 30.0,
        "max_value": 60.0,
        "step": 5.0,
        "priority": 1,
        "enabled": True
    },
    "take_profit_market_pnl": {
        "initial_value": 70.0,
        "min_value": 50.0,
        "max_value": 100.0,
        "step": 10.0,
        "priority": 2,
        "enabled": True
    },
    "trail_stop_market_pnl": {
        "initial_value": 1040,
        "min_value": 800,
        "max_value": 1500,
        "step": 100,
        "priority": 3,
        "enabled": True
    },
    "trade_start_hour": {
        "initial_value": "09:30",
        "min_value": "09:00",
        "max_value": "10:00",
        "step": 15,
        "priority": 4,
        "enabled": True
    },
    "trade_cutoff_hour": {
        "initial_value": "13:45",
        "min_value": "13:00",
        "max_value": "15:00",
        "step": 15,
        "priority": 5,
        "enabled": True
    },
    "min_escape_time": {
        "initial_value": 83.0,
        "min_value": 60.0,
        "max_value": 120.0,
        "step": 10.0,
        "priority": 6,
        "enabled": True
    },
    "max_trades_per_day": {
        "initial_value": 10,
        "min_value": 5,
        "max_value": 20,
        "step": 2,
        "priority": 7,
        "enabled": True
    },
    "stop_echappee_threshold": {
        "initial_value": 1.0,
        "min_value": 1.0,
        "max_value": 3.0,
        "step": 0.5,
        "priority": 8,
        "enabled": True
    },
    "start_echappee_threshold": {
        "initial_value": 1.5,
        "min_value": 1.0,
        "max_value": 3.0,
        "step": 0.5,
        "priority": 9,
        "enabled": True
    },
    "top_n_threshold": {
        "initial_value": 1,
        "min_value": 1,
        "max_value": 5,
        "step": 1,
        "priority": 10,
        "enabled": False
    },
    "trade_value_eur": {
        "initial_value": 100.0,
        "min_value": 50.0,
        "max_value": 200.0,
        "step": 25.0,
        "priority": 11,
        "enabled": False
    },
    "trade_interval_minutes": {
        "initial_value": 150000,
        "min_value": 100000,
        "max_value": 200000,
        "step": 25000,
        "priority": 12,
        "enabled": False
    },
    "max_pnl_timeout_minutes": {
        "initial_value": 6000.0,
        "min_value": 4000.0,
        "max_value": 8000.0,
        "step": 1000.0,
        "priority": 13,
        "enabled": False
    },
}


# =============================================================================
#                        ADAPTATEUR SIMULATEUR
# =============================================================================

class TradingSimulator:
    """
    Adaptateur autour de MultiFileSimulator pour exposer une méthode simple:
        pnl = simulator.run(config)
    """

    def __init__(self, data_files=None, parallel=True):
        if data_files is None:
            data_files = glob.glob('../data/prices_data/dataset3/**/*.lz4',
                                   recursive=True)

        self.backend = MultiFileSimulator(
            data_files=data_files,
            parallel=parallel,
            verbose=False
        )

    def run(self, config: dict) -> float:
        result = self.backend.run_all_files(config)
        return result["total_pnl"]


# =============================================================================
#                         PARAM OPTIMIZER (TOP-DOWN)
# =============================================================================

class ParamOptimizer:

    def __init__(self, simulator, param_file, cache_file, best_file):
        self.simulator = simulator
        self.param_space = ParameterSpace(param_file)
        self.cache = ResultCache(cache_file)
        self.best = BestConfig(best_file)

    def optimize(self, max_tests=0, max_iterations=50):
        """
        max_tests=0 = pas de limite → explore toute la plage autour du centre.
        """

        self.param_space.load()

        current_cfg = self.best.load_or_initial(self.param_space)

        current_pnl = self.evaluate(current_cfg)
        print(f"PnL de départ : {current_pnl:.2f}")

        for iteration in range(1, max_iterations + 1):
            print(f"\n=== ITÉRATION {iteration}/{max_iterations} ===")
            improved = False

            for param in self.param_space.active_params():
                new_cfg, new_pnl = self.optimize_param(param, current_cfg, max_tests)

                if new_pnl > current_pnl:
                    print(f"  ✔ Amélioration {param.name}: {current_pnl:.2f} → {new_pnl:.2f}")
                    current_cfg = new_cfg
                    current_pnl = new_pnl
                    improved = True

            # Toujours mettre à jour le best global
            self.best.update_if_better(current_cfg, current_pnl)

            if not improved:
                print("  (aucune amélioration mais on continue)")

        print(f"\nFIN : meilleur PnL global = {self.best.pnl:.2f}")
        return self.best.config

    # -------------------------------------------------------------------------
    #                  Optimisation d'un paramètre (± n·step)
    # -------------------------------------------------------------------------

    def optimize_param(self, param, base_cfg, max_tests):
        center = base_cfg[param.name]
        candidates = param.generate_candidates_around(center, max_tests)

        print(f"  → Paramètre {param.name} : centre={center} (tests={len(candidates)})")

        best_cfg = base_cfg
        best_pnl = float("-inf")

        for val in candidates:
            cfg = base_cfg.copy()
            cfg[param.name] = val
            pnl = self.evaluate(cfg)

            print(f"      {param.name} = {val} → PnL = {pnl:.2f}")

            if pnl > best_pnl:
                best_cfg = cfg
                best_pnl = pnl

        print(f"  → Meilleur pour {param.name} = {best_cfg[param.name]} ({best_pnl:.2f})")
        return best_cfg, best_pnl

    # -------------------------------------------------------------------------
    #                  Cache + simulation
    # -------------------------------------------------------------------------

    def evaluate(self, config):
        key = self.cache.key(config)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        pnl = self.simulator.run(config)
        self.cache.store(key, pnl, config)
        return pnl


# =============================================================================
#                       COMPOSANTS : PARAMETERS
# =============================================================================

class Parameter:

    def __init__(self, name, settings):
        self.name = name
        self.initial = settings["initial_value"]
        self.min = settings["min_value"]
        self.max = settings["max_value"]
        self.step = settings["step"]
        self.priority = settings["priority"]
        self.enabled = settings.get("enabled", True)

    def is_time(self):
        return isinstance(self.initial, str) and ":" in self.initial

    # -------------------------------------------------------------------------
    #           NOUVELLE VERSION FULL (center ± n·step jusqu’aux bornes)
    # -------------------------------------------------------------------------

    def generate_candidates_around(self, center, max_tests):
        if self.is_time():
            return self._gen_time(center, max_tests)
        return self._gen_num(center, max_tests)

    # 🔥 NUMÉRIQUE : exploration complète autour du centre
    def _gen_num(self, center, max_tests):
        values = [center]

        before = center - self.step
        after = center + self.step

        while before >= self.min or after <= self.max:

            if after <= self.max:
                values.append(after)
                after += self.step

            if before >= self.min:
                values.append(before)
                before -= self.step

            # max_tests=0 → pas de limite
            if max_tests and len(values) >= max_tests:
                break

        return values

    # 🔥 TEMPS : exploration complète autour du centre
    def _gen_time(self, center_str, max_tests):
        def to_dt(s): return datetime.strptime(s, "%H:%M")

        center = to_dt(center_str)
        min_t = to_dt(self.min)
        max_t = to_dt(self.max)
        step = timedelta(minutes=int(self.step))

        values = [center_str]

        before = center - step
        after = center + step

        while before >= min_t or after <= max_t:

            if after <= max_t:
                values.append(after.strftime("%H:%M"))
                after += step

            if before >= min_t:
                values.append(before.strftime("%H:%M"))
                before -= step

            if max_tests and len(values) >= max_tests:
                break

        return values


# =============================================================================
#                 PARAMETER SPACE : ensemble des paramètres
# =============================================================================

class ParameterSpace:

    def __init__(self, filename):
        self.filename = filename
        self.params = {}

    def load(self):
        with open(self.filename) as f:
            raw = json.load(f)
        for name, settings in raw.items():
            self.params[name] = Parameter(name, settings)

    def active_params(self):
        return sorted(
            [p for p in self.params.values() if p.enabled],
            key=lambda p: p.priority
        )

    def initial_config(self):
        return {name: p.initial for name, p in self.params.items()}


# =============================================================================
#                           RESULT CACHE
# =============================================================================

def _parse_csv_value(v):
    try: return int(v)
    except: pass
    try: return float(v)
    except: pass
    return v

class ResultCache:

    def __init__(self, csv_file):
        self.file = csv_file
        self.data = {}
        if os.path.exists(csv_file):
            self._load()

    def _load(self):
        with open(self.file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                pnl = float(row.pop("pnl"))
                config = {k:_parse_csv_value(v) for k,v in row.items()}
                key = self.key(config)
                self.data[key] = pnl
        print(f"Cache chargé : {len(self.data)} configs.")

    def key(self, config):
        return json.dumps(config, sort_keys=True)

    def get(self, key):
        return self.data.get(key)

    def store(self, key, pnl, config):
        self.data[key] = pnl
        self._append_csv(pnl, config)

    def _append_csv(self, pnl, config):
        exists = os.path.exists(self.file)
        with open(self.file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["pnl"] + list(config.keys()))
            if not exists:
                writer.writeheader()
            writer.writerow({"pnl": pnl, **config})


# =============================================================================
#                             BEST CONFIG
# =============================================================================

class BestConfig:

    def __init__(self, filename):
        self.filename = filename
        self.config = None
        self.pnl = float("-inf")

    def load_or_initial(self, param_space):
        if not os.path.exists(self.filename):
            print("Aucun best_config → valeurs initiales.")
            self.config = param_space.initial_config()
            return self.config

        with open(self.filename) as f:
            data = json.load(f)
            self.config = data["config"]
            self.pnl = data["pnl"]
        print(f"Meilleur existant: {self.pnl:.2f}")
        return self.config.copy()

    def update_if_better(self, config, pnl):
        if pnl > self.pnl:
            print(f"🏆 Nouveau best global : {pnl:.2f}")
            self.config = config.copy()
            self.pnl = pnl
            self._save()

    def _save(self):
        with open(self.filename, "w") as f:
            json.dump({"pnl": self.pnl, "config": self.config}, f, indent=4)


# =============================================================================
#                                    MAIN
# =============================================================================

def main():
    param_file = "params.json"
    cache_file = "results.csv"
    best_file = "best_config.json"

    # Si params.json n'existe pas → créer automatiquement
    if not os.path.exists(param_file):
        print(f"{param_file} introuvable → création.")
        with open(param_file, "w") as f:
            json.dump(DEFAULT_PARAMS, f, indent=4)

    simulator = TradingSimulator(parallel=True)

    optimizer = ParamOptimizer(
        simulator=simulator,
        param_file=param_file,
        cache_file=cache_file,
        best_file=best_file
    )

    best_cfg = optimizer.optimize(
        max_tests=0,       # 0 = explore toute la plage
        max_iterations=100
    )

    print("\nConfiguration optimale finale :")
    for k, v in best_cfg.items():
        print(f"  - {k}: {v}")


if __name__ == "__main__":
    main()
