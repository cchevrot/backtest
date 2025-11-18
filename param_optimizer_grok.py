import json
import csv
import os
import glob
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional
from multi_file_simulator import MultiFileSimulator  # Assure-toi que ce module existe


@dataclass(frozen=True)
class ParamRange:
    min_val: Any
    max_val: Any
    step: Any
    initial: Any
    priority: int = 999
    enabled: bool = True

    def __post_init__(self):
        # Gestion automatique du type heure (str → datetime)
        if isinstance(self.initial, str) and ":" in self.initial:
            fmt = "%H:%M"
            to_dt = lambda x: datetime.strptime(x, fmt)
            object.__setattr__(self, "min_val", to_dt(self.min_val))
            object.__setattr__(self, "max_val", to_dt(self.max_val))
            object.__setattr__(self, "step", timedelta(minutes=int(self.step)))
            object.__setattr__(self, "initial", to_dt(self.initial))


class ParamOptimizer:
    CACHE_KEY_TYPE = Tuple[Tuple[str, Any], ...]

    def __init__(
        self,
        json_file: str = "params.json",
        results_file: str = "results.csv",
        best_file: str = "best_results.csv",
        best_config_file: str = "best_config.json",
        data_files: Optional[List[str]] = None,
        parallel: bool = True,
    ):
        self.json_file = json_file
        self.results_file = results_file
        self.best_file = best_file
        self.best_config_file = best_config_file

        data_files = data_files or glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        self.simulator = MultiFileSimulator(data_files, parallel=parallel, verbose=False)

        self.params: Dict[str, ParamRange] = {}
        self.param_order: List[str] = []
        self.config_cache: Dict[ParamOptimizer.CACHE_KEY_TYPE, float] = {}
        self.all_results: List[Tuple[float, Dict[str, Any]]] = []

        self.global_best_pnl: float = float('-inf')
        self.global_best_config: Optional[Dict[str, Any]] = None

        self._load_cache_from_csv()

    # ==============================================================
    # Cache & Persistence
    # ==============================================================

    @staticmethod
    def _config_to_key(config: Dict[str, Any]) -> CACHE_KEY_TYPE:
        return tuple(sorted((k, v) for k, v in config.items()))

    def _load_cache_from_csv(self):
        if not os.path.exists(self.results_file):
            print("Aucun fichier results.csv → cache vide")
            return

        try:
            with open(self.results_file, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pnl = float(row.pop('pnl'))
                    config = {k: self._smart_cast(v) for k, v in row.items()}
                    key = self._config_to_key(config)
                    self.config_cache[key] = pnl
                    self.all_results.append((pnl, config))
            print(f"Cache chargé : {len(self.config_cache)} configurations")
        except Exception as e:
            print(f"Erreur lors du chargement du cache : {e}")

    @staticmethod
    def _smart_cast(value: str) -> Any:
        for caster in (int, float):
            try:
                return caster(value)
            except ValueError:
                continue
        return value

    def _append_result(self, config: Dict[str, Any], pnl: float):
        key = self._config_to_key(config)
        if key in self.config_cache:
            return

        self.config_cache[key] = pnl
        self.all_results.append((pnl, config.copy()))

        file_exists = os.path.exists(self.results_file) and os.stat(self.results_file).st_size > 0
        with open(self.results_file, "a", newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["pnl", *config.keys()])
            if not file_exists:
                writer.writeheader()
            writer.writerow({"pnl": pnl, **config})

    def _save_best(self, top_n: int = 10):
        self.all_results.sort(reverse=True, key=lambda x: x[0])
        with open(self.best_file, "w", newline='', encoding='utf-8') as f:
            fieldnames = ["pnl"] + [name for name in self.params.keys()]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for pnl, cfg in self.all_results[:top_n]:
                writer.writerow({"pnl": pnl, **cfg})

    def save_best_config(self, config: Dict[str, Any], pnl: float):
        data = {
            "timestamp": datetime.now().isoformat(),
            "pnl": pnl,
            "config": config
        }
        with open(self.best_config_file, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, default=str)
        print(f"NOUVELLE MEILLEURE CONFIG → PnL = {pnl:.2f}")

    # ==============================================================
    # Chargement paramètres
    # ==============================================================

    def load_params(self):
        with open(self.json_file, encoding='utf-8') as f:
            raw = json.load(f)

        self.params.clear()
        for name, settings in raw.items():
            if not settings.get("enabled", True):
                continue
            self.params[name] = ParamRange(
                min_val=settings["min_value"],
                max_val=settings["max_value"],
                step=settings["step"],
                initial=settings["initial_value"],
                priority=settings.get("priority", 999),
            )

        self.param_order = sorted(self.params.keys(), key=lambda k: self.params[k].priority)
        print(f"Paramètres actifs : {len(self.param_order)}")

    def load_best_config(self) -> Dict[str, Any]:
        if os.path.exists(self.best_config_file):
            with open(self.best_config_file, encoding='utf-8') as f:
                data = json.load(f)
                config = data.get("config", {})
                self.global_best_pnl = data.get("pnl", float('-inf'))
                self.global_best_config = config.copy()
                print(f"Meilleure config précédente → PnL = {self.global_best_pnl:.2f}")
                return config

        print("Aucune config précédente → valeurs initiales")
        return {name: p.initial.strftime("%H:%M") if isinstance(p.initial, datetime) else p.initial
                for name, p in self.params.items()}

    # ==============================================================
    # Génération de valeurs
    # ==============================================================

    def _values_around(self, current: Any, param: ParamRange, max_count: int, expand: bool = False) -> List[Any]:
        if max_count <= 1 and not expand:
            return [current]

        is_time = isinstance(current, datetime)
        step = param.step
        values = [current]
        left = current - step
        right = current + step
        limit = 1000 if expand else max_count

        while len(values) < limit:
            added = False
            if right <= param.max_val:
                values.append(right)
                right += step
                added = True
            if left >= param.min_val:
                values.append(left)
                left -= step
                added = True
            if not added:
                break

        if is_time:
            return [v.strftime("%H:%M") for v in values[:max_count]]
        return [round(v, 4) if isinstance(v, float) else v for v in values[:max_count]]

    def _untested_values(self, param_name: str, base_config: Dict[str, Any], count: int) -> List[Any]:
        current = base_config[param_name]
        param = self.params[param_name]
        candidates = self._values_around(current, param, count * 10, expand=True)
        untested = []

        for val in candidates:
            cfg = base_config.copy()
            cfg[param_name] = val
            if self._config_to_key(cfg) not in self.config_cache:
                untested.append(val)
                if len(untested) >= count:
                    break

        return untested or self._values_around(current, param, count)

    # ==============================================================
    # Évaluation
    # ==============================================================

    def _evaluate(self, config: Dict[str, Any]) -> float:
        key = self._config_to_key(config)
        if key in self.config_cache:
            pnl = self.config_cache[key]
            print(f"    Cache hit → PnL = {pnl:.2f}")
            return pnl

        result = self.simulator.run_all_files(config)
        pnl = result['total_pnl']
        self.config_cache[key] = pnl
        print(f"    Simulé → PnL = {pnl:.2f}")
        return pnl

    # ==============================================================
    # Optimisation d’un paramètre
    # ==============================================================

    def _optimize_param(
        self,
        name: str,
        base_config: Dict[str, Any],
        max_tests: int,
        explore: bool
    ) -> Tuple[float, Any, Dict[str, Any]]:
        current_val = base_config[name]
        param = self.params[name]

        if explore:
            values = self._untested_values(name, base_config, max_tests)
            mode = "exploration"
        else:
            values = self._values_around(current_val, param, max_tests)
            mode = "locale"

        print(f"  {name} (P{param.priority}): {current_val} → {values} [{mode}]")

        results: List[Tuple[float, Any, Dict[str, Any]]] = []
        for val in values:
            cfg = base_config.copy()
            cfg[name] = val
            pnl = self._evaluate(cfg)
            results.append((pnl, val, cfg))
            self._append_result(cfg, pnl)

        results.sort(reverse=True, key=lambda x: x[0])
        return results[0]

    # ==============================================================
    # Boucle principale
    # ==============================================================

    def run_optimization(
        self,
        max_tests_per_param: int = 5,
        max_iterations: int = 50,
        reset_from_initial: bool = False
    ):
        self.load_params()

        if reset_from_initial:
            config = {n: p.initial.strftime("%H:%M") if isinstance(p.initial, datetime) else p.initial
                      for n, p in self.params.items()}
            best_pnl = float('-inf')
            print("RESET → départ depuis valeurs initiales")
        else:
            config = self.load_best_config()
            best_pnl = self._evaluate(config)

        if best_pnl > self.global_best_pnl:
            self.global_best_pnl = best_pnl
            self.global_best_config = config.copy()
            self.save_best_config(config, best_pnl)

        print("\n" + "="*80)
        print(f"DÉPART → PnL = {best_pnl:.2f} | Cache = {len(self.config_cache)} configs")
        print("="*80)

        self._append_result(config, best_pnl)
        prev_iteration_pnl = float('-inf')

        for it in range(1, max_iterations + 1):
            print(f"\n{' ITERATION ' + str(it) + ' ':#^80}")
            iteration_start_pnl = best_pnl
            improvements = 0
            explore = (it > 1 and best_pnl <= prev_iteration_pnl)

            if explore:
                print("Mode EXPLORATION activé (valeurs non testées)")

            for param_name in self.param_order:
                new_pnl, new_val, new_cfg = self._optimize_param(
                    param_name, config, max_tests_per_param, explore
                )

                if new_pnl > best_pnl + 1e-6:
                    gain = new_pnl - best_pnl
                    print(f"    Amélioration {param_name} = {new_val} → +{gain:.2f}")
                    config = new_cfg
                    best_pnl = new_pnl
                    improvements += 1
                else:
                    config[param_name] = new_val

            gain_it = best_pnl - iteration_start_pnl
            print(f"\n  Bilan itération {it}: +{gain_it:.2f} | {improvements} améliorations")

            if best_pnl > self.global_best_pnl:
                print(f"  RECORD ! → {best_pnl:.2f}")
                self.global_best_pnl = best_pnl
                self.global_best_config = config.copy()
                self.save_best_config(config, best_pnl)

            self._save_best()

            if gain_it <= 0:
                print("Convergence atteinte → arrêt")
                break

            prev_iteration_pnl = iteration_start_pnl

        print("\n" + "="*80)
        print("OPTIMISATION TERMINÉE")
        print(f"Meilleur PnL global : {self.global_best_pnl:.2f}")
        print(f"Configurations testées : {len(self.config_cache)}")
        print(f"Fichiers générés : {self.best_file}, {self.best_config_file}, {self.results_file}")
        print("="*80)


# ==============================================================
# Configuration par défaut
# ==============================================================

DEFAULT_PARAMS = {
    "min_market_pnl": {
        "initial_value": 43.0, "min_value": 30.0, "max_value": 60.0, "step": 5.0, "priority": 1, "enabled": True
    },
    "take_profit_market_pnl": {
        "initial_value": 70.0, "min_value": 50.0, "max_value": 100.0, "step": 10.0, "priority": 2, "enabled": True
    },
    "trail_stop_market_pnl": {
        "initial_value": 1040, "min_value": 800, "max_value": 1500, "step": 100, "priority": 3, "enabled": True
    },
    "trade_start_hour": {
        "initial_value": "09:30", "min_value": "09:00", "max_value": "10:00", "step": 15, "priority": 4, "enabled": True
    },
    "trade_cutoff_hour": {
        "initial_value": "13:45", "min_value": "13:00", "max_value": "15:00", "step": 15, "priority": 5, "enabled": True
    },
    "min_escape_time": {
        "initial_value": 83.0, "min_value": 60.0, "max_value": 120.0, "step": 10.0, "priority": 6, "enabled": True
    },
    "max_trades_per_day": {
        "initial_value": 10, "min_value": 5, "max_value": 20, "step": 2, "priority": 7, "enabled": True
    },
    "stop_echappee_threshold": {
        "initial_value": 1, "min_value": 1, "max_value": 3, "step": 0.5, "priority": 8, "enabled": True
    },
    "start_echappee_threshold": {
        "initial_value": 1.5, "min_value": 1.0, "max_value": 3.0, "step": 0.5, "priority": 9, "enabled": True
    },
    "top_n_threshold": {
        "initial_value": 1, "min_value": 1, "max_value": 5, "step": 1, "priority": 10, "enabled": False
    },
    "trade_value_eur": {
        "initial_value": 100.0, "min_value": 50.0, "max_value": 200.0, "step": 25.0, "priority": 11, "enabled": False
    },
    "trade_interval_minutes": {
        "initial_value": 150000, "min_value": 100000, "max_value": 200000, "step": 25000, "priority": 12, "enabled": False
    },
    "max_pnl_timeout_minutes": {
        "initial_value": 6000.0, "min_value": 4000.0, "max_value": 8000.0, "step": 1000.0, "priority": 13, "enabled": False
    },
}


def main():
    optimizer = ParamOptimizer(parallel=True)

    # Création du fichier params.json s’il n’existe pas
    if not os.path.exists("params.json"):
        with open("params.json", "w", encoding='utf-8') as f:
            json.dump(DEFAULT_PARAMS, f, indent=4)
        print("params.json créé avec les valeurs par défaut")

    # Lancement de l’optimisation
    optimizer.run_optimization(
        max_tests_per_param=4,      # ajuste selon ta puissance de calcul
        max_iterations=100,         # très grand = jusqu’à convergence
        reset_from_initial=False    # True = oublie tout et repart de zéro
    )


if __name__ == "__main__":
    main()