"""
ConfigManager — Gestionnaire de configuration pour l'optimisation de stratégies de trading.

==== RÔLE DE LA CLASSE ====
ConfigManager centralise la gestion des paramètres de la stratégie :
- Définit les plages de valeurs acceptables pour chaque paramètre
- Charge et sauvegarde les meilleures configurations trouvées
- Valide les configurations pour éviter les erreurs

C'est le gardien des paramètres : il s'assure que toutes les valeurs sont 
dans les plages définies et cohérentes.

==== RESPONSABILITÉS PRINCIPALES ====
1. Définir les configurations par défaut de tous les paramètres
   (valeur initiale, min, max, step)
2. Sauvegarder la meilleure configuration dans best_config.json
3. Charger la meilleure configuration au démarrage
4. Valider les paramètres avant utilisation
5. Fournir les paramètres par défaut si aucune config sauvegardée

==== ATTRIBUTS ====
- config_file : str - Chemin du fichier de sauvegarde (défaut: "best_config.json")
  
- default_param_configs : dict - Configuration de tous les paramètres
  Structure : {
    'nom_parametre': {
      'initial_value': valeur_de_départ,
      'min_value': valeur_minimale_autorisée,
      'max_value': valeur_maximale_autorisée,
      'step': pas_d'incrémentation
    }
  }

==== PARAMÈTRES GÉRÉS ====

Paramètres de sortie (fermeture de positions) :
- take_profit_market_pnl : Objectif de gain pour fermer (ex: 50-200€, step 5)
  Plus élevé = attend plus de gain avant de fermer
  
- trail_stop_market_pnl : Protection des gains (ex: 30-50€, step 1)
  Si le PnL baisse de X€ depuis le max, fermer la position
  
- max_pnl_timeout_minutes : Timeout sans nouveau max (ex: 60-6000 min)
  Fermer si pas de nouveau max PnL depuis X minutes

Paramètres d'entrée (ouverture de positions) :
- min_market_pnl : PnL minimum requis pour ouvrir (ex: 10-50€, step 5)
  Évite d'ouvrir sur des signaux faibles
  
- start_echappee_threshold : Multiplicateur d'écart-type pour entrer (ex: 0.5-1.5)
  Seuil = moyenne + (threshold × écart-type)
  Plus élevé = plus sélectif (attend les vraies échappées)
  
- stop_echappee_threshold : Multiplicateur d'écart-type pour sortir (ex: 0-1)
  Seuil de sortie = moyenne - (threshold × écart-type)

Paramètres de timing :
- min_escape_time : Durée minimale d'échappée (ex: 60-600s, step 60)
  Le ticker doit rester en échappée pendant X secondes avant ouverture
  Évite les fausses échappées éphémères
  
- trade_interval_minutes : Intervalle entre trades périodiques (ex: 30-300 min)
  Contrôle la fréquence des trades

Paramètres de limitation :
- top_n_threshold : Position max dans le classement (ex: 1-10)
  Le ticker doit être dans le top N pour être éligible
  
- max_trades_per_day : Limite quotidienne de trades (ex: 1-5)
  Évite le sur-trading
  
- trade_cutoff_hour : Heure de fin de trading (ex: "12:00"-"16:00")
  Pas de nouveaux trades après cette heure
  
- trade_start_hour : Heure de début de trading (ex: "09:00"-"11:00")
  Pas de nouveaux trades avant cette heure

Paramètre de capital :
- trade_value_eur : Montant par trade (ex: 100-500€, step 1)
  Contrôle la taille des positions

==== MÉTHODES PRINCIPALES ====
- __init__(config_file) : Initialise le gestionnaire avec un fichier de config
  Définit default_param_configs avec toutes les plages de valeurs
  
- load_best_config() : Charge la meilleure config depuis le fichier JSON
  Returns : (best_params, best_pnl, best_iteration) ou (None, None, None)
  Valide automatiquement les paramètres chargés
  
- save_best_config(params, pnl, iteration) : Sauvegarde la meilleure config
  Écrit dans le fichier JSON : {
    "best_iteration": iteration,
    "best_pnl": pnl,
    "best_params": params
  }
  
- get_default_params() : Retourne les paramètres par défaut
  Extrait les 'initial_value' de default_param_configs
  
- validate_params(params) : Valide une configuration
  Vérifie que :
  - Tous les paramètres requis sont présents
  - Toutes les valeurs sont dans les plages min/max
  - Les formats sont corrects (ex: HH:MM pour les heures)
  Returns : True si valide, False sinon

==== FORMAT DU FICHIER best_config.json ====
{
  "best_iteration": 42,
  "best_pnl": 1234.56,
  "best_params": {
    "take_profit_market_pnl": 84.0,
    "min_market_pnl": 20.0,
    "trade_cutoff_hour": "12:30",
    ...
  }
}

==== FLUX D'UTILISATION ====
1. Au démarrage : main.py crée un ConfigManager
2. ConfigManager.load_best_config() charge la config précédente
3. Si pas de config valide : utilise get_default_params()
4. Pendant l'optimisation : validate_params() vérifie chaque config
5. Quand meilleur trouvé : save_best_config() sauvegarde
6. Au prochain démarrage : on repart de la meilleure config trouvée

==== VALIDATION DES PARAMÈTRES ====
Pour les paramètres numériques :
  min_value <= valeur <= max_value

Pour les paramètres temporels (HH:MM) :
  Conversion en minutes → vérification des bornes → validation du format

Exemple : trade_cutoff_hour = "14:30"
  → 14*60 + 30 = 870 minutes
  → Vérifie : min_minutes <= 870 <= max_minutes

==== GESTION DES ERREURS ====
- Fichier manquant : Retourne None, utilise valeurs par défaut
- JSON mal formaté : Retourne None, affiche erreur en rouge
- Paramètre hors bornes : Retourne None, affiche erreur
- Paramètre manquant : Retourne None, affiche erreur

==== EXEMPLE D'UTILISATION ====
cm = ConfigManager()
params, pnl, iteration = cm.load_best_config()
if params is None:
    params = cm.get_default_params()
if cm.validate_params(params):
    # Utiliser les paramètres
    pass
else:
    # Erreur de validation
    pass
"""

import json
import os
from colorama import Fore

class ConfigManager:
    """Gère le chargement, la sauvegarde et la validation des configurations."""
    
    def __init__(self, config_file="best_config.json"):
        self.config_file = config_file
        self.default_param_configs = {
            'trade_start_hour': {  # Nouveau paramètre
                'initial_value': "09:30", 
                'min_value': "09:30", 
                'max_value': "18:00", 
                'step': 30  # Pas de 1 heure, en minutes
            },
            'trade_cutoff_hour': {
                'initial_value': "13:45", # "13:45", 
                'min_value': "09:00", 
                'max_value': "18:00", 
                'step': 30  # Pas de 1 heure, en minutes
            },


            'min_market_pnl': {
               
                'initial_value': 43.0,
                'min_value':0.0, 'max_value': 200.0, 'step': 1.0
            },
            'take_profit_market_pnl': {
                'initial_value': 70.0,
                'min_value': 0.0, 'max_value': 200.0, 'step': 4
            },
            'trail_stop_market_pnl': {
                'initial_value': 1000,
                'min_value': 0.0, 'max_value': 200.0, 'step': 5
            },
  
            'min_escape_time': {
                'initial_value':83.0,
                'min_value': 0, 'max_value': 200.0, 'step': 60
            },
            'max_trades_per_day': {
                'initial_value': 10,
                'min_value': 0, 'max_value': 200, 'step': 2
            },
            'trade_value_eur': {
                'initial_value': 100.0,
                'min_value': 100.0, 'max_value': 100.0, 'step': 1.0
            },
            'top_n_threshold': {
                'initial_value': 1,
                'min_value': 0, 'max_value': 200, 'step': 1
            },
            'stop_echappee_threshold': {
                'initial_value': 1,
                'min_value': 0, 'max_value': 200, 'step': 0.5
            },
            'start_echappee_threshold': {
                'initial_value': 1.5,
                'min_value': 0, 'max_value': 200, 'step': 0.5
            },

            'trade_interval_minutes': {
                'initial_value': 150000,
                'min_value': 150000, 'max_value': 150000, 'step': 50
            },

            'max_pnl_timeout_minutes': {
                'initial_value': 6000.0,
                'min_value': 6000.0, 'max_value': 6000.0, 'step': 6000.0
            },



        }

    def load_best_config(self):
        """Charge la meilleure configuration depuis un fichier JSON si elle est valide."""
        if not os.path.exists(self.config_file):
            print(f"{Fore.YELLOW}Aucun fichier de configuration trouvé à {self.config_file}")
            return None, None, None

        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)

            if not all(key in config_data for key in ["best_iteration", "best_pnl", "best_params"]):
                print(f"{Fore.RED}Fichier JSON mal formaté : clés manquantes")
                return None, None, None

            best_params = config_data["best_params"]
            for param, config in self.default_param_configs.items():
                if param not in best_params:
                    print(f"{Fore.RED}Paramètre {param} manquant dans le fichier JSON")
                    return None, None, None
                if param in ['trade_cutoff_hour', 'trade_start_hour']:
                    # Valider le format HH:MM et les bornes
                    try:
                        hours, minutes = map(int, best_params[param].split(':'))
                        total_minutes = hours * 60 + minutes
                        min_minutes = int(config['min_value'].split(':')[0]) * 60 + int(config['min_value'].split(':')[1])
                        max_minutes = int(config['max_value'].split(':')[0]) * 60 + int(config['max_value'].split(':')[1])
                        if not (min_minutes <= total_minutes <= max_minutes):
                            print(f"{Fore.RED}Valeur de {param} hors des bornes")
                            return None, None, None
                    except ValueError:
                        print(f"{Fore.RED}Format invalide pour {param}: {best_params[param]}")
                        return None, None, None
                else:
                    if not (config['min_value'] <= best_params[param] <= config['max_value']):
                        print(f"{Fore.RED}Valeur de {param} hors des bornes")
                        return None, None, None

            print(f"{Fore.GREEN}Configuration chargée depuis {self.config_file}")
            return config_data["best_params"], config_data["best_pnl"], config_data["best_iteration"]
        except Exception as e:
            print(f"{Fore.RED}Erreur lors du chargement de la configuration : {e}")
            return None, None, None

    def save_best_config(self, best_params, best_pnl, best_iteration):
        """Enregistre la meilleure configuration dans un fichier JSON."""
        config_data = {
            "best_iteration": best_iteration,
            "best_pnl": best_pnl,
            "best_params": best_params
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=4)
            print(f"{Fore.GREEN}Meilleure configuration enregistrée dans {self.config_file}")
        except Exception as e:
            print(f"{Fore.RED}Erreur lors de l'enregistrement de la configuration : {e}")

    def get_default_params(self):
        """Retourne les paramètres par défaut."""
        return {param: config['initial_value'] for param, config in self.default_param_configs.items()}

    def validate_params(self, params):
        """Valide les paramètres par rapport aux configurations."""
        for param, value in params.items():
            if param not in self.default_param_configs:
                return False
            config = self.default_param_configs[param]
            if param in ['trade_cutoff_hour', 'trade_start_hour']:
                try:
                    hours, minutes = map(int, value.split(':'))
                    total_minutes = hours * 60 + minutes
                    min_minutes = int(config['min_value'].split(':')[0]) * 60 + int(config['min_value'].split(':')[1])
                    max_minutes = int(config['max_value'].split(':')[0]) * 60 + int(config['max_value'].split(':')[1])
                    if not (min_minutes <= total_minutes <= max_minutes):
                        return False
                except ValueError:
                    return False
            else:
                if not (config['min_value'] <= value <= config['max_value']):
                    return False
        return True
    


if __name__ == "__main__":
    cm = ConfigManager()

    print("\n--- Paramètres par défaut ---")
    default_params = cm.get_default_params()
    for k, v in default_params.items():
        print(f"{k}: {v}")

    print("\n--- Validation des paramètres par défaut ---")
    is_valid = cm.validate_params(default_params)
    print(f"Valides ? {Fore.GREEN if is_valid else Fore.RED}{is_valid}")

    if is_valid:
        print("\n--- Sauvegarde de la configuration ---")
        cm.save_best_config(best_params=default_params, best_pnl=1234.56, best_iteration=42)

        print("\n--- Chargement de la configuration ---")
        loaded_params, loaded_pnl, loaded_iter = cm.load_best_config()
        print(f"\nParamètres chargés : {loaded_params}")
        print(f"PNL chargé : {loaded_pnl}")
        print(f"Iteration chargée : {loaded_iter}")