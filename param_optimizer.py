"""
ParamOptimizer - Optimiseur de paramètres pour stratégies de trading.

Permet de tester systématiquement des combinaisons de paramètres
pour trouver la configuration optimale d'une stratégie.
"""

import json
import csv
import os
import glob
from datetime import datetime, timedelta
from itertools import product, islice
from simulation_runner import SimulationRunner


class ParamOptimizer:
    """Optimise les paramètres d'une stratégie de trading par recherche exhaustive."""
    
    def __init__(self, json_file="params.json", results_file="results.csv",
                 best_file="best_results.csv", log_file="optimizer.log",
                 data_files=None, parallel=False):
        """
        Initialise l'optimiseur.
        
        Args:
            json_file: Fichier JSON contenant les paramètres à optimiser
            results_file: Fichier CSV pour stocker tous les résultats
            best_file: Fichier CSV pour stocker les meilleurs résultats
            log_file: Fichier de log
            data_files: Liste des fichiers de données (None = auto-détection)
            parallel: Utiliser le mode parallèle pour les simulations
        """
        self.json_file = json_file
        self.results_file = results_file
        self.best_file = best_file
        self.log_file = log_file
        self.params = {}
        self.results = []
        self.param_order = []
        
        # Configuration du runner de simulation
        if data_files is None:
            data_files = glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        self.simulation_runner = SimulationRunner(data_files, parallel=parallel)

    def _log(self, msg: str):
        """Enregistre un message dans le log et l'affiche."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _format_values_only(self, param_dict: dict) -> str:
        """Retourne une chaîne avec seulement les valeurs des paramètres."""
        return ", ".join(str(param_dict[name]) for name in self.param_order)

    def save_params(self, params: dict):
        """Sauvegarde les paramètres dans un fichier JSON."""
        with open(self.json_file, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=4)
        self._log(f"Paramètres sauvegardés dans {self.json_file}")

    def load_params(self):
        """Charge les paramètres depuis le fichier JSON."""
        if not os.path.exists(self.json_file):
            raise FileNotFoundError(f"Fichier {self.json_file} introuvable.")
        
        with open(self.json_file, "r", encoding="utf-8") as f:
            self.params = json.load(f)
        
        self.param_order = list(self.params.keys())
        self._log(f"Paramètres chargés ({len(self.params)} paramètres)")

    def _simulate_strategy(self, param_values: dict) -> float:
        """
        ★★★ NIVEAU 1 : OPTIMISATION MULTI-PARAMÈTRES ★★★
        Teste UNE combinaison de paramètres sur TOUS les fichiers .lz4
        
        Hiérarchie des appels :
        ParamOptimizer._simulate_strategy() 
            └─> SimulationRunner.run_simulation()  [TOUS les fichiers]
                  └─> SingleFileSimulator.run()    [UN fichier]
        
        Args:
            param_values: Dictionnaire des paramètres de la stratégie
            
        Returns:
            PnL total agrégé de tous les fichiers
        """
        # Appel au niveau 2 : exécute la simulation sur TOUS les fichiers
        metrics = self.simulation_runner.run_simulation(param_values)
        return metrics['total_pnl']

    def _generate_values(self, settings: dict, max_tests: int = 5) -> list:
        """
        Génère une liste de valeurs à tester pour un paramètre.
        Commence par la valeur initiale, puis explore autour.
        
        Args:
            settings: Configuration du paramètre (min, max, step)
            max_tests: Nombre maximum de valeurs à générer
            
        Returns:
            Liste des valeurs à tester (commence par initial_value)
        """
        initial = settings["initial_value"]
        min_val = settings["min_value"]
        max_val = settings["max_value"]
        step = settings["step"]
        values = []

        # Gestion des horaires (format HH:MM)
        if isinstance(initial, str) and ":" in initial:
            start_time = datetime.strptime(str(initial), "%H:%M")
            min_time = datetime.strptime(min_val, "%H:%M")
            max_time = datetime.strptime(max_val, "%H:%M")
            step_delta = timedelta(minutes=int(step))
            
            # Commencer par la valeur initiale
            values.append(start_time.strftime("%H:%M"))
            
            # Ajouter les valeurs avant
            current = start_time - step_delta
            before_values = []
            while current >= min_time and len(values) + len(before_values) < max_tests:
                before_values.insert(0, current.strftime("%H:%M"))
                current -= step_delta
            
            # Ajouter les valeurs après
            current = start_time + step_delta
            after_values = []
            while current <= max_time and len(values) + len(before_values) + len(after_values) < max_tests:
                after_values.append(current.strftime("%H:%M"))
                current += step_delta
            
            values = [initial] + after_values[:max_tests-1] if max_tests == 1 else before_values + values + after_values
            values = values[:max_tests]
        else:
            # Gestion des valeurs numériques - commencer par initial
            initial_val = float(initial)
            min_num = float(min_val)
            max_num = float(max_val)
            step_num = float(step)
            
            # Commencer par la valeur initiale
            values.append(round(initial_val, 2))
            
            # Ajouter les valeurs avant
            current = initial_val - step_num
            before_values = []
            while current >= min_num and len(values) + len(before_values) < max_tests:
                before_values.insert(0, round(current, 2))
                current -= step_num
            
            # Ajouter les valeurs après
            current = initial_val + step_num
            after_values = []
            while current <= max_num and len(values) + len(before_values) + len(after_values) < max_tests:
                after_values.append(round(current, 2))
                current += step_num
            
            values = [round(initial_val, 2)] + after_values[:max_tests-1] if max_tests == 1 else before_values + values + after_values
            values = values[:max_tests]

        return values

    def _write_result_to_csv(self, row: dict):
        """Écrit un résultat dans le fichier CSV."""
        file_empty = not os.path.exists(self.results_file) or os.stat(self.results_file).st_size == 0
        
        with open(self.results_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if file_empty:
                writer.writeheader()
            writer.writerow(row)

    def _save_best_results(self, top_n: int):
        """Sauvegarde les meilleurs résultats dans un fichier CSV."""
        self.results.sort(reverse=True, key=lambda x: x[0])
        top_results = self.results[:top_n]
        
        with open(self.best_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["pnl"] + self.param_order
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for pnl, params in top_results:
                writer.writerow({"pnl": pnl, **params})

    def _cleanup_files(self):
        """Nettoie les fichiers de résultats existants."""
        for file in [self.results_file, self.best_file, self.log_file]:
            open(file, "w").close()

    def run_full_optimization(self, max_tests_per_param: int = 5, 
                             top_n: int = 10, max_total_tests: int = 1000):
        """
        Lance l'optimisation complète des paramètres.
        
        Args:
            max_tests_per_param: Nombre de valeurs à tester par paramètre
            top_n: Nombre de meilleurs résultats à sauvegarder
            max_total_tests: Nombre maximum de combinaisons à tester
        """
        if not self.params:
            self.load_params()

        self._cleanup_files()

        # Générer les valeurs pour chaque paramètre
        param_values_list = []
        for name in self.param_order:
            vals = self._generate_values(self.params[name], max_tests=max_tests_per_param)
            param_values_list.append(vals)
            self._log(f"{name}: {vals}")

        # Calculer le nombre total de combinaisons
        try:
            total_possible = len(list(product(*param_values_list))) if all(param_values_list) else 0
            total_combos = min(max_total_tests, total_possible)
        except Exception:
            total_combos = max_total_tests

        self._log(f"\nDÉBUT OPTIMISATION → {total_combos} tests max")
        self._log(f"Mode: {'Parallèle' if self.simulation_runner.parallel else 'Séquentiel'}\n")

        # Tester toutes les combinaisons
        combo_iterator = product(*param_values_list)
        for combo_index, combo in enumerate(islice(combo_iterator, max_total_tests), 1):
            param_dict = dict(zip(self.param_order, combo))
            pnl = self._simulate_strategy(param_dict)
            
            # Enregistrer le résultat
            row = {"pnl": pnl, **param_dict}
            self._write_result_to_csv(row)
            self.results.append((pnl, param_dict))

            # Afficher le progrès
            values_str = self._format_values_only(param_dict)
            self._log(f"TEST {combo_index:>{len(str(total_combos))}}/{total_combos} | "
                      f"({values_str}) → PnL = {pnl:>7.2f} €")

        # Sauvegarder les meilleurs résultats
        self._save_best_results(top_n)

        self._log(f"\nOPTIMISATION TERMINÉE !")
        self._log(f"{len(self.results)} tests réalisés | Top {top_n} → {self.best_file}")


def main():
    """Point d'entrée pour l'optimisation."""
    optimizer = ParamOptimizer(parallel=False)

    # Configuration des paramètres à optimiser
    params_config = {
        "trade_start_hour": {
            "initial_value": "09:30",
            "min_value": "09:30",
            "max_value": "12:30",
            "step": 60
        },
        "trade_cutoff_hour": {
            "initial_value": "13:45",
            "min_value": "13:45",
            "max_value": "17:45",
            "step": 60
        },
        "min_market_pnl": {
            "initial_value": 43.0,
            "min_value": 43.0,
            "max_value": 183.0,
            "step": 20.0
        },
        "take_profit_market_pnl": {
            "initial_value": 70.0,
            "min_value": 70.0,
            "max_value": 190.0,
            "step": 20.0
        },
        "trail_stop_market_pnl": {
            "initial_value": 1000,
            "min_value": 0,
            "max_value": 2000,
            "step": 100
        },
        "min_escape_time": {
            "initial_value": 83.0,
            "min_value": 0,
            "max_value": 200.0,
            "step": 30
        },
        "max_trades_per_day": {
            "initial_value": 10,
            "min_value": 10,
            "max_value": 50,
            "step": 10
        },
        "trade_value_eur": {
            "initial_value": 100.0,
            "min_value": 100.0,
            "max_value": 200.0,
            "step": 25.0
        },
        "top_n_threshold": {
            "initial_value": 1,
            "min_value": 0,
            "max_value": 10,
            "step": 1
        },
        "stop_echappee_threshold": {
            "initial_value": 1,
            "min_value": 0,
            "max_value": 5,
            "step": 0.5
        },
        "start_echappee_threshold": {
            "initial_value": 1.5,
            "min_value": 0,
            "max_value": 5,
            "step": 0.5
        },
        "trade_interval_minutes": {
            "initial_value": 150000,
            "min_value": 150000,
            "max_value": 150000,
            "step": 50
        },
        "max_pnl_timeout_minutes": {
            "initial_value": 6000.0,
            "min_value": 6000.0,
            "max_value": 6000.0,
            "step": 6000.0
        }
    }

    optimizer.save_params(params_config)
    optimizer.load_params()
    optimizer.run_full_optimization(max_tests_per_param=3, top_n=10, max_total_tests=1000)


if __name__ == "__main__":
    main()
