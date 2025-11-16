import json
import csv
import os
import glob
from datetime import datetime, timedelta
from multi_file_simulator import MultiFileSimulator


class ParamOptimizer:
    """Optimisation séquentielle: un paramètre à la fois, dans l'ordre de priorité."""

    def __init__(self, json_file="params.json", results_file="results.csv",
                 best_file="best_results.csv", data_files=None, parallel=True):
        self.json_file = json_file
        self.results_file = results_file
        self.best_file = best_file
        
        # Initialisation du simulateur
        data_files = data_files or glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        data_files = [data_files[0]] if data_files else []
        self.multi_file_simulator = MultiFileSimulator(data_files, parallel=parallel, verbose=False)
        
        self.params = {}
        self.param_order = []
        self.all_results = []

    # ========== Gestion des paramètres ==========
    
    def save_params(self, params: dict):
        with open(self.json_file, "w") as f:
            json.dump(params, f, indent=4)

    def load_params(self):
        with open(self.json_file) as f:
            self.params = json.load(f)
        # Tri par priorité croissante
        self.param_order = sorted(self.params.keys(), 
                                  key=lambda k: self.params[k].get('priority', 999))

    # ========== Génération des valeurs ==========
    
    def _generate_values(self, settings: dict, max_tests: int) -> list:
        """Génère des valeurs autour de la valeur initiale."""
        if max_tests == 1:
            return [settings["initial_value"]]
        
        is_time = isinstance(settings["initial_value"], str) and ":" in settings["initial_value"]
        
        if is_time:
            initial = datetime.strptime(str(settings["initial_value"]), "%H:%M")
            min_val = datetime.strptime(settings["min_value"], "%H:%M")
            max_val = datetime.strptime(settings["max_value"], "%H:%M")
            step = timedelta(minutes=int(settings["step"]))
            fmt = lambda x: x.strftime("%H:%M")
        else:
            initial = float(settings["initial_value"])
            min_val = float(settings["min_value"])
            max_val = float(settings["max_value"])
            step = float(settings["step"])
            fmt = lambda x: round(x, 2)
        
        # Génération alternée autour de la valeur initiale
        values = [fmt(initial)]
        before, after = initial - step, initial + step
        
        while len(values) < max_tests:
            if after <= max_val:
                values.append(fmt(after))
                after += step
            if len(values) >= max_tests:
                break
            if before >= min_val:
                values.append(fmt(before))
                before -= step
            if before < min_val and after > max_val:
                break
        
        return values

    # ========== Simulation ==========
    
    def _test_params(self, param_values: dict) -> float:
        return self.multi_file_simulator.run_all_files(param_values)['total_pnl']

    def _write_result(self, row: dict):
        file_exists = os.path.exists(self.results_file) and os.stat(self.results_file).st_size > 0
        with open(self.results_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def _save_best(self, top_n: int):
        self.all_results.sort(reverse=True, key=lambda x: x[0])
        with open(self.best_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["pnl"] + self.param_order)
            writer.writeheader()
            for pnl, params in self.all_results[:top_n]:
                writer.writerow({"pnl": pnl, **params})

    # ========== Optimisation séquentielle ==========
    
    def run_optimization(self, max_tests_per_param: int = 5):
        """
        Optimisation séquentielle:
        1. Commence avec la config par défaut
        2. Pour chaque paramètre (ordre de priorité):
           - Teste toutes les valeurs possibles
           - Garde la meilleure valeur
           - Passe au paramètre suivant avec cette valeur fixée
        """
        self.load_params()
        
        # Nettoyage
        for f in [self.results_file, self.best_file]:
            open(f, "w").close()
        
        # Configuration de départ: toutes les valeurs initiales
        current_best_config = {name: self.params[name]["initial_value"] 
                               for name in self.param_order}
        current_best_pnl = self._test_params(current_best_config)
        
        print(f"🎯 Config initiale: PnL = {current_best_pnl:.2f}")
        self.all_results.append((current_best_pnl, current_best_config.copy()))
        self._write_result({"pnl": current_best_pnl, **current_best_config})
        
        # Optimisation séquentielle de chaque paramètre
        for param_name in self.param_order:
            priority = self.params[param_name]["priority"]
            print(f"\n{'='*80}")
            print(f"🔍 Optimisation de '{param_name}' (priorité {priority})")
            print(f"{'='*80}")
            
            # Génération des valeurs à tester
            test_values = self._generate_values(self.params[param_name], max_tests_per_param)
            print(f"📋 Valeurs à tester: {test_values}")
            
            param_results = []
            
            # Test de chaque valeur avec la config actuelle figée
            for value in test_values:
                test_config = current_best_config.copy()
                test_config[param_name] = value
                
                pnl = self._test_params(test_config)
                param_results.append((pnl, value, test_config.copy()))
                self.all_results.append((pnl, test_config))
                self._write_result({"pnl": pnl, **test_config})
                
                print(f"  ✓ {param_name}={value} → PnL={pnl:.2f}")
            
            # Sélection de la meilleure valeur pour ce paramètre
            param_results.sort(reverse=True, key=lambda x: x[0])
            best_pnl, best_value, best_config = param_results[0]
            
            # Mise à jour de la config de référence
            if best_pnl > current_best_pnl:
                print(f"\n✅ AMÉLIORATION: {param_name}={best_value} (PnL: {current_best_pnl:.2f} → {best_pnl:.2f})")
                current_best_config = best_config
                current_best_pnl = best_pnl
            else:
                print(f"\n➡️  Meilleure valeur: {param_name}={best_value} (PnL={best_pnl:.2f}, pas d'amélioration)")
                # On garde quand même la meilleure valeur trouvée pour ce paramètre
                current_best_config[param_name] = best_value
        
        # Sauvegarde finale
        self._save_best(top_n=10)
        print(f"\n{'='*80}")
        print(f"🏁 OPTIMISATION TERMINÉE")
        print(f"📈 PnL final: {current_best_pnl:.2f}")
        print(f"📁 Résultats: {self.best_file}")
        print(f"{'='*80}")


# ========== Configuration ==========

DEFAULT_PARAMS = {
    # Priorité 1: Paramètres critiques de profit/perte
    "take_profit_market_pnl": {"initial_value": 70.0, "min_value": 50.0, "max_value": 100.0, "step": 10.0, "priority": 1},
    "trail_stop_market_pnl": {"initial_value": 1040, "min_value": 800, "max_value": 1500, "step": 100, "priority": 1},
    "min_market_pnl": {"initial_value": 43.0, "min_value": 30.0, "max_value": 60.0, "step": 5.0, "priority": 1},
    
    # Priorité 2: Temporels
    "trade_start_hour": {"initial_value": "09:30", "min_value": "09:00", "max_value": "10:00", "step": 15, "priority": 2},
    "trade_cutoff_hour": {"initial_value": "13:45", "min_value": "13:00", "max_value": "15:00", "step": 15, "priority": 2},
    "min_escape_time": {"initial_value": 83.0, "min_value": 60.0, "max_value": 120.0, "step": 10.0, "priority": 2},
    "max_trades_per_day": {"initial_value": 10, "min_value": 5, "max_value": 20, "step": 2, "priority": 2},
    
    # Priorité 3: Seuils
    "stop_echappee_threshold": {"initial_value": 1, "min_value": 1, "max_value": 3, "step": 0.5, "priority": 3},
    "start_echappee_threshold": {"initial_value": 1.5, "min_value": 1.0, "max_value": 3.0, "step": 0.5, "priority": 3},
    "top_n_threshold": {"initial_value": 1, "min_value": 1, "max_value": 5, "step": 1, "priority": 3},
    
    # Priorité 4: Gestion fine
    "trade_value_eur": {"initial_value": 100.0, "min_value": 50.0, "max_value": 200.0, "step": 25.0, "priority": 4},
    "trade_interval_minutes": {"initial_value": 150000, "min_value": 100000, "max_value": 200000, "step": 25000, "priority": 4},
    "max_pnl_timeout_minutes": {"initial_value": 6000.0, "min_value": 4000.0, "max_value": 8000.0, "step": 1000.0, "priority": 4},
}


def main():
    optimizer = ParamOptimizer(parallel=True)
    optimizer.save_params(DEFAULT_PARAMS)
    optimizer.run_optimization(max_tests_per_param=3)


if __name__ == "__main__":
    main()