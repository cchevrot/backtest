"""
Script principal pour l'optimisation de stratégies de trading par backtesting.

==== VUE D'ENSEMBLE DU PROJET ====
Ce projet est un système d'optimisation automatique pour une stratégie de trading 
algorithmique appelée "Algo Échappée". Il teste différentes configurations de 
paramètres sur des données historiques de prix pour trouver la combinaison optimale.

==== ARCHITECTURE PRINCIPALE ====
main.py (ce fichier) - Le chef d'orchestre :
- Lance un serveur web pour visualiser les résultats en temps réel
- Exécute une boucle d'optimisation infinie qui teste différentes configurations
- Utilise la descente de coordonnées : optimise un paramètre à la fois
- Sauvegarde automatiquement les meilleures configurations trouvées
- Redémarre le serveur web à chaque cycle complet

algo_echappee.py - La stratégie de trading :
- Identifie les actions "en échappée" (forte progression par rapport à la moyenne)
- Gère l'ouverture/fermeture des positions selon des critères statistiques
- Applique les limites (fenêtre horaire, max trades/jour, intervalles)

portfolio.py - Gestion du portefeuille :
- Suit toutes les positions ouvertes et fermées
- Calcule les PnL (Profit and Loss) réalisés et non réalisés
- Gère le cash disponible (capital initial : 1M$)

simulation_runner.py - Exécuteur de simulations :
- Exécute les backtests sur plusieurs fichiers de données (parallélisé)
- Calcule les métriques : PnL total, ROI, écart-type, jours positifs/négatifs
- Utilise une mémoire pour éviter de retester les mêmes configurations

optimizer.py - Optimiseur :
- Implémente la descente de coordonnées
- Teste systématiquement chaque paramètre dans sa plage définie

config_manager.py - Gestionnaire de configuration :
- Définit les plages de valeurs pour chaque paramètre (min, max, step)
- Charge/sauvegarde les meilleures configurations trouvées

==== FLUX D'EXÉCUTION ====
1. Charge la meilleure config précédente (ou défaut)
2. Pour chaque itération :
   - Teste une variation d'un paramètre
   - Exécute la simulation sur tous les fichiers de données
   - Compare le PnL obtenu
   - Sauvegarde si amélioration
3. Après un cycle complet, génère une config aléatoire si nécessaire
4. Continue jusqu'à épuisement des combinaisons

==== MÉTHODE D'OPTIMISATION ====
Descente de coordonnées :
- Optimise un paramètre à la fois
- Teste toutes les valeurs possibles dans la plage définie
- Conserve la meilleure valeur
- Passe au paramètre suivant
- Recommence le cycle jusqu'à convergence

"""
import multiprocessing
import os
import signal
import sys
import time
import random
from colorama import init, Fore, Style

import generate_web_page
from config_manager import ConfigManager
from simulation_runner import SimulationRunner
from optimizer import Optimizer
from memoire_config import SimulationMemoire


# Initialiser colorama pour les couleurs dans la console
# Permet d'afficher du texte coloré dans le terminal Windows
init(autoreset=True)

def run_web_server():
    """
    Fonction pour exécuter le script generate_web_page dans un processus séparé.

    Cette fonction lance le serveur web qui permet de visualiser les résultats
    des simulations en temps réel via une interface web.
    """
    try:
        generate_web_page.main()
    except (KeyboardInterrupt, SystemExit):
        # Gestion propre des interruptions
        pass
    except Exception as e:
        print(f"{Fore.RED}Error in web server process: {e}")

def start_web_server_process():
    """
    Démarre un nouveau processus serveur web et le retourne.

    Returns:
        multiprocessing.Process: Le processus du serveur web démarré
    """
    print(f"{Fore.YELLOW}Starting web server in a separate process...")
    web_process = multiprocessing.Process(target=run_web_server, daemon=True)
    web_process.start()
    print(f"{Fore.GREEN}Web server process started with PID: {web_process.pid}")
    return web_process

def terminate_web_server_process(web_process):
    """
    Termine le processus serveur web donné de manière propre.

    Args:
        web_process (multiprocessing.Process): Le processus à terminer
    """
    if web_process and web_process.is_alive():
        print(f"{Fore.YELLOW}Terminating web server process (PID: {web_process.pid})...")
        web_process.terminate()
        web_process.join(timeout=5.0)
        if web_process.is_alive():
            print(f"{Fore.RED}Web server process did not terminate gracefully, "
                  f"forcing kill...")
            try:
                os.kill(web_process.pid, signal.SIGTERM)
            except OSError:
                # Sur Windows, SIGTERM n'existe pas, utiliser SIGKILL équivalent
                pass

def signal_handler(sig, frame):  # pylint: disable=unused-argument
    """
    Gestionnaire de signaux pour assurer un arrêt propre du programme.

    Cette fonction est appelée quand le programme reçoit un signal d'interruption
    (Ctrl+C) ou de terminaison. Elle s'assure que le serveur web est arrêté proprement.

    Args:
        sig: Le signal reçu
        frame: Le frame d'exécution actuel
    """
    print(f"{Fore.YELLOW}Received termination signal. Shutting down...")
    global web_process  # pylint: disable=global-statement
    terminate_web_server_process(web_process)
    sys.exit(0)

if __name__ == "__main__":
    # Enregistrer les gestionnaires de signaux pour un arrêt propre
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Signal de terminaison

    # Démarrer le processus serveur web initial
    web_process = start_web_server_process()

    # Liste des fichiers de données de prix compressés (format LZ4)
    # Chaque fichier contient les données de prix pour une journée spécifique
    data_files = [
        # Données de juin 2025
        r"../data/06/17/prices_data.lz4",
        r"../data/06/18/prices_data.lz4",
        r"../data/06/20/prices_data.lz4",
        r"../data/06/23/prices_data.lz4",
        r"../data/06/24/prices_data.lz4",
        r"../data/06/25/prices_data.lz4",
        r"../data/06/26/prices_data.lz4",
        r"../data/06/27/prices_data.lz4",
        r"../data/06/30/prices_data.lz4",

        # Données de juillet 2025
        r"../data/07/02/prices_data.lz4",
        r"../data/07/03/prices_data.lz4",
        r"../data/07/07/prices_data.lz4",
        r"../data/07/08/prices_data.lz4",
        r"../data/07/09/prices_data.lz4",
        r"../data/07/10/prices_data.lz4",
        r"../data/07/11/prices_data.lz4",
        r"../data/07/14/prices_data.lz4",
        r"../data/07/15/prices_data.lz4",
        r"../data/07/16/prices_data.lz4",
        r"../data/07/17/prices_data_2025-07-17.lz4",
        r"../data/07/18/prices_data_2025-07-18.lz4",
        r"../data/07/21/prices_data.lz4",
        r"../data/07/30/prices_data.lz4",

        # Données d'août 2025
        r"../data/08/01/prices_data.lz4",
    ]

    # Initialisation des composants principaux du système
    config_manager = ConfigManager()  # Gestionnaire de configuration des paramètres
    memoire = SimulationMemoire()     # Mémoire des configurations déjà testées
    simulation_runner = SimulationRunner(data_files, memoire)  # Exécuteur de simulations
    optimizer = Optimizer(config_manager.default_param_configs, simulation_runner)  # Optimiseur

    # Charger la meilleure configuration précédente ou utiliser les valeurs par défaut
    best_params, best_pnl, best_iteration = config_manager.load_best_config()

    if best_params is None or not config_manager.validate_params(best_params):
        print(f"{Fore.YELLOW}No valid best configuration found, using default parameters.")
        current_params = config_manager.get_default_params()
        best_pnl = -10000  # Valeur initiale très basse pour s'assurer qu'elle sera améliorée
        best_iteration = 0
    else:
        print(f"{Fore.YELLOW}Loaded best configuration: {best_params}, PnL: ${best_pnl:.2f}")
        current_params = best_params.copy()

    # Variables de contrôle de la boucle d'optimisation
    iteration = 0          # Compteur d'itérations global
    param_idx = 0          # Index du paramètre actuellement optimisé
    num_params = len(config_manager.default_param_configs)  # Nombre total de paramètres

    def generate_random_params(configs, memoire_config):
        """
        Génère un ensemble aléatoire de paramètres qui n'ont pas encore été testés.

        Cette fonction évite de retester des configurations déjà évaluées en utilisant
        la mémoire des simulations précédentes.

        Args:
            configs (dict): Configuration des paramètres avec leurs plages de valeurs
            memoire_config (SimulationMemoire): Objet mémoire pour vérifier les configurations testées

        Returns:
            dict: Nouvelle configuration de paramètres non testée, ou None si impossible
        """
        max_attempts = 1000  # Prévenir les boucles infinies
        attempts = 0
        while attempts < max_attempts:
            random_params = {}
            for param, config in configs.items():
                min_val = config['min_value']
                max_val = config['max_value']
                step = config['step']
                # Générer toutes les valeurs possibles selon le pas défini
                possible_values = [min_val + i * step for i in range(int((max_val - min_val) / step) + 1)]
                random_params[param] = random.choice(possible_values)

            # Vérifier si cette configuration n'a pas déjà été testée
            if not memoire_config.has_been_tested(random_params):
                print(f"{Fore.GREEN}Generated new untested configuration: {random_params}")
                return random_params
            attempts += 1

        print(f"{Fore.RED}Erreur : Impossible de trouver une configuration non testée "
              f"après {max_attempts} tentatives.")
        return None  # Retourner None si aucune configuration non testée n'est trouvée

    # Boucle principale d'optimisation
    try:
        while True:
            iteration += 1
            param_name = list(config_manager.default_param_configs.keys())[param_idx]

            print(f"\n{Fore.YELLOW}{Style.BRIGHT}=== Simulation Itération {iteration} "
                  f"(Optimisation de {param_name}) ===")

            # Étape 1: Affichage de la configuration actuelle
            print(f"{Fore.YELLOW}Étape 1: Affichage de la configuration")
            print(f"Current parameters: {current_params}")

            # Étape 2: Optimisation par descente de coordonnées
            # Cette méthode optimise un paramètre à la fois en gardant les autres fixes
            print(f"{Fore.YELLOW}Étape 2: Optimisation par descente par coordonnées")
            current_params, current_pnl, has_untested = optimizer.coordinate_descent_step(
                current_params, param_idx, iteration)

            # Étape 3: Vérification et sauvegarde de la meilleure configuration
            print(f"{Fore.YELLOW}Étape 3: Vérification de la meilleure configuration")
            if current_pnl > best_pnl:
                print(f"{Fore.GREEN}Nouveau meilleur PnL trouvé : ${current_pnl:.2f}")
                best_params = current_params.copy()
                best_pnl = current_pnl
                best_iteration = iteration
                print(f"{Fore.YELLOW}Saving best configuration: {best_params}")
                config_manager.save_best_config(best_params, best_pnl, best_iteration)
            else:
                print(f"{Fore.RED}Pas d'amélioration du PnL. Current PnL: ${current_pnl:.2f}")

            # Étape 4: Passage au paramètre suivant
            print(f"{Fore.YELLOW}Étape 5: Passage au paramètre suivant")
            if not has_untested:
                print(f"{Fore.YELLOW}Toutes les valeurs pour {param_name} ont été testées.")

            param_idx = (param_idx + 1) % num_params  # Passer au paramètre suivant (cycle)

            # Après un cycle complet de paramètres, redémarrer le serveur web et essayer de générer une nouvelle configuration
            if param_idx == 0:
                print(f"{Fore.YELLOW}Full cycle completed. Restarting web server and "
                      f"checking for untested configurations.")

                # Terminer le processus serveur web actuel
                terminate_web_server_process(web_process)

                # Démarrer un nouveau processus serveur web
                web_process = start_web_server_process()

                # Si aucune valeur non testée n'est disponible, essayer de générer une nouvelle configuration aléatoire
                if not has_untested:
                    new_params = generate_random_params(config_manager.default_param_configs, memoire)
                    if new_params is None:
                        # Aucune nouvelle configuration disponible, terminer l'optimisation
                        print(f"{Fore.GREEN}Simulation terminée : aucune nouvelle configuration "
                              f"non testée disponible.")
                        print(f"Meilleure configuration trouvée à l'itération {best_iteration} "
                              f"avec un PnL de ${best_pnl:.2f}")
                        print(f"Paramètres : {best_params}")
                        break
                    print(f"{Fore.GREEN}Génération d'une nouvelle configuration aléatoire pour continuer.")
                    current_params = new_params
                    print(f"{Fore.YELLOW}Nouvelle configuration aléatoire: {current_params}")

            # Petite pause pour éviter de surcharger le système
            time.sleep(0.1)

    finally:
        # S'assurer que le processus serveur web est terminé quand la boucle principale se termine
        terminate_web_server_process(web_process)
        print(f"{Fore.GREEN}Main program terminated.")