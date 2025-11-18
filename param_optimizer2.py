import json
import csv
import os
import glob
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from multi_file_simulator import MultiFileSimulator


@dataclass
class ParamConfig:
    """Configuration d'un paramètre à optimiser."""
    initial_value: Any
    min_value: Any
    max_value: Any
    step: Any
    priority: int
    enabled: bool = True


@dataclass
class OptimizationResult:
    """Résultat d'une optimisation."""
    pnl: float
    config: Dict[str, Any]


class ConfigCache:
    """Gestionnaire de cache des configurations testées."""
    
    def __init__(self, results_file: str):
        self.results_file = results_file
        self.cache: Dict[str, float] = {}
        self._load_from_csv()
    
    def _config_to_key(self, config: Dict[str, Any]) -> str:
        """Convertit une config en clé unique (JSON trié)."""
        return json.dumps(config, sort_keys=True)
    
    def _load_from_csv(self) -> None:
        """Charge toutes les configurations depuis results.csv."""
        if not os.path.exists(self.results_file):
            print("📂 Aucun historique trouvé, démarrage avec cache vide")
            return
        
        try:
            with open(self.results_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pnl = float(row.pop('pnl'))
                    config = self._parse_config_values(row)
                    self.cache[self._config_to_key(config)] = pnl
            
            print(f"✅ Cache chargé: {len(self.cache)} configurations depuis {self.results_file}")
        except Exception as e:
            print(f"⚠️  Erreur lors du chargement du cache: {e}")
            self.cache = {}
    
    @staticmethod
    def _parse_config_values(row: Dict[str, str]) -> Dict[str, Any]:
        """Convertit les valeurs CSV en types appropriés."""
        config = {}
        for key, value in row.items():
            try:
                config[key] = int(value)
            except ValueError:
                try:
                    config[key] = float(value)
                except ValueError:
                    config[key] = value
        return config
    
    def get(self, config: Dict[str, Any]) -> Optional[float]:
        """Récupère le PnL d'une config si elle existe dans le cache."""
        return self.cache.get(self._config_to_key(config))
    
    def add(self, config: Dict[str, Any], pnl: float) -> None:
        """Ajoute une config au cache."""
        self.cache[self._config_to_key(config)] = pnl
    
    def contains(self, config: Dict[str, Any]) -> bool:
        """Vérifie si une config est dans le cache."""
        return self._config_to_key(config) in self.cache


class ValueGenerator:
    """Génère des valeurs de test pour les paramètres."""
    
    @staticmethod
    def generate_around_value(param_config: ParamConfig, center_value: Any, 
                            max_tests: int, expand_search: bool = False) -> List[Any]:
        """
        Génère des valeurs autour d'une valeur centrale.
        
        Args:
            param_config: Configuration du paramètre
            center_value: Valeur centrale autour de laquelle générer
            max_tests: Nombre maximum de valeurs à générer
            expand_search: Si True, élargit la recherche au-delà de max_tests
        """
        if max_tests == 1 and not expand_search:
            return [center_value]
        
        is_time = isinstance(center_value, str) and ":" in center_value
        
        if is_time:
            return ValueGenerator._generate_time_values(
                param_config, center_value, max_tests, expand_search
            )
        else:
            return ValueGenerator._generate_numeric_values(
                param_config, center_value, max_tests, expand_search
            )
    
    @staticmethod
    def _generate_time_values(param_config: ParamConfig, center_value: str,
                            max_tests: int, expand_search: bool) -> List[str]:
        """Génère des valeurs temporelles."""
        current = datetime.strptime(center_value, "%H:%M")
        min_val = datetime.strptime(param_config.min_value, "%H:%M")
        max_val = datetime.strptime(param_config.max_value, "%H:%M")
        step = timedelta(minutes=int(param_config.step))
        
        values = [current.strftime("%H:%M")]
        before, after = current - step, current + step
        max_iterations = 1000 if expand_search else max_tests
        
        while len(values) < max_iterations:
            if after <= max_val:
                values.append(after.strftime("%H:%M"))
                after += step
            if len(values) >= max_tests and not expand_search:
                break
            if before >= min_val:
                values.append(before.strftime("%H:%M"))
                before -= step
            if before < min_val and after > max_val:
                break
        
        return values
    
    @staticmethod
    def _generate_numeric_values(param_config: ParamConfig, center_value: float,
                               max_tests: int, expand_search: bool) -> List[float]:
        """Génère des valeurs numériques."""
        current = float(center_value)
        min_val = float(param_config.min_value)
        max_val = float(param_config.max_value)
        step = float(param_config.step)
        
        values = [round(current, 2)]
        before, after = current - step, current + step
        max_iterations = 1000 if expand_search else max_tests
        
        while len(values) < max_iterations:
            if after <= max_val:
                values.append(round(after, 2))
                after += step
            if len(values) >= max_tests and not expand_search:
                break
            if before >= min_val:
                values.append(round(before, 2))
                before -= step
            if before < min_val and after > max_val:
                break
        
        return values


class ResultsWriter:
    """Gère l'écriture des résultats."""
    
    def __init__(self, results_file: str, best_file: str, best_config_file: str):
        self.results_file = results_file
        self.best_file = best_file
        self.best_config_file = best_config_file
    
    def write_result(self, pnl: float, config: Dict[str, Any], cache: ConfigCache) -> None:
        """Écrit un résultat seulement s'il n'est pas déjà dans le fichier."""
        if cache.contains(config):
            return
        
        row = {"pnl": pnl, **config}
        file_exists = os.path.exists(self.results_file) and os.stat(self.results_file).st_size > 0
        
        with open(self.results_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    
    def save_best_results(self, results: List[OptimizationResult], 
                         param_names: List[str], top_n: int = 10) -> None:
        """Sauvegarde les N meilleures configurations."""
        sorted_results = sorted(results, key=lambda x: x.pnl, reverse=True)
        
        with open(self.best_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["pnl"] + param_names)
            writer.writeheader()
            for result in sorted_results[:top_n]:
                writer.writerow({"pnl": result.pnl, **result.config})
    
    def save_best_config(self, config: Dict[str, Any], pnl: float) -> None:
        """Sauvegarde la meilleure configuration trouvée."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "pnl": pnl,
            "config": config
        }
        with open(self.best_config_file, "w") as f:
            json.dump(data, f, indent=4)
        print(f"  💾 Nouvelle meilleure config sauvegardée: PnL={pnl:.2f}")
    
    def load_best_config(self) -> Optional[Dict[str, Any]]:
        """Charge la meilleure configuration sauvegardée."""
        if not os.path.exists(self.best_config_file):
            return None
        
        with open(self.best_config_file) as f:
            data = json.load(f)
        
        print(f"📂 Meilleure config chargée depuis {self.best_config_file}")
        print(f"   PnL précédent: {data.get('pnl', 'N/A')}")
        return data


class ParamOptimizer:
    """Optimisation séquentielle itérative des paramètres."""

    def __init__(self, json_file: str = "params.json", 
                 results_file: str = "results.csv",
                 best_file: str = "best_results.csv", 
                 best_config_file: str = "best_config.json",
                 data_files: Optional[List[str]] = None, 
                 parallel: bool = True):
        
        self.json_file = json_file
        self.params: Dict[str, ParamConfig] = {}
        self.param_order: List[str] = []
        
        # Composants
        self.cache = ConfigCache(results_file)
        self.writer = ResultsWriter(results_file, best_file, best_config_file)
        self.value_generator = ValueGenerator()
        
        # Simulateur
        data_files = data_files or glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        self.simulator = MultiFileSimulator(data_files, parallel=parallel, verbose=False)
        
        # État de l'optimisation
        self.all_results: List[OptimizationResult] = []
        self.global_best_pnl = float('-inf')
        self.global_best_config: Optional[Dict[str, Any]] = None
        self._previous_iteration_pnl = float('inf')

    def save_params(self, params: Dict[str, Dict[str, Any]]) -> None:
        """Sauvegarde les paramètres dans un fichier JSON."""
        with open(self.json_file, "w") as f:
            json.dump(params, f, indent=4)

    def load_params(self) -> None:
        """Charge les paramètres depuis le fichier JSON."""
        with open(self.json_file) as f:
            params_dict = json.load(f)
        
        self.params = {
            name: ParamConfig(**config) 
            for name, config in params_dict.items()
        }
        
        active_params = {k: v for k, v in self.params.items() if v.enabled}
        self.param_order = sorted(active_params.keys(), 
                                 key=lambda k: active_params[k].priority)
        
        disabled_count = len(self.params) - len(active_params)
        if disabled_count > 0:
            disabled_names = [k for k, v in self.params.items() if not v.enabled]
            print(f"⚠️  {disabled_count} paramètre(s) désactivé(s): {disabled_names}")

    def _load_initial_config(self, reset_from_initial: bool) -> Dict[str, Any]:
        """Charge la configuration initiale."""
        if reset_from_initial:
            print("🔄 RESET: Redémarrage depuis les valeurs initiales")
            return {name: config.initial_value for name, config in self.params.items()}
        
        best_data = self.writer.load_best_config()
        if best_data:
            self.global_best_pnl = best_data.get('pnl', float('-inf'))
            self.global_best_config = best_data.get('config', {}).copy()
            return best_data.get('config', {})
        
        print(f"📝 Aucune config précédente, utilisation des valeurs initiales")
        return {name: config.initial_value for name, config in self.params.items()}

    def _test_config(self, config: Dict[str, Any]) -> float:
        """Teste une configuration, utilise le cache si disponible."""
        cached_pnl = self.cache.get(config)
        if cached_pnl is not None:
            print(f"      ♻️  Config déjà testée (cache) → PnL={cached_pnl:.2f}")
            return cached_pnl
        
        pnl = self.simulator.run_all_files(config)['total_pnl']
        self.cache.add(config, pnl)
        return pnl

    def _find_untested_values(self, param_name: str, current_config: Dict[str, Any], 
                            max_tests: int) -> List[Any]:
        """Trouve des valeurs non encore testées pour un paramètre."""
        current_value = current_config[param_name]
        param_config = self.params[param_name]
        
        all_values = self.value_generator.generate_around_value(
            param_config, current_value, max_tests, expand_search=True
        )
        
        untested = []
        for value in all_values:
            test_config = current_config.copy()
            test_config[param_name] = value
            
            if not self.cache.contains(test_config):
                untested.append(value)
                if len(untested) >= max_tests:
                    break
        
        return untested

    def _optimize_param(self, param_name: str, current_config: Dict[str, Any], 
                       max_tests: int, force_exploration: bool = False) -> OptimizationResult:
        """Optimise un seul paramètre."""
        param_config = self.params[param_name]
        current_value = current_config[param_name]
        
        # Génération des valeurs à tester
        if force_exploration:
            test_values = self._find_untested_values(param_name, current_config, max_tests)
            if test_values:
                print(f"  🔍 {param_name} (P{param_config.priority}): current={current_value} → explore={test_values} 🌍")
            else:
                print(f"  ✓ {param_name} (P{param_config.priority}): toutes les valeurs proches déjà testées")
                test_values = self.value_generator.generate_around_value(
                    param_config, current_value, max_tests
                )
        else:
            test_values = self.value_generator.generate_around_value(
                param_config, current_value, max_tests
            )
            print(f"  🔍 {param_name} (P{param_config.priority}): current={current_value} → test={test_values}")
        
        # Test de chaque valeur
        results = []
        for value in test_values:
            test_config = current_config.copy()
            test_config[param_name] = value
            
            pnl = self._test_config(test_config)
            result = OptimizationResult(pnl, test_config.copy())
            results.append(result)
            self.all_results.append(result)
            self.writer.write_result(pnl, test_config, self.cache)
        
        # Retourne le meilleur résultat
        return max(results, key=lambda r: r.pnl)

    def _print_iteration_summary(self, iteration: int, start_pnl: float, 
                                end_pnl: float, improvements: int) -> None:
        """Affiche le résumé d'une itération."""
        gain = end_pnl - start_pnl
        print(f"\n  📊 Bilan itération {iteration}:")
        print(f"     • Améliorations: {improvements}/{len(self.param_order)}")
        print(f"     • Gain itération: {gain:+.2f}")
        print(f"     • PnL itération: {end_pnl:.2f}")
        
        if end_pnl > self.global_best_pnl:
            gain_vs_best = end_pnl - self.global_best_pnl
            print(f"     🏆 NOUVEAU RECORD! Gain vs meilleur: +{gain_vs_best:.2f}")
        else:
            print(f"     • Écart vs meilleur: {end_pnl - self.global_best_pnl:+.2f}")

    def run_optimization(self, max_tests_per_param: int = 5, 
                        max_iterations: int = 10, 
                        reset_from_initial: bool = False) -> None:
        """
        Lance l'optimisation itérative.
        
        Args:
            max_tests_per_param: Nombre de valeurs à tester par paramètre
            max_iterations: Nombre maximum d'itérations
            reset_from_initial: Si True, ignore la config précédente
        """
        self.load_params()
        
        # Configuration initiale
        current_config = self._load_initial_config(reset_from_initial)
        current_pnl = self._test_config(current_config)
        
        if self.global_best_config is None or current_pnl > self.global_best_pnl:
            self.global_best_pnl = current_pnl
            self.global_best_config = current_config.copy()
            self.writer.save_best_config(self.global_best_config, self.global_best_pnl)
        
        print(f"\n{'='*80}")
        print(f"🎯 Config de départ: PnL = {current_pnl:.2f}")
        print(f"🏆 Meilleure config globale: PnL = {self.global_best_pnl:.2f}")
        print(f"📋 Paramètres actifs: {len(self.param_order)}/{len(self.params)}")
        print(f"♻️  Configurations en cache: {len(self.cache.cache)}")
        print(f"{'='*80}")
        
        self.all_results.append(OptimizationResult(current_pnl, current_config.copy()))
        self.writer.write_result(current_pnl, current_config, self.cache)
        
        # Boucle d'optimisation
        for iteration in range(1, max_iterations + 1):
            print(f"\n{'#'*80}")
            print(f"🔄 ITÉRATION {iteration}/{max_iterations}")
            print(f"🏆 Meilleure config globale: PnL = {self.global_best_pnl:.2f} (référence)")
            print(f"{'#'*80}")
            
            iteration_start_pnl = current_pnl
            improvements = 0
            force_exploration = (iteration > 1 and iteration_start_pnl <= self._previous_iteration_pnl)
            
            if force_exploration:
                print("  🌍 Mode EXPLORATION activé: recherche de valeurs non testées")
            
            # Optimisation de chaque paramètre
            for param_name in self.param_order:
                best_result = self._optimize_param(
                    param_name, current_config, max_tests_per_param, force_exploration
                )
                
                if best_result.pnl > current_pnl:
                    improvement = best_result.pnl - current_pnl
                    print(f"    ✅ {param_name}={best_result.config[param_name]} → +{improvement:.2f} (PnL: {best_result.pnl:.2f})")
                    current_config = best_result.config
                    current_pnl = best_result.pnl
                    improvements += 1
                else:
                    print(f"    ➡️  {param_name}={best_result.config[param_name]} (PnL: {best_result.pnl:.2f}, stable)")
                    current_config[param_name] = best_result.config[param_name]
            
            # Bilan de l'itération
            self._print_iteration_summary(iteration, iteration_start_pnl, current_pnl, improvements)
            
            # Mise à jour du meilleur global
            if current_pnl > self.global_best_pnl:
                self.global_best_pnl = current_pnl
                self.global_best_config = current_config.copy()
                self.writer.save_best_config(self.global_best_config, self.global_best_pnl)
            
            self.writer.save_best_results(self.all_results, list(self.params.keys()), top_n=10)
            self._previous_iteration_pnl = iteration_start_pnl
            
            # Condition d'arrêt
            if current_pnl <= iteration_start_pnl:
                print(f"\n  🛑 Convergence atteinte (aucune amélioration)")
                break
        
        # Résumé final
        print(f"\n{'='*80}")
        print(f"🏁 OPTIMISATION TERMINÉE")
        print(f"{'='*80}")
        print(f"📈 PnL final itération: {current_pnl:.2f}")
        print(f"🏆 PnL meilleur global: {self.global_best_pnl:.2f}")
        print(f"🔢 Itérations: {iteration}/{max_iterations}")
        print(f"♻️  Configurations testées (total): {len(self.cache.cache)}")
        print(f"📁 Résultats: {self.writer.best_file}")
        print(f"💾 Config sauvegardée: {self.writer.best_config_file}")
        print(f"📜 Historique complet: {self.writer.results_file}")
        print(f"{'='*80}\n")


# ========== Configuration par défaut ==========

DEFAULT_PARAMS = {
    "min_market_pnl": {
        "initial_value": 43.0, "min_value": 30.0, "max_value": 60.0, 
        "step": 5.0, "priority": 1, "enabled": True
    },
    "take_profit_market_pnl": {
        "initial_value": 70.0, "min_value": 50.0, "max_value": 100.0, 
        "step": 10.0, "priority": 2, "enabled": True
    },
    "trail_stop_market_pnl": {
        "initial_value": 1040, "min_value": 800, "max_value": 1500, 
        "step": 100, "priority": 3, "enabled": True
    },
    "trade_start_hour": {
        "initial_value": "09:30", "min_value": "09:00", "max_value": "10:00", 
        "step": 15, "priority": 4, "enabled": True
    },
    "trade_cutoff_hour": {
        "initial_value": "13:45", "min_value": "13:00", "max_value": "15:00", 
        "step": 15, "priority": 5, "enabled": True
    },
    "min_escape_time": {
        "initial_value": 83.0, "min_value": 60.0, "max_value": 120.0, 
        "step": 10.0, "priority": 6, "enabled": True
    },
    "max_trades_per_day": {
        "initial_value": 10, "min_value": 5, "max_value": 20, 
        "step": 2, "priority": 7, "enabled": True
    },
    "stop_echappee_threshold": {
        "initial_value": 1, "min_value": 1, "max_value": 3, 
        "step": 0.5, "priority": 8, "enabled": True
    },
    "start_echappee_threshold": {
        "initial_value": 1.5, "min_value": 1.0, "max_value": 3.0, 
        "step": 0.5, "priority": 9, "enabled": True
    },
    "top_n_threshold": {
        "initial_value": 1, "min_value": 1, "max_value": 5, 
        "step": 1, "priority": 10, "enabled": False
    },
    "trade_value_eur": {
        "initial_value": 100.0, "min_value": 50.0, "max_value": 200.0, 
        "step": 25.0, "priority": 11, "enabled": False
    },
    "trade_interval_minutes": {
        "initial_value": 150000, "min_value": 100000, "max_value": 200000, 
        "step": 25000, "priority": 12, "enabled": False
    },
    "max_pnl_timeout_minutes": {
        "initial_value": 6000.0, "min_value": 4000.0, "max_value": 8000.0, 
        "step": 1000.0, "priority": 13, "enabled": False
    },
}


def main():
    optimizer = ParamOptimizer(parallel=True)
    
    if not os.path.exists("params.json"):
        optimizer.save_params(DEFAULT_PARAMS)
    
    optimizer.run_optimization(max_tests_per_param=3, max_iterations=10000)


if __name__ == "__main__":
    main()