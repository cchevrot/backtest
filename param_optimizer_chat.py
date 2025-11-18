import json
import csv
import os
import glob
from datetime import datetime, timedelta
from multi_file_simulator import MultiFileSimulator


# ============================================================
#                       UTILITAIRES
# ============================================================

def is_time_string(value):
    return isinstance(value, str) and ":" in value


def parse_value(value, settings):
    """Convertit une valeur en float/int/time selon le paramètre."""
    if is_time_string(value):
        return datetime.strptime(str(value), "%H:%M")
    try:
        v = float(value)
        return int(v) if v.is_integer() else v
    except Exception:
        return value


def format_value(value):
    """Formate un float/int/time."""
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, float):
        return round(value, 2)
    return value


def load_csv_as_dicts(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def write_csv_row(path, row):
    file_exists = os.path.exists(path) and os.stat(path).st_size > 0
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ============================================================
#              CLASSE PRINCIPALE: ParamOptimizer
# ============================================================

class ParamOptimizer:
    """Optimisation séquentielle itérative avec cache."""

    # --------------------------------------------------------
    #                 INITIALISATION
    # --------------------------------------------------------
    def __init__(self, json_file="params.json", results_file="results.csv",
                 best_file="best_results.csv", best_config_file="best_config.json",
                 data_files=None, parallel=True):

        self.json_file = json_file
        self.results_file = results_file
        self.best_file = best_file
        self.best_config_file = best_config_file

        # Fichiers de données
        data_files = data_files or glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        self.multi_file_simulator = MultiFileSimulator(data_files, parallel=parallel, verbose=False)

        # Paramètres
        self.params = {}
        self.param_order = []

        # Résultats accumulés (pnl, config)
        self.all_results = []

        # Best global
        self.global_best_pnl = float('-inf')
        self.global_best_config = None

        # Cache
        self.config_cache = {}
        self._load_cache()

    # --------------------------------------------------------
    #               GESTION DU CACHE
    # --------------------------------------------------------
    def _config_to_key(self, config: dict):
        return json.dumps(config, sort_keys=True)

    def _load_cache(self):
        rows = load_csv_as_dicts(self.results_file)
        if not rows:
            print("📂 Aucun historique trouvé, cache vide.")
            return

        for row in rows:
            pnl = float(row.pop("pnl"))
            config = {k: parse_value(v, None) for k, v in row.items()}
            key = self._config_to_key(config)
            self.config_cache[key] = pnl
            self.all_results.append((pnl, config))

        print(f"✅ Cache chargé: {len(self.config_cache)} configurations")

    # --------------------------------------------------------
    #                PARAMÈTRES
    # --------------------------------------------------------
    def save_params(self, params):
        with open(self.json_file, "w") as f:
            json.dump(params, f, indent=4)

    def load_params(self):
        with open(self.json_file) as f:
            self.params = json.load(f)

        active = {k: v for k, v in self.params.items() if v.get("enabled", True)}
        self.param_order = sorted(active.keys(), key=lambda k: active[k].get("priority", 999))

        disabled = [k for k, v in self.params.items() if not v.get("enabled", True)]
        if disabled:
            print(f"⚠️ Paramètres désactivés: {disabled}")

    # --------------------------------------------------------
    #                BEST CONFIG
    # --------------------------------------------------------
    def load_best_config(self):
        if not os.path.exists(self.best_config_file):
            print("📝 Pas de config précédente → valeurs initiales.")
            return {k: v["initial_value"] for k, v in self.params.items()}

        with open(self.best_config_file) as f:
            data = json.load(f)

        self.global_best_pnl = data.get("pnl", float('-inf'))
        self.global_best_config = data.get("config", {})
        print(f"📂 Best config chargée. PnL={self.global_best_pnl:.2f}")

        return self.global_best_config.copy()

    def save_best_config(self, config, pnl):
        with open(self.best_config_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "pnl": pnl,
                "config": config
            }, f, indent=4)
        print(f"💾 Best mise à jour: PnL={pnl:.2f}")

    # --------------------------------------------------------
    #          GÉNÉRATION DE VALEURS POUR UN PARAMÈTRE
    # --------------------------------------------------------
    def _value_range(self, settings, center, max_tests, expand=False):
        """Retourne une liste de valeurs autour de 'center'."""
        step = settings["step"]
        min_v = parse_value(settings["min_value"], settings)
        max_v = parse_value(settings["max_value"], settings)

        center = parse_value(center, settings)
        step = timedelta(minutes=int(step)) if isinstance(center, datetime) else float(step)

        values = [format_value(center)]
        before, after = center - step, center + step

        limit = max_tests if not expand else 1000

        while len(values) < limit:
            if after <= max_v:
                values.append(format_value(after))
                after += step
            if not expand and len(values) >= max_tests:
                break
            if before >= min_v:
                values.append(format_value(before))
                before -= step
            if before < min_v and after > max_v:
                break

        return values

    # --------------------------------------------------------
    #                TEST + CACHE
    # --------------------------------------------------------
    def _test_config(self, config):
        key = self._config_to_key(config)
        if key in self.config_cache:
            print(f"      ♻️ Cache → PnL={self.config_cache[key]:.2f}")
            return self.config_cache[key]

        pnl = self.multi_file_simulator.run_all_files(config)["total_pnl"]
        self.config_cache[key] = pnl
        return pnl

    # --------------------------------------------------------
    #          OPTIMISATION D’UN PARAMÈTRE
    # --------------------------------------------------------
    def _optimize_param(self, name, base_config, max_tests, explore=False):
        settings = self.params[name]
        current = base_config[name]

        # valeurs à tester
        if explore:
            values = self._find_new_values(name, base_config, max_tests)
        else:
            values = self._value_range(settings, current, max_tests)

        print(f"  🔍 {name}: {current} → {values}")

        best = None

        for val in values:
            cfg = base_config.copy()
            cfg[name] = val
            pnl = self._test_config(cfg)

            self.all_results.append((pnl, cfg))
            write_csv_row(self.results_file, {"pnl": pnl, **cfg})

            if best is None or pnl > best[0]:
                best = (pnl, val, cfg)

        return best

    def _find_new_values(self, name, cfg, max_tests):
        """Trouve des valeurs encore non testées."""
        settings = self.params[name]
        current = cfg[name]

        candidates = self._value_range(settings, current, max_tests, expand=True)
        untested = []

        for val in candidates:
            test_cfg = cfg.copy()
            test_cfg[name] = val
            key = self._config_to_key(test_cfg)
            if key not in self.config_cache:
                untested.append(val)
                if len(untested) >= max_tests:
                    break

        return untested or self._value_range(settings, current, max_tests)

    # --------------------------------------------------------
    #             OPTIMISATION COMPLÈTE
    # --------------------------------------------------------
    def run_optimization(self, max_tests_per_param=5, max_iterations=10, reset_from_initial=False):
        self.load_params()

        current_cfg = (
            {k: v["initial_value"] for k, v in self.params.items()}
            if reset_from_initial else
            self.load_best_config()
        )

        current_pnl = self._test_config(current_cfg)
        self.all_results.append((current_pnl, current_cfg))
        write_csv_row(self.results_file, {"pnl": current_pnl, **current_cfg})

        if current_pnl > self.global_best_pnl:
            self.global_best_pnl = current_pnl
            self.global_best_config = current_cfg.copy()
            self.save_best_config(current_cfg, current_pnl)

        for it in range(1, max_iterations + 1):
            print(f"\n# ======== ITERATION {it}/{max_iterations} ========")

            start_pnl = current_pnl
            explore = (it > 1 and current_pnl <= start_pnl)

            for param in self.param_order:
                best_pnl, best_val, best_cfg = self._optimize_param(
                    param, current_cfg, max_tests_per_param, explore
                )

                if best_pnl > current_pnl:
                    current_cfg = best_cfg
                    current_pnl = best_pnl
                    print(f"    ✔ amélioration {param}={best_val} → {best_pnl:.2f}")
                else:
                    current_cfg[param] = best_val
                    print(f"    ➡ stable {param}={best_val}")

            if current_pnl > self.global_best_pnl:
                self.global_best_pnl = current_pnl
                self.global_best_config = current_cfg.copy()
                self.save_best_config(current_cfg, current_pnl)

            if current_pnl <= start_pnl:
                print("🛑 Convergence → arrêt.")
                break

        print("\n🏁 Optimisation terminée.")
        print(f"Meilleur PnL global: {self.global_best_pnl:.2f}")


# ============================================================
#              CONFIGURATION PAR DÉFAUT
# ============================================================

DEFAULT_PARAMS = {
    "min_market_pnl": {"initial_value": 43.0, "min_value": 30.0, "max_value": 60.0, "step": 5.0, "priority": 1, "enabled": True},
    "take_profit_market_pnl": {"initial_value": 70.0, "min_value": 50.0, "max_value": 100.0, "step": 10.0, "priority": 2, "enabled": True},
    "trail_stop_market_pnl": {"initial_value": 1040, "min_value": 800, "max_value": 1500, "step": 100, "priority": 3, "enabled": True},
    "trade_start_hour": {"initial_value": "09:30", "min_value": "09:00", "max_value": "10:00", "step": 15, "priority": 4, "enabled": True},
    "trade_cutoff_hour": {"initial_value": "13:45", "min_value": "13:00", "max_value": "15:00", "step": 15, "priority": 5, "enabled": True},
    "min_escape_time": {"initial_value": 83.0, "min_value": 60.0, "max_value": 120.0, "step": 10.0, "priority": 6, "enabled": True},
    "max_trades_per_day": {"initial_value": 10, "min_value": 5, "max_value": 20, "step": 2, "priority": 7, "enabled": True},
    "stop_echappee_threshold": {"initial_value": 1, "min_value": 1, "max_value": 3, "step": 0.5, "priority": 8, "enabled": True},
    "start_echappee_threshold": {"initial_value": 1.5, "min_value": 1.0, "max_value": 3.0, "step": 0.5, "priority": 9, "enabled": True},
}


# ============================================================
#                     MAIN
# ============================================================

def main():
    opt = ParamOptimizer(parallel=True)

    if not os.path.exists("params.json"):
        opt.save_params(DEFAULT_PARAMS)

    opt.run_optimization(max_tests_per_param=3, max_iterations=5000)


if __name__ == "__main__":
    main()
