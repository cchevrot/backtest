import json
import csv
import os
import glob
from datetime import datetime, timedelta
from multi_file_simulator import MultiFileSimulator


class ParamOptimizer:
    """Optimisation séquentielle itérative: boucle sur tous les paramètres jusqu'à convergence."""

    def __init__(self, json_file="params.json", results_file="results.csv",
                 best_file="best_results.csv", best_config_file="best_config.json",
                 data_files=None, parallel=True):
        self.json_file = json_file
        self.results_file = results_file
        self.best_file = best_file
        self.best_config_file = best_config_file
        
        # Initialisation du simulateur
        data_files = data_files or glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        self.multi_file_simulator = MultiFileSimulator(data_files, parallel=parallel, verbose=False)
        
        self.params = {}
        self.param_order = []
        self.all_results = []
        
        # Nouvelle variable: meilleure config globale
        self.global_best_pnl = float('-inf')
        self.global_best_config = None
        
        # 🆕 Cache des configurations déjà testées
        self.config_cache = {}
        self._load_cache_from_csv()

    # ========== 🆕 Gestion du cache ==========
    
    def _config_to_key(self, config: dict) -> str:
        """Convertit une config en clé unique (JSON trié)."""
        return json.dumps(config, sort_keys=True)
    
    def _load_cache_from_csv(self):
        """Charge toutes les configurations déjà testées depuis results.csv."""
        if not os.path.exists(self.results_file):
            print("📂 Aucun historique trouvé, démarrage avec cache vide")
            return
        
        try:
            with open(self.results_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
                for row in rows:
                    pnl = float(row.pop('pnl'))
                    # Convertit les valeurs en types appropriés
                    config = {}
                    for key, value in row.items():
                        try:
                            # Essaie int d'abord
                            config[key] = int(value)
                        except ValueError:
                            try:
                                # Puis float
                                config[key] = float(value)
                            except ValueError:
                                # Sinon garde en string
                                config[key] = value
                    
                    config_key = self._config_to_key(config)
                    self.config_cache[config_key] = pnl
                    self.all_results.append((pnl, config))
            
            print(f"✅ Cache chargé: {len(self.config_cache)} configurations depuis {self.results_file}")
            
        except Exception as e:
            print(f"⚠️  Erreur lors du chargement du cache: {e}")
            self.config_cache = {}

    # ========== Gestion des paramètres ==========
    
    def save_params(self, params: dict):
        with open(self.json_file, "w") as f:
            json.dump(params, f, indent=4)

    def load_params(self):
        with open(self.json_file) as f:
            self.params = json.load(f)
        
        # Filtre les paramètres actifs et tri par priorité
        active_params = {k: v for k, v in self.params.items() 
                        if v.get('enabled', True)}
        
        self.param_order = sorted(active_params.keys(), 
                                  key=lambda k: active_params[k].get('priority', 999))
        
        disabled_count = len(self.params) - len(active_params)
        if disabled_count > 0:
            disabled_names = [k for k, v in self.params.items() if not v.get('enabled', True)]
            print(f"⚠️  {disabled_count} paramètre(s) désactivé(s): {disabled_names}")

    def load_best_config(self) -> dict:
        """
        Charge la meilleure configuration sauvegardée si elle existe.
        Sinon, utilise les valeurs initiales du JSON.
        """
        if os.path.exists(self.best_config_file):
            with open(self.best_config_file) as f:
                best_config = json.load(f)
            print(f"📂 Meilleure config chargée depuis {self.best_config_file}")
            print(f"   PnL précédent: {best_config.get('pnl', 'N/A')}")
            
            # Initialise la meilleure config globale
            self.global_best_pnl = best_config.get('pnl', float('-inf'))
            self.global_best_config = best_config.get('config', {}).copy()
            
            return best_config.get('config', {})
        else:
            print(f"📝 Aucune config précédente, utilisation des valeurs initiales")
            return {name: self.params[name]["initial_value"] 
                   for name in self.params.keys()}

    def save_best_config(self, config: dict, pnl: float):
        """Sauvegarde la meilleure configuration trouvée."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "pnl": pnl,
            "config": config
        }
        with open(self.best_config_file, "w") as f:
            json.dump(data, f, indent=4)
        print(f"  💾 Nouvelle meilleure config sauvegardée: PnL={pnl:.2f}")

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

    def _generate_values_around_current(self, param_name: str, current_value, 
                                        max_tests: int, expand_search: bool = False) -> list:
        """
        Génère des valeurs autour de la valeur ACTUELLE (meilleure trouvée précédemment)
        au lieu de la valeur initiale du JSON.
        
        Args:
            expand_search: Si True, élargit la recherche au-delà de max_tests pour trouver
                          des valeurs non encore testées
        """
        if max_tests == 1 and not expand_search:
            return [current_value]
        
        settings = self.params[param_name]
        is_time = isinstance(current_value, str) and ":" in current_value
        
        if is_time:
            current = datetime.strptime(str(current_value), "%H:%M")
            min_val = datetime.strptime(settings["min_value"], "%H:%M")
            max_val = datetime.strptime(settings["max_value"], "%H:%M")
            step = timedelta(minutes=int(settings["step"]))
            fmt = lambda x: x.strftime("%H:%M")
        else:
            current = float(current_value)
            min_val = float(settings["min_value"])
            max_val = float(settings["max_value"])
            step = float(settings["step"])
            fmt = lambda x: round(x, 2)
        
        # Génération alternée autour de la valeur courante
        values = [fmt(current)]
        before, after = current - step, current + step
        
        max_iterations = max_tests if not expand_search else 1000  # Limite de sécurité
        
        while len(values) < max_iterations:
            if after <= max_val:
                values.append(fmt(after))
                after += step
            if len(values) >= max_tests and not expand_search:
                break
            if before >= min_val:
                values.append(fmt(before))
                before -= step
            if before < min_val and after > max_val:
                break
        
        return values
    
    def _find_untested_values(self, param_name: str, current_config: dict, 
                             max_tests: int) -> list:
        """
        Trouve des valeurs non encore testées pour un paramètre donné.
        Élargit progressivement la recherche autour de la valeur actuelle.
        """
        current_value = current_config[param_name]
        
        # Génère beaucoup plus de valeurs que nécessaire
        all_possible_values = self._generate_values_around_current(
            param_name, current_value, max_tests, expand_search=True
        )
        
        # Filtre pour ne garder que les valeurs non testées
        untested_values = []
        for value in all_possible_values:
            test_config = current_config.copy()
            test_config[param_name] = value
            config_key = self._config_to_key(test_config)
            
            if config_key not in self.config_cache:
                untested_values.append(value)
                if len(untested_values) >= max_tests:
                    break
        
        return untested_values

    # ========== Simulation ==========
    
    def _test_params(self, param_values: dict) -> float:
        """🆕 Teste une config, utilise le cache si déjà testée."""
        config_key = self._config_to_key(param_values)
        
        # Vérification dans le cache
        if config_key in self.config_cache:
            cached_pnl = self.config_cache[config_key]
            print(f"      ♻️  Config déjà testée (cache) → PnL={cached_pnl:.2f}")
            return cached_pnl
        
        # Nouvelle simulation
        pnl = self.multi_file_simulator.run_all_files(param_values)['total_pnl']
        
        # Ajout au cache
        self.config_cache[config_key] = pnl
        
        return pnl

    def _write_result(self, row: dict):
        """🆕 Écrit un résultat seulement s'il n'est pas déjà dans le fichier."""
        config_key = self._config_to_key({k: v for k, v in row.items() if k != 'pnl'})
        
        # Si déjà en cache, ne pas réécrire
        if config_key in self.config_cache:
            return
        
        file_exists = os.path.exists(self.results_file) and os.stat(self.results_file).st_size > 0
        with open(self.results_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def _save_best(self, top_n: int):
        """Sauvegarde les N meilleures configs."""
        self.all_results.sort(reverse=True, key=lambda x: x[0])
        with open(self.best_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["pnl"] + list(self.params.keys()))
            writer.writeheader()
            for pnl, params in self.all_results[:top_n]:
                writer.writerow({"pnl": pnl, **params})

    # ========== Optimisation d'un paramètre ==========
    
    def _optimize_single_param(self, param_name: str, current_config: dict, 
                                max_tests: int, force_exploration: bool = False) -> tuple:
        """
        Optimise un seul paramètre en testant différentes valeurs 
        autour de la valeur ACTUELLE (pas la valeur initiale).
        
        Args:
            force_exploration: Si True, cherche des valeurs non testées au lieu
                              des valeurs habituelles autour de current
        """
        priority = self.params[param_name]["priority"]
        current_value = current_config[param_name]
        
        # 🆕 Mode exploration: cherche des valeurs non testées
        if force_exploration:
            test_values = self._find_untested_values(param_name, current_config, max_tests)
            if test_values:
                print(f"  🔍 {param_name} (P{priority}): current={current_value} → explore={test_values} 🌍")
            else:
                print(f"  ✓ {param_name} (P{priority}): toutes les valeurs proches déjà testées")
                # Fallback sur les valeurs normales
                test_values = self._generate_values_around_current(param_name, current_value, max_tests)
        else:
            # Mode normal: valeurs autour de current
            test_values = self._generate_values_around_current(param_name, current_value, max_tests)
            print(f"  🔍 {param_name} (P{priority}): current={current_value} → test={test_values}")
        
        param_results = []
        
        # Test de chaque valeur
        for value in test_values:
            test_config = current_config.copy()
            test_config[param_name] = value
            
            pnl = self._test_params(test_config)
            param_results.append((pnl, value, test_config.copy()))
            self.all_results.append((pnl, test_config))
            self._write_result({"pnl": pnl, **test_config})
        
        # Sélection de la meilleure valeur
        param_results.sort(reverse=True, key=lambda x: x[0])
        best_pnl, best_value, best_config = param_results[0]
        
        return best_pnl, best_value, best_config

    # ========== Optimisation itérative complète ==========
    
    def run_optimization(self, max_tests_per_param: int = 5, max_iterations: int = 10, 
                        reset_from_initial: bool = False):
        """
        Optimisation itérative:
        1. Charge la meilleure config précédente (sauf si reset_from_initial=True)
        2. Charge le cache depuis results.csv (configurations déjà testées)
        3. Boucle sur tous les paramètres actifs (ordre de priorité)
        4. Pour chaque paramètre: teste autour de la valeur actuelle (ou réutilise le cache)
        5. Répète jusqu'à convergence ou max_iterations
        6. Sauvegarde la meilleure config à chaque itération si amélioration
        
        Args:
            max_tests_per_param: Nombre de valeurs à tester par paramètre
            max_iterations: Nombre max d'itérations complètes
            reset_from_initial: Si True, ignore la config précédente et repart des valeurs initiales
        """
        self.load_params()
        
        # 🆕 Plus de nettoyage des CSV ! Ils sont conservés
        # Les fichiers CSV sont maintenant persistants entre les exécutions
        
        # Configuration de départ
        if reset_from_initial:
            print("🔄 RESET: Redémarrage depuis les valeurs initiales")
            current_best_config = {name: self.params[name]["initial_value"] 
                                  for name in self.params.keys()}
            self.global_best_pnl = float('-inf')
            self.global_best_config = None
        else:
            # Charge la meilleure config précédente si disponible
            current_best_config = self.load_best_config()
        
        current_best_pnl = self._test_params(current_best_config)
        
        # Initialise la meilleure config globale si nécessaire
        if self.global_best_config is None or current_best_pnl > self.global_best_pnl:
            self.global_best_pnl = current_best_pnl
            self.global_best_config = current_best_config.copy()
            self.save_best_config(self.global_best_config, self.global_best_pnl)
        
        print(f"\n{'='*80}")
        print(f"🎯 Config de départ: PnL = {current_best_pnl:.2f}")
        print(f"🏆 Meilleure config globale: PnL = {self.global_best_pnl:.2f}")
        print(f"📋 Paramètres actifs: {len(self.param_order)}/{len(self.params)}")
        print(f"♻️  Configurations en cache: {len(self.config_cache)}")
        print(f"{'='*80}")
        
        self.all_results.append((current_best_pnl, current_best_config.copy()))
        self._write_result({"pnl": current_best_pnl, **current_best_config})
        
        # Boucle d'optimisation itérative
        for iteration in range(1, max_iterations + 1):
            print(f"\n{'#'*80}")
            print(f"🔄 ITÉRATION {iteration}/{max_iterations}")
            print(f"🏆 Meilleure config globale: PnL = {self.global_best_pnl:.2f} (référence)")
            print(f"{'#'*80}")
            
            iteration_start_pnl = current_best_pnl
            improvements_count = 0
            
            # 🆕 Détermine si on doit explorer de nouvelles valeurs
            # Si aucune amélioration à l'itération précédente, on active l'exploration
            force_exploration = (iteration > 1 and iteration_start_pnl <= getattr(self, '_previous_iteration_pnl', float('inf')))
            
            if force_exploration:
                print("  🌍 Mode EXPLORATION activé: recherche de valeurs non testées")
            
            # Optimisation séquentielle de chaque paramètre ACTIF
            for param_name in self.param_order:
                best_pnl, best_value, best_config = self._optimize_single_param(
                    param_name, current_best_config, max_tests_per_param, force_exploration
                )
                
                # Vérification de l'amélioration
                if best_pnl > current_best_pnl:
                    improvement = best_pnl - current_best_pnl
                    print(f"    ✅ {param_name}={best_value} → +{improvement:.2f} (PnL: {best_pnl:.2f})")
                    current_best_config = best_config
                    current_best_pnl = best_pnl
                    improvements_count += 1
                else:
                    print(f"    ➡️  {param_name}={best_value} (PnL: {best_pnl:.2f}, stable)")
                    # Garde quand même la meilleure valeur pour ce paramètre
                    current_best_config[param_name] = best_value
            
            # Bilan de l'itération
            iteration_gain = current_best_pnl - iteration_start_pnl
            print(f"\n  📊 Bilan itération {iteration}:")
            print(f"     • Améliorations: {improvements_count}/{len(self.param_order)}")
            print(f"     • Gain itération: {iteration_gain:+.2f}")
            print(f"     • PnL itération: {current_best_pnl:.2f}")
            
            # Vérification si c'est la meilleure config globale
            if current_best_pnl > self.global_best_pnl:
                gain_vs_best = current_best_pnl - self.global_best_pnl
                print(f"     🏆 NOUVEAU RECORD! Gain vs meilleur: +{gain_vs_best:.2f}")
                self.global_best_pnl = current_best_pnl
                self.global_best_config = current_best_config.copy()
                self.save_best_config(self.global_best_config, self.global_best_pnl)
            else:
                print(f"     • Écart vs meilleur: {current_best_pnl - self.global_best_pnl:+.2f}")
            
            # 🆕 Mise à jour de best_results.csv après chaque itération
            self._save_best(top_n=10)
            
            # Condition d'arrêt: aucune amélioration
            if iteration_gain <= 0:
                print(f"\n  🛑 Convergence atteinte (aucune amélioration)")
                break
        
        # Sauvegarde finale des meilleurs résultats
        self._save_best(top_n=10)
        
        print(f"\n{'='*80}")
        print(f"🏁 OPTIMISATION TERMINÉE")
        print(f"{'='*80}")
        print(f"📈 PnL final itération: {current_best_pnl:.2f}")
        print(f"🏆 PnL meilleur global: {self.global_best_pnl:.2f}")
        print(f"🔢 Itérations: {iteration}/{max_iterations}")
        print(f"♻️  Configurations testées (total): {len(self.config_cache)}")
        print(f"📁 Résultats: {self.best_file}")
        print(f"💾 Config sauvegardée: {self.best_config_file}")
        print(f"📜 Historique complet: {self.results_file}")
        print(f"{'='*80}\n")


# ========== Configuration ==========

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
        "initial_value": 1, 
        "min_value": 1, 
        "max_value": 3, 
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


def main():
    optimizer = ParamOptimizer(parallel=True)
    
    # Première fois: crée les paramètres initiaux
    if not os.path.exists("params.json"):
        optimizer.save_params(DEFAULT_PARAMS)
    
    # Lance l'optimisation (utilise automatiquement la meilleure config précédente)
    optimizer.run_optimization(max_tests_per_param=3, max_iterations=10000)
    
    # Pour forcer un reset depuis les valeurs initiales:
    # optimizer.run_optimization(max_tests_per_param=3, max_iterations=10, reset_from_initial=True)


if __name__ == "__main__":
    main()