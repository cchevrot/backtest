"""
ParamOptimizer - Optimiseur de paramètres pour stratégies de trading.

★★★ NIVEAU 1 : OPTIMISATION MULTI-PARAMÈTRES ★★★

Permet de tester systématiquement des combinaisons de paramètres
pour trouver la configuration optimale d'une stratégie.

Hiérarchie complète :
ParamOptimizer._test_params_on_all_files()      [Niveau 1 - Optimisation]
    └─> MultiFileSimulator.run_all_files()       [Niveau 2 - Multi-fichiers]
          └─> SingleFileSimulator.run_single_file() [Niveau 3 - Fichier unique]
"""

import json
import csv
import os
import glob
from datetime import datetime, timedelta
from itertools import product, islice
from multi_file_simulator import MultiFileSimulator


class ParamOptimizer:
    """★★★ NIVEAU 1 ★★★ Optimise les paramètres d'une stratégie par recherche exhaustive."""
    
    def __init__(self, json_file="params.json", results_file="results.csv",
                 best_file="best_results.csv", log_file="optimizer.log",
                 data_files=None, parallel=True, verbose=False):
        """
        Initialise l'optimiseur.
        
        Args:
            json_file: Fichier JSON contenant les paramètres à optimiser
            results_file: Fichier CSV pour stocker tous les résultats
            best_file: Fichier CSV pour stocker les meilleurs résultats
            log_file: Fichier de log
            data_files: Liste des fichiers de données (None = auto-détection)
            parallel: Utiliser le mode parallèle pour les simulations
            verbose: Mode d'affichage (True=détaillé, False=condensé CSV)
        """
        self.json_file = json_file
        self.results_file = results_file
        self.best_file = best_file
        self.log_file = log_file
        self.params = {}
        self.results = []
        self.param_order = []
        
        if data_files is None:
            data_files = glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        
        self.multi_file_simulator = MultiFileSimulator(
            data_files, 
            parallel=parallel, 
            verbose=verbose
        )

    # ═══════════════════════════════════════════════════════════
    # LOGGING & FORMATTING
    # ═══════════════════════════════════════════════════════════
    
    def _log(self, msg: str):
        """Enregistre un message dans le log et l'affiche."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _format_param_values(self, param_dict: dict) -> str:
        """Retourne une chaîne avec seulement les valeurs des paramètres."""
        return ", ".join(str(param_dict[name]) for name in self.param_order)

    # ═══════════════════════════════════════════════════════════
    # PARAM CONFIGURATION PERSISTENCE
    # ═══════════════════════════════════════════════════════════
    
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

    # ═══════════════════════════════════════════════════════════
    # SIMULATION EXECUTION (NIVEAU 1)
    # ═══════════════════════════════════════════════════════════
    
    def _test_params_on_all_files(self, param_values: dict) -> float:
        """
        ★★★ NIVEAU 1 : OPTIMISATION MULTI-PARAMÈTRES ★★★
        Teste UNE combinaison de paramètres sur TOUS les fichiers .lz4
        
        Args:
            param_values: Dictionnaire des paramètres de la stratégie
            
        Returns:
            PnL total agrégé de tous les fichiers
        """
        metrics = self.multi_file_simulator.run_all_files(param_values)
        return metrics['total_pnl']

    # ═══════════════════════════════════════════════════════════
    # VALUE GENERATION
    # ═══════════════════════════════════════════════════════════
    
    def _generate_time_values(self, initial: str, min_val: str, max_val: str, 
                             step: int, max_tests: int) -> list:
        """Génère des valeurs de temps (HH:MM) en commençant par la valeur initiale."""
        start_time = datetime.strptime(str(initial), "%H:%M")
        min_time = datetime.strptime(min_val, "%H:%M")
        max_time = datetime.strptime(max_val, "%H:%M")
        step_delta = timedelta(minutes=int(step))
        
        # Si un seul test, retourner uniquement la valeur initiale
        if max_tests == 1:
            return [initial]
        
        # Commencer par la valeur initiale
        values = [start_time.strftime("%H:%M")]
        
        # Alterner entre avant et après pour explorer de manière équilibrée
        current_before = start_time - step_delta
        current_after = start_time + step_delta
        
        while len(values) < max_tests:
            # Ajouter une valeur après si possible
            if current_after <= max_time and len(values) < max_tests:
                values.append(current_after.strftime("%H:%M"))
                current_after += step_delta
            
            # Ajouter une valeur avant si possible
            if current_before >= min_time and len(values) < max_tests:
                values.append(current_before.strftime("%H:%M"))
                current_before -= step_delta
            
            # Si on ne peut plus ajouter ni avant ni après, sortir
            if current_after > max_time and current_before < min_time:
                break
        
        return values

    def _generate_numeric_values(self, initial: float, min_val: float, max_val: float,
                                 step: float, max_tests: int) -> list:
        """Génère des valeurs numériques en commençant par la valeur initiale."""
        initial_val = float(initial)
        min_num = float(min_val)
        max_num = float(max_val)
        step_num = float(step)
        
        # Si un seul test, retourner uniquement la valeur initiale
        if max_tests == 1:
            return [round(initial_val, 2)]
        
        # Commencer par la valeur initiale
        values = [round(initial_val, 2)]
        
        # Alterner entre avant et après pour explorer de manière équilibrée
        current_before = initial_val - step_num
        current_after = initial_val + step_num
        
        while len(values) < max_tests:
            # Ajouter une valeur après si possible
            if current_after <= max_num and len(values) < max_tests:
                values.append(round(current_after, 2))
                current_after += step_num
            
            # Ajouter une valeur avant si possible
            if current_before >= min_num and len(values) < max_tests:
                values.append(round(current_before, 2))
                current_before -= step_num
            
            # Si on ne peut plus ajouter ni avant ni après, sortir
            if current_after > max_num and current_before < min_num:
                break
        
        return values

    def _generate_values(self, settings: dict, max_tests: int = 5) -> list:
        """
        Génère une liste de valeurs à tester pour un paramètre.
        Commence TOUJOURS par la valeur initiale, puis explore autour.
        
        Args:
            settings: Configuration du paramètre (min, max, step)
            max_tests: Nombre maximum de valeurs à générer
            
        Returns:
            Liste des valeurs à tester (commence TOUJOURS par initial_value)
        """
        initial = settings["initial_value"]
        min_val = settings["min_value"]
        max_val = settings["max_value"]
        step = settings["step"]

        # Gestion des horaires (format HH:MM)
        if isinstance(initial, str) and ":" in initial:
            return self._generate_time_values(initial, min_val, max_val, step, max_tests)
        else:
            return self._generate_numeric_values(initial, min_val, max_val, step, max_tests)

    # ═══════════════════════════════════════════════════════════
    # RESULTS PERSISTENCE
    # ═══════════════════════════════════════════════════════════
    
    def _write_result_to_csv(self, row: dict):
        """Écrit un résultat dans le fichier CSV."""
        file_empty = not os.path.exists(self.results_file) or \
                     os.stat(self.results_file).st_size == 0
        
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

    # ═══════════════════════════════════════════════════════════
    # OPTIMIZATION ENGINE
    # ═════════════════════════════════════════════════════════== 
    
    def _calculate_total_combos(self, param_values_list: list, max_total_tests: int) -> int:
        """Calcule le nombre total de combinaisons à tester."""
        try:
            total_possible = len(list(product(*param_values_list))) if all(param_values_list) else 0
            return min(max_total_tests, total_possible)
        except Exception:
            return max_total_tests

    def _generate_all_param_values(self, max_tests_per_param: int) -> list:
        """Génère les valeurs pour tous les paramètres."""
        param_values_list = []
        for name in self.param_order:
            vals = self._generate_values(self.params[name], max_tests=max_tests_per_param)
            param_values_list.append(vals)
            self._log(f"{name}: {vals}")
        return param_values_list

    def _test_single_combination(self, combo_index: int, total_combos: int, 
                                combo: tuple) -> tuple:
        """Teste une combinaison de paramètres et retourne (pnl, param_dict)."""
        param_dict = dict(zip(self.param_order, combo))
        pnl = self._test_params_on_all_files(param_dict)
        
        # Enregistrer le résultat
        row = {"pnl": pnl, **param_dict}
        self._write_result_to_csv(row)
        
        # Afficher le progrès
        values_str = self._format_param_values(param_dict)
        self._log(f"TEST {combo_index:>{len(str(total_combos))}}/{total_combos} | "
                  f"({values_str}) → PnL = {pnl:>7.2f} €")
        
        return (pnl, param_dict)

    def run_full_optimization(self, max_tests_per_param: int = 5, 
                             top_n: int = 10, max_total_tests: int = 1000):
        """
        Lance l'optimisation complète des paramètres.
        LE PREMIER TEST UTILISERA TOUJOURS TOUTES LES VALEURS INITIALES.
        
        Args:
            max_tests_per_param: Nombre de valeurs à tester par paramètre
            top_n: Nombre de meilleurs résultats à sauvegarder
            max_total_tests: Nombre maximum de combinaisons à tester
        """
        if not self.params:
            self.load_params()

        self._cleanup_files()

        # Générer les valeurs pour chaque paramètre
        param_values_list = self._generate_all_param_values(max_tests_per_param)
        
        # Calculer le nombre total de combinaisons
        total_combos = self._calculate_total_combos(param_values_list, max_total_tests)

        self._log(f"\nDÉBUT OPTIMISATION → {total_combos} tests max")
        self._log(f"Mode: {'Parallèle' if self.multi_file_simulator.parallel else 'Séquentiel'}")
        self._log(f"Verbose: {'Oui' if self.multi_file_simulator.verbose else 'Non (CSV compact)'}")
        self._log(f"⭐ Premier test = TOUTES les valeurs initiales\n")

        # Tester toutes les combinaisons
        combo_iterator = product(*param_values_list)
        for combo_index, combo in enumerate(islice(combo_iterator, max_total_tests), 1):
            result = self._test_single_combination(combo_index, total_combos, combo)
            self.results.append(result)

        # Sauvegarder les meilleurs résultats
        self._save_best_results(top_n)

        self._log(f"\nOPTIMISATION TERMINÉE !")
        self._log(f"{len(self.results)} tests réalisés | Top {top_n} → {self.best_file}")


# ═══════════════════════════════════════════════════════════
# DEFAULT PARAMETER CONFIGURATION AVEC VARIATIONS
# ═══════════════════════════════════════════════════════════

DEFAULT_PARAMS_CONFIG = {
    "trade_start_hour": {
        "initial_value": "09:30",
        "min_value": "09:00",      # -30 min
        "max_value": "10:00",      # +30 min
        "step": 15                 # Pas de 15 minutes
    },
    "trade_cutoff_hour": {
        "initial_value": "13:45",
        "min_value": "13:00",      # -45 min
        "max_value": "15:00",      # +75 min
        "step": 15                 # Pas de 15 minutes
    },
    "min_market_pnl": {
        "initial_value": 43.0,
        "min_value": 30.0,         # -13€
        "max_value": 60.0,         # +17€
        "step": 5.0                # Pas de 5€
    },
    "take_profit_market_pnl": {
        "initial_value": 70.0,
        "min_value": 50.0,         # -20€
        "max_value": 100.0,        # +30€
        "step": 10.0               # Pas de 10€
    },
    "trail_stop_market_pnl": {
        "initial_value": 1040,
        "min_value": 800,          # -240€
        "max_value": 1500,         # +460€
        "step": 100                # Pas de 100€
    },
    "min_escape_time": {
        "initial_value": 83.0,
        "min_value": 60.0,         # -23 sec
        "max_value": 120.0,        # +37 sec
        "step": 10.0               # Pas de 10 secondes
    },
    "max_trades_per_day": {
        "initial_value": 10,
        "min_value": 5,            # -5 trades
        "max_value": 20,           # +10 trades
        "step": 2                  # Pas de 2 trades
    },
    "trade_value_eur": {
        "initial_value": 100.0,
        "min_value": 50.0,         # -50€
        "max_value": 200.0,        # +100€
        "step": 25.0               # Pas de 25€
    },
    "top_n_threshold": {
        "initial_value": 1,
        "min_value": 1,
        "max_value": 5,            # +4
        "step": 1
    },
    "stop_echappee_threshold": {
        "initial_value": 1,
        "min_value": 1,
        "max_value": 3,            # +2
        "step": 0.5                # Pas de 0.5
    },
    "start_echappee_threshold": {
        "initial_value": 1.5,
        "min_value": 1.0,          # -0.5
        "max_value": 3.0,          # +1.5
        "step": 0.5                # Pas de 0.5
    },
    "trade_interval_minutes": {
        "initial_value": 150000,
        "min_value": 100000,       # -50k
        "max_value": 200000,       # +50k
        "step": 25000              # Pas de 25k
    },
    "max_pnl_timeout_minutes": {
        "initial_value": 6000.0,
        "min_value": 4000.0,       # -2000
        "max_value": 8000.0,       # +2000
        "step": 1000.0             # Pas de 1000
    }
}


# ═══════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════

def main():
    """Point d'entrée pour l'optimisation."""
    optimizer = ParamOptimizer(parallel=True, verbose=False)
    
    optimizer.save_params(DEFAULT_PARAMS_CONFIG)
    optimizer.load_params()
    optimizer.run_full_optimization(
        max_tests_per_param=3,     # 3 valeurs par paramètre
        top_n=10,                  # Garde les 10 meilleurs
        max_total_tests=1000       # Maximum 1000 tests
    )


if __name__ == "__main__":
    main()