import json
import csv
import os
import random
from datetime import datetime, timedelta
from itertools import product, islice


class ParamOptimizer:
    def __init__(self, json_file="params.json", results_file="results.csv",
                 best_file="best_results.csv", log_file="optimizer.log"):
        self.json_file = json_file
        self.results_file = results_file
        self.best_file = best_file
        self.log_file = log_file
        self.params = {}
        self.results = []
        self.param_order = []  # Pour garder l'ordre des paramètres

    # -----------------------
    # UTILS
    # -----------------------
    def _log(self, msg: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _format_values_only(self, param_dict: dict) -> str:
        """Retourne seulement les valeurs dans l'ordre des paramètres"""
        return ", ".join(str(param_dict[name]) for name in self.param_order)

    # -----------------------
    # JSON
    # -----------------------
    def save_params(self, params: dict):
        with open(self.json_file, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=4)
        self._log(f"Paramètres sauvegardés dans {self.json_file}")

    def load_params(self):
        if not os.path.exists(self.json_file):
            raise FileNotFoundError(f"Fichier {self.json_file} introuvable.")
        with open(self.json_file, "r", encoding="utf-8") as f:
            self.params = json.load(f)
        self.param_order = list(self.params.keys())  # Mémorise l'ordre
        self._log(f"Paramètres chargés ({len(self.params)} total)")

    # -----------------------
    # SIMULATION
    # -----------------------
    def _simulate_strategy(self, param_values: dict) -> float:
        """Simulation fictive PnL. À remplacer par ton vrai algo."""
        base_pnl = 900 + random.random() * 200
        noise = random.uniform(-50, 50)
        return round(base_pnl + noise, 2)

    # -----------------------
    # GÉNÉRATION DES VALEURS
    # -----------------------
    def _generate_values(self, settings, max_tests=5):
        initial = settings["initial_value"]
        min_val = settings["min_value"]
        max_val = settings["max_value"]
        step = settings["step"]
        values = []

        if isinstance(initial, str) and ":" in initial:
            start = datetime.strptime(min_val, "%H:%M")
            end = datetime.strptime(max_val, "%H:%M")
            step_delta = timedelta(minutes=int(step))
            current = start
            while current <= end and len(values) < max_tests:
                values.append(current.strftime("%H:%M"))
                current += step_delta
        else:
            val = float(min_val)
            while val <= float(max_val) and len(values) < max_tests:
                values.append(round(val, 2))
                val += float(step)

        return values

    # -----------------------
    # OPTIMISATION COMPLÈTE
    # -----------------------
    def run_full_optimization(self, max_tests_per_param=5, top_n=10, max_total_tests=1000):
        if not self.params:
            self.load_params()

        # Nettoyer les fichiers
        for file in [self.results_file, self.best_file, self.log_file]:
            open(file, "w").close()

        # Générer les valeurs
        param_values_list = []
        for name in self.param_order:
            vals = self._generate_values(self.params[name], max_tests=max_tests_per_param)
            param_values_list.append(vals)
            self._log(f"{name}: {vals}")

        # Calculer le nombre total de combinaisons (ou max_total_tests)
        try:
            total_combos = min(max_total_tests, 
                              len(list(product(*param_values_list))) if all(param_values_list) else 0)
        except:
            total_combos = max_total_tests

        self._log(f"\nDÉBUT OPTIMISATION → {total_combos} tests max\n")

        combo_iterator = product(*param_values_list)
        for combo_index, combo in enumerate(islice(combo_iterator, max_total_tests), 1):
            param_dict = dict(zip(self.param_order, combo))
            pnl = self._simulate_strategy(param_dict)
            row = {"pnl": pnl, **param_dict}

            # CSV
            file_empty = os.stat(self.results_file).st_size == 0
            with open(self.results_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=row.keys())
                if file_empty:
                    writer.writeheader()
                writer.writerow(row)

            self.results.append((pnl, param_dict))

            # AFFICHAGE : (val1, val2, ...) → PnL = XXX.XX €
            values_str = self._format_values_only(param_dict)
            self._log(f"TEST {combo_index:>{len(str(total_combos))}}/{total_combos} | "
                      f"({values_str}) → PnL = {pnl:>7.2f} €")

        # Top N
        self.results.sort(reverse=True, key=lambda x: x[0])
        top_results = self.results[:top_n]
        with open(self.best_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["pnl"] + self.param_order
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for pnl, params in top_results:
                writer.writerow({"pnl": pnl, **params})

        self._log(f"\nOPTIMISATION TERMINÉE !")
        self._log(f"{len(self.results)} tests réalisés | Top {top_n} → {self.best_file}")


# ===================================================
# EXÉCUTION
# ===================================================
if __name__ == "__main__":
    optimizer = ParamOptimizer()

    best_params = {
        "trade_start_hour": {"initial_value": "09:30", "min_value": "09:30", "max_value": "12:30", "step": 60},
        "trade_cutoff_hour": {"initial_value": "13:45", "min_value": "13:45", "max_value": "17:45", "step": 60},
        "min_market_pnl": {"initial_value": 43.0, "min_value": 43.0, "max_value": 183.0, "step": 20.0},
        "take_profit_market_pnl": {"initial_value": 70.0, "min_value": 70.0, "max_value": 190.0, "step": 20.0},
        "trail_stop_market_pnl": {"initial_value": 1000, "min_value": 0, "max_value": 2000, "step": 100},
        "min_escape_time": {"initial_value": 83.0, "min_value": 0, "max_value": 200.0, "step": 30},
        "max_trades_per_day": {"initial_value": 10, "min_value": 10, "max_value": 50, "step": 10},
        "trade_value_eur": {"initial_value": 100.0, "min_value": 100.0, "max_value": 200.0, "step": 25.0},
        "top_n_threshold": {"initial_value": 1, "min_value": 0, "max_value": 10, "step": 1},
        "stop_echappee_threshold": {"initial_value": 1, "min_value": 0, "max_value": 5, "step": 0.5},
        "start_echappee_threshold": {"initial_value": 1.5, "min_value": 0, "max_value": 5, "step": 0.5},
        "trade_interval_minutes": {"initial_value": 150000, "min_value": 150000, "max_value": 150000, "step": 50},
        "max_pnl_timeout_minutes": {"initial_value": 6000.0, "min_value": 6000.0, "max_value": 6000.0, "step": 6000.0}
    }

    optimizer.save_params(best_params)
    optimizer.load_params()
    optimizer.run_full_optimization(max_tests_per_param=3, top_n=10, max_total_tests=1000)