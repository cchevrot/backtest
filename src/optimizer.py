"""
Optimizer — Module d'optimisation pour les stratégies de trading.

==== RÔLE DE LA CLASSE ====
L'Optimizer implémente l'algorithme de descente de coordonnées pour trouver 
les meilleurs paramètres d'une stratégie de trading.

Il teste systématiquement toutes les valeurs possibles pour chaque paramètre, 
un à la fois, tout en gardant les autres constants.

==== MÉTHODE D'OPTIMISATION : DESCENTE DE COORDONNÉES ====
Principe :
1. Choisir un paramètre à optimiser (ex: take_profit_market_pnl)
2. Tester TOUTES les valeurs possibles pour ce paramètre
   (ex: de 50 à 200 par pas de 5 → teste 50, 55, 60, ..., 200)
3. Garder la valeur qui donne le meilleur PnL
4. Passer au paramètre suivant
5. Répéter le cycle jusqu'à convergence

Avantages :
+ Simple et robuste
+ Garantit de tester toutes les combinaisons dans les plages définies
+ Ne nécessite pas de gradient (adapté aux fonctions non-dérivables)

Inconvénients :
- Peut être lent si beaucoup de paramètres
- Optimum local possible (solution : redémarrer avec config aléatoire)

==== ATTRIBUTS ====
- param_configs : dict - Configuration de chaque paramètre à optimiser
  Structure : {
    'nom_parametre': {
      'initial_value': valeur_par_defaut,
      'min_value': valeur_minimale,
      'max_value': valeur_maximale,
      'step': pas_entre_valeurs
    }
  }
  Exemple : {
    'take_profit_market_pnl': {
      'initial_value': 50.0,
      'min_value': 50.0,
      'max_value': 200.0,
      'step': 5.0
    }
  }
  → Testera : 50, 55, 60, 65, ..., 195, 200
  
- simulation_runner : SimulationRunner - Exécuteur de simulations
  Utilisé pour calculer le PnL de chaque configuration testée

==== MÉTHODES PRINCIPALES ====
- coordinate_descent_step(current_params, param_idx, iteration)
  Effectue UNE étape d'optimisation sur UN paramètre
  
  Args:
    - current_params : Configuration actuelle de tous les paramètres
    - param_idx : Index du paramètre à optimiser (0, 1, 2, ...)
    - iteration : Numéro de l'itération (pour affichage/logging)
  
  Process :
    1. Extrait la configuration du paramètre à optimiser
    2. Génère toutes les valeurs possibles (min → max par step)
    3. Pour chaque valeur :
       - Crée une nouvelle configuration avec cette valeur
       - Vérifie si déjà testée (via memoire)
       - Si non testée : exécute la simulation et compare le PnL
    4. Retourne (meilleurs_params, meilleur_pnl, has_untested)
  
  Returns:
    - best_params : Configuration avec le meilleur PnL trouvé
    - best_pnl : Meilleur PnL obtenu
    - has_untested : True si au moins une valeur n'avait pas été testée
  
  Note : has_untested permet de savoir si on a exploré du nouveau territoire
         Si False, toutes les valeurs ont déjà été testées

- _parse_time_to_minutes(time_str) : Convertit "HH:MM" → minutes totales
  Exemple : "14:30" → 870 minutes (14*60 + 30)
  
- _minutes_to_time(total_minutes) : Convertit minutes → "HH:MM"
  Exemple : 870 → "14:30"

==== GESTION DES PARAMÈTRES TEMPORELS ====
Certains paramètres sont au format horaire (HH:MM) plutôt que numériques :
- trade_cutoff_hour : Heure de fin de trading (ex: "14:00")
- trade_start_hour : Heure de début de trading (ex: "09:30")

Pour ces paramètres, l'optimiseur :
1. Convertit les heures en minutes
2. Génère les valeurs possibles en minutes
3. Reconvertit en format HH:MM pour les tests

Exemple :
  min_value: "09:00" → 540 minutes
  max_value: "12:00" → 720 minutes
  step: 30 minutes
  → Teste : "09:00", "09:30", "10:00", ..., "12:00"

==== CLASSES UTILISÉES ====
- SimulationRunner : Exécute les simulations pour calculer le PnL
  Méthode appelée : run_simulation_display(params, iteration)

==== FLUX D'UTILISATION ====
1. main.py appelle coordinate_descent_step() en boucle
2. Optimizer teste toutes les valeurs d'un paramètre
3. Pour chaque valeur, SimulationRunner calcule le PnL
4. Optimizer garde la meilleure configuration
5. main.py passe au paramètre suivant (param_idx += 1)
6. Le cycle continue jusqu'à convergence

==== EXEMPLE D'OPTIMISATION ====
Config initiale : {take_profit: 50, stop_loss: 20}
Optimiser take_profit (plage: 50-100, step: 10) :
  Test 50 → PnL = 1000$
  Test 60 → PnL = 1200$ ← meilleur
  Test 70 → PnL = 1100$
  ...
  Test 100 → PnL = 800$
  → Garde take_profit = 60

Config nouvelle : {take_profit: 60, stop_loss: 20}
Optimiser stop_loss (plage: 10-30, step: 5) :
  Test 10 → PnL = 1100$
  Test 15 → PnL = 1300$ ← meilleur
  ...
  → Garde stop_loss = 15

Config finale : {take_profit: 60, stop_loss: 15}
"""

from colorama import Fore, Style
from copy import deepcopy


class Optimizer:
    """
    Classe d'optimisation utilisant la méthode de descente de coordonnées.
    
    Cette classe optimise les paramètres d'une stratégie de trading en testant
    systématiquement différentes valeurs pour chaque paramètre, un à la fois.
    
    Attributes:
        param_configs (dict): Configuration des paramètres avec leurs plages de valeurs
        simulation_runner (SimulationRunner): Objet pour exécuter les simulations
    """
    
    def __init__(self, param_configs, simulation_runner):
        """
        Initialise l'optimiseur avec la configuration des paramètres.
        
        Args:
            param_configs (dict): Configuration des paramètres à optimiser
            simulation_runner (SimulationRunner): Exécuteur de simulations
        """
        self.param_configs = param_configs
        self.simulation_runner = simulation_runner

    def _parse_time_to_minutes(self, time_str):
        """
        Convertit une chaîne HH:MM en minutes.
        
        Args:
            time_str (str): Chaîne de temps au format HH:MM
            
        Returns:
            int: Nombre total de minutes
            
        Raises:
            ValueError: Si le format de temps est invalide
        """
        try:
            hours, minutes = map(int, time_str.split(':'))
            return hours * 60 + minutes
        except ValueError:
            raise ValueError(f"Format de temps invalide pour {time_str}. Attendu: HH:MM")

    def _minutes_to_time(self, total_minutes):
        """
        Convertit des minutes en chaîne HH:MM.
        
        Args:
            total_minutes (int): Nombre total de minutes
            
        Returns:
            str: Chaîne de temps au format HH:MM
        """
        hours = int(total_minutes // 60)
        minutes = int(total_minutes % 60)
        return f"{hours:02d}:{minutes:02d}"

    def coordinate_descent_step(self, current_params, param_idx, iteration):
        """
        Effectue une étape d'optimisation par descente de coordonnées.
        
        Cette méthode optimise un paramètre spécifique en testant toutes les
        valeurs possibles dans sa plage définie, tout en gardant les autres
        paramètres constants.
        
        Args:
            current_params (dict): Paramètres actuels de la stratégie
            param_idx (int): Index du paramètre à optimiser
            iteration (int): Numéro de l'itération actuelle
            
        Returns:
            tuple: (meilleurs_paramètres, meilleur_pnl, a_des_valeurs_non_testées)
        """
        param_name = list(self.param_configs.keys())[param_idx]
        config = self.param_configs[param_name]
        min_val = config['min_value']
        max_val = config['max_value']
        step = config['step']
        current_value = current_params[param_name]
        best_pnl = self.simulation_runner.run_simulation_display(current_params, iteration)
        best_params = current_params.copy()
        has_untested = False

        print(f"Starting optimization for {param_name} from {min_val} to {max_val}, current PnL: ${best_pnl:.2f}")

        # Gérer les paramètres au format HH:MM (heures de trading)
        if param_name in ['trade_cutoff_hour', 'trade_start_hour']:
            min_minutes = self._parse_time_to_minutes(min_val)
            max_minutes = self._parse_time_to_minutes(max_val)
            step_minutes = step  # step est déjà en minutes

            # Générer les valeurs possibles pour les heures
            possible_values = []
            value_minutes = min_minutes
            while value_minutes <= max_minutes:
                possible_values.append(self._minutes_to_time(value_minutes))
                value_minutes += step_minutes
        else:
            # Pour les paramètres numériques (stop_loss, take_profit, etc.)
            possible_values = []
            value = min_val
            while value <= max_val:
                possible_values.append(value)
                value += step
                # Éviter les erreurs d'arrondi pour les flottants
                if isinstance(value, float) and abs(value - max_val) < 1e-6:
                    possible_values.append(max_val)
                    break

        # Tester chaque valeur possible pour le paramètre
        for value in possible_values:
            test_params = current_params.copy()
            test_params[param_name] = value
            
            # Vérifier si cette configuration a déjà été testée
            if self.simulation_runner.memoire.has_been_tested(test_params):
                print(f"Configuration avec {param_name} = {value} déjà testée, passage à l'étape suivante")
                continue
                
            has_untested = True
            pnl = self.simulation_runner.run_simulation_display(test_params, iteration)
            print(f"Tested {param_name} = {value}, PnL = ${pnl:.2f}")
            
            # Mettre à jour si le PnL est égal ou meilleur
            if pnl >= best_pnl:
                best_pnl = pnl
                best_params = test_params.copy()

        print(f"Best parameters after optimization: {best_params}, Best PnL: ${best_pnl:.2f}, Has untested: {has_untested}")
        return best_params, best_pnl, has_untested