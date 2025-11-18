#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
                      OPTIMISATEUR DE PARAMÈTRES — VERSION PÉDAGOGIQUE
================================================================================

Ce fichier est pensé pour être lu TOP-DOWN :

1) On commence par les imports et la config par défaut
2) Puis l'adaptateur du simulateur
3) Puis la classe principale ParamOptimizer (chef d'orchestre)
4) Puis les composants : Parameter, ParameterSpace, ResultCache, BestConfig
5) Enfin le main()

Les schémas ASCII ci-dessous résument l'architecture :

ARCHITECTURE GLOBALE
---------------------

┌──────────────────────────────────────────────────────────┐
│                    PARAM OPTIMIZER                       │
│   (chef d’orchestre : lit, optimise, sauvegarde)         │
└───────────────┬──────────────────────────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │ ParameterSpace      │ <── lit params.json
    │ (définit domaines)  │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │ BestConfig          │ <── lit best_config.json
    │ (meilleure solution)│
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │ ResultCache         │ <── lit results.csv
    │ (mémoisation PnL)   │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │ TradingSimulator    │ <── wrap MultiFileSimulator.run_all_files
    └─────────────────────┘


BOUCLE D'OPTIMISATION
----------------------

+----------------------------------------------------------+
| OPTIMIZE()                                               |
+----------------------------------------------------------+
         |
         v
 1. charger paramètres (ParameterSpace.load)
 2. charger meilleure config connue (BestConfig.load_or_initial)
 3. calculer son PnL (evaluate)
         |
         v
 +--------------------------------------+
 | pour i = 1 à max_iterations :        |
 |      amélioration = False            |
 |      pour chaque paramètre actif :   |
 |           tester plusieurs valeurs   |
 |           si meilleure → mise à jour |
 |           amélioration = True        |
 |      si !amélioration : STOP         |
 +--------------------------------------+
         |
         v
 4. sauvegarder la meilleure solution (BestConfig)
"""

import json
import csv
import os
import glob
from datetime import datetime, timedelta

# On suppose que tu as déjà ce module dans ton projet
# (comme dans ton code original)
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
    # tu peux réactiver ceux-ci si tu veux
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

    Au lieu d'appeler toi-même run_all_files(config)['total_pnl'].
    """

    def __init__(self, data_files=None, parallel=True):
        if data_files is None:
            # même logique que ton code original
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
#                         PARTIE A — TOP LEVEL
# =============================================================================

class ParamOptimizer:
    """
    Optimisateur pensé top-down.

    SCHÉMA ASCII (rappel) :
    ------------------------

    +----------------------------------------------------------+
    | OPTIMIZE()                                               |
    +----------------------------------------------------------+
             |
             v
     1. charger paramètres (ParameterSpace.load)
     2. charger meilleure config (BestConfig.load_or_initial)
     3. calculer PnL initial (evaluate)
             |
             v
     4. boucle :
          - pour chaque paramètre :
                tester plusieurs valeurs
                garder la meilleure
          - si pas d'amélioration : on arrête
             |
             v
     5. résultat final : BestConfig
    """

    def __init__(self, simulator, param_file, cache_file, best_file):
        self.simulator = simulator
        self.param_space = ParameterSpace(param_file)
        self.cache = ResultCache(cache_file)
        self.best = BestConfig(best_file)

    def optimize(self, max_tests=3, max_iterations=50):
        """
        Fonction principale à lire en premier quand tu explores le fichier.
        """

        # 1) Charger les paramètres
        self.param_space.load()

        # 2) Charger meilleure config si déjà existante, sinon config initiale
        current_cfg = self.best.load_or_initial(self.param_space)

        # 3) Calculer PnL de départ
        current_pnl = self.evaluate(current_cfg)
        print(f"PnL de départ : {current_pnl:.2f}")

        # 4) Boucle sur les itérations
        for iteration in range(1, max_iterations + 1):
            print(f"\n=== ITÉRATION {iteration}/{max_iterations} ===")
            improved = False

            # Parcours des paramètres actifs par ordre de priorité
            for param in self.param_space.active_params():
                new_cfg, new_pnl = self.optimize_param(param, current_cfg, max_tests)

                if new_pnl > current_pnl:
                    print(f"  ✔ Amélioration {param.name}: {current_pnl:.2f} → {new_pnl:.2f}")
                    current_cfg = new_cfg
                    current_pnl = new_pnl
                    improved = True
                else:
                    print(f"  ➜ Pas mieux pour {param.name} (meilleur testé: {new_pnl:.2f})")

            # Sauvegarde si meilleure config globale
            self.best.update_if_better(current_cfg, current_pnl)

            # Si aucune amélioration sur l’itération entière → convergence atteinte
            if not improved:
                print("Aucune amélioration sur cette itération → arrêt.")
                break

        print(f"\nFIN : meilleur PnL global = {self.best.pnl:.2f}")
        return self.best.config

    # -------------------------------------------------------------------------
    #         NIVEAU INTERMÉDIAIRE : optimisation d’un paramètre
    # -------------------------------------------------------------------------
    def optimize_param(self, param, base_cfg, max_tests):
        """
        Optimise un seul paramètre :
          - génère des valeurs candidates
          - teste chaque config
          - renvoie (config_best, pnl_best)
        """
        current_value = base_cfg[param.name]
        candidates = param.generate_candidates_around(current_value, max_tests)

        best_cfg = base_cfg
        best_pnl = float('-inf')

        for val in candidates:
            cfg = base_cfg.copy()
            cfg[param.name] = val
            pnl = self.evaluate(cfg)
            if pnl > best_pnl:
                best_pnl = pnl
                best_cfg = cfg

        return best_cfg, best_pnl

    # -------------------------------------------------------------------------
    #                EVALUATION : cache + simulateur
    # -------------------------------------------------------------------------
    def evaluate(self, config: dict) -> float:
        """
        Teste une configuration :
        - si déjà présente dans le cache (CSV) → récupérée directement
        - sinon → simulation avec TradingSimulator + insertion dans le cache
        """
        key = self.cache.key(config)
        cached = self.cache.get(key)
        if cached is not None:
            # print(f"  (cache) PnL={cached:.2f}")  # tu peux décommenter
            return cached

        pnl = self.simulator.run(config)
        self.cache.store(key, pnl, config)
        return pnl


# =============================================================================
#                    PARTIE B — COMPOSANTS INTERMÉDIAIRES
# =============================================================================

class Parameter:
    """
    Représente UN paramètre.
    
    Exemple :
        name="min_market_pnl"
        initial=43.0
        min=30.0
        max=60.0
        step=5.0
        priority=1
        enabled=True
    """

    def __init__(self, name, settings: dict):
        self.name = name
        self.initial = settings["initial_value"]
        self.min = settings["min_value"]
        self.max = settings["max_value"]
        self.step = settings["step"]
        self.priority = settings["priority"]
        self.enabled = settings.get("enabled", True)

    def is_time(self) -> bool:
        """Renvoie True si le paramètre est de type 'heure' (HH:MM)."""
        return isinstance(self.initial, str) and ":" in self.initial

    def generate_candidates_around(self, center, max_tests: int):
        """
        Génère une liste de valeurs autour de 'center'.
        
        Exemple numérique :
            center = 43, step = 5 → [43, 38, 48, 33, 53, ...]
        
        Exemple temps:
            center = "09:30", step = 15 → ["09:30","09:15","09:45","09:00","10:00"...]
        """
        if self.is_time():
            return self._gen_time(center, max_tests)
        return self._gen_num(center, max_tests)

    def _gen_num(self, center, max_tests):
        values = [center]
        before = center - self.step
        after = center + self.step

        while len(values) < max_tests:
            if before >= self.min:
                values.append(before)
                before -= self.step
            if after <= self.max:
                values.append(after)
                after += self.step
            if before < self.min and after > self.max:
                break
        return values

    def _gen_time(self, center_str, max_tests):
        def to_dt(s):
            return datetime.strptime(s, "%H:%M")

        center = to_dt(center_str)
        min_t = to_dt(self.min)
        max_t = to_dt(self.max)
        step = timedelta(minutes=int(self.step))

        values = [center_str]
        before = center - step
        after = center + step

        while len(values) < max_tests:
            if before >= min_t:
                values.append(before.strftime("%H:%M"))
                before -= step
            if after <= max_t:
                values.append(after.strftime("%H:%M"))
                after += step
            if before < min_t and after > max_t:
                break

        return values


class ParameterSpace:
    """
    Gère l’ensemble des paramètres, lit le JSON et fournit :
      - la liste des paramètres actifs
      - la config initiale
    """

    def __init__(self, filename: str):
        self.filename = filename
        self.params: dict[str, Parameter] = {}

    def load(self):
        """Charge params.json et crée les objets Parameter."""
        with open(self.filename) as f:
            raw = json.load(f)
        for name, settings in raw.items():
            self.params[name] = Parameter(name, settings)

    def active_params(self):
        """Liste des Parameter 'enabled', triés par priorité."""
        return sorted(
            [p for p in self.params.values() if p.enabled],
            key=lambda p: p.priority
        )

    def initial_config(self) -> dict:
        """Construit {nom_param: valeur_initiale}."""
        return {n: p.initial for n, p in self.params.items()}


def _parse_csv_value(v: str):
    """Convertit une chaîne CSV en int/float/str pour garder les types."""
    try:
        iv = int(v)
        return iv
    except ValueError:
        try:
            fv = float(v)
            return fv
        except ValueError:
            return v


class ResultCache:
    """
    Cache des configurations déjà testées.

    Structure interne :
        self.data : dict[config_key] = pnl

    Où config_key est un json.dumps trié des paramètres.
    """

    def __init__(self, csv_file: str):
        self.csv_file = csv_file
        self.data: dict[str, float] = {}
        if os.path.exists(csv_file):
            self._load()

    def _load(self):
        with open(self.csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pnl = float(row.pop("pnl"))
                # row contient les paramètres sous forme de str
                config = {k: _parse_csv_value(v) for k, v in row.items()}
                key = self.key(config)
                self.data[key] = pnl
        print(f"Cache chargé : {len(self.data)} configurations.")

    def key(self, config: dict) -> str:
        """Crée une clé unique basée sur le JSON trié des paramètres."""
        return json.dumps(config, sort_keys=True)

    def get(self, key: str):
        return self.data.get(key)

    def store(self, key: str, pnl: float, config: dict):
        """Ajoute au cache en mémoire + append dans le CSV."""
        self.data[key] = pnl
        self._append_csv(pnl, config)

    def _append_csv(self, pnl: float, config: dict):
        exists = os.path.exists(self.csv_file)
        with open(self.csv_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["pnl"] + list(config.keys()))
            if not exists:
                writer.writeheader()
            writer.writerow({"pnl": pnl, **config})


class BestConfig:
    """
    Gère la meilleure configuration trouvée.

    Fichier JSON :
        {
           "pnl": <float>,
           "config": { param_name: value, ... }
        }
    """

    def __init__(self, filename: str):
        self.filename = filename
        self.config: dict | None = None
        self.pnl: float = float('-inf')

    def load_or_initial(self, param_space: ParameterSpace) -> dict:
        """Charge best_config.json si existe, sinon renvoie config initiale."""
        if not os.path.exists(self.filename):
            self.config = param_space.initial_config()
            print("Aucune best_config existante → utilisation des valeurs initiales.")
            return self.config

        with open(self.filename, "r") as f:
            data = json.load(f)

        self.config = data["config"]
        self.pnl = data["pnl"]
        print(f"Meilleure config existante chargée. PnL = {self.pnl:.2f}")
        return self.config.copy()

    def update_if_better(self, config: dict, pnl: float):
        """Si pnl > meilleur connu, met à jour et sauvegarde."""
        if pnl > self.pnl:
            self.pnl = pnl
            self.config = config.copy()
            self._save()
            print(f"🏆 Nouveau meilleur PnL global : {pnl:.2f}")

    def _save(self):
        with open(self.filename, "w") as f:
            json.dump({"pnl": self.pnl, "config": self.config}, f, indent=4)


# =============================================================================
#                                   MAIN
# =============================================================================

def main():
    param_file = "params.json"
    cache_file = "results.csv"
    best_file = "best_config.json"

    # Si params.json n'existe pas, on le crée avec DEFAULT_PARAMS
    if not os.path.exists(param_file):
        print(f"{param_file} introuvable → création avec DEFAULT_PARAMS.")
        with open(param_file, "w") as f:
            json.dump(DEFAULT_PARAMS, f, indent=4)

    # Création de l'optimiseur
    simulator = TradingSimulator(parallel=True)
    optimizer = ParamOptimizer(
        simulator=simulator,
        param_file=param_file,
        cache_file=cache_file,
        best_file=best_file
    )

    # Lancement de l'optimisation
    best_config = optimizer.optimize(
        max_tests=3,        # nb de valeurs testées par paramètre
        max_iterations=100  # limite dure sur le nombre d'itérations
    )

    print("\nConfiguration optimale finale :")
    for k, v in best_config.items():
        print(f"  - {k}: {v}")


if __name__ == "__main__":
    main()
