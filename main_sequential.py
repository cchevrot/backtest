import json
import os
import pandas as pd
import numpy as np
from colorama import init, Fore, Style
from config_manager import ConfigManager
from simulation_runner import SimulationRunner
from memoire_config import SimulationMemoire

# Initialiser colorama pour les couleurs dans la console
init(autoreset=True)

def main_sequential():
    """Exécute la simulation séquentielle avec la meilleure configuration de best_config.json."""
    
    # Liste des fichiers de données (identique à celle dans main.py)
    data_files = [
        r"../data/prices_data/06/2025-06-17-prices_data.lz4",
        r"../data/prices_data/06/2025-06-18-prices_data.lz4",
        r"../data/prices_data/06/2025-06-20-prices_data.lz4",
        r"../data/prices_data/06/2025-06-23-prices_data.lz4",
        r"../data/prices_data/06/2025-06-24-prices_data.lz4",
        r"../data/prices_data/06/2025-06-25-prices_data.lz4",
        r"../data/prices_data/06/2025-06-26-prices_data.lz4",
        r"../data/prices_data/06/2025-06-27-prices_data.lz4",
        r"../data/prices_data/06/2025-06-30-prices_data.lz4",
        r"../data/prices_data/07/2025-07-02-prices_data.lz4",
        r"../data/prices_data/07/2025-07-03-prices_data.lz4",
        r"../data/prices_data/07/2025-07-07-prices_data.lz4",
        r"../data/prices_data/07/2025-07-08-prices_data.lz4",
        r"../data/prices_data/07/2025-07-09-prices_data.lz4",
        r"../data/prices_data/07/2025-07-10-prices_data.lz4",
        r"../data/prices_data/07/2025-07-11-prices_data.lz4",
        r"../data/prices_data/07/2025-07-14-prices_data.lz4",
        r"../data/prices_data/07/2025-07-15-prices_data.lz4",
        r"../data/prices_data/07/2025-07-16-prices_data.lz4",
        r"../data/prices_data/07/2025-07-17-prices_data.lz4",
        r"../data/prices_data/07/2025-07-18-prices_data.lz4",
        r"../data/prices_data/07/2025-07-21-prices_data.lz4",
        r"../data/prices_data/07/2025-07-30-prices_data.lz4",
        r"../data/prices_data/08/2025-08-01-prices_data.lz4",
    ]

    # Initialisation des composants
    config_manager = ConfigManager()
    memoire = SimulationMemoire()
    simulation_runner = SimulationRunner(data_files, memoire)

    # Charger la meilleure configuration
    best_params, best_pnl, best_iteration = config_manager.load_best_config()
    
    if best_params is None or not config_manager.validate_params(best_params):
        print(f"{Fore.RED}Erreur : Aucune configuration valide trouvée dans best_config.json")
        print(f"{Fore.YELLOW}Utilisation des paramètres par défaut.")
        best_params = config_manager.get_default_params()
        best_pnl = None
        best_iteration = 0
    else:
        print(f"{Fore.GREEN}Meilleure configuration chargée : {best_params}")
        print(f"{Fore.GREEN}PnL de la meilleure configuration : ${best_pnl:.2f} (itération {best_iteration})")

    param_data = []
    for param, value in best_params.items():
        formatted_value = f"{value:.0f}s" if param == 'min_escape_time' else str(value)
        param_data.append([param.replace('_', ' ').title(), formatted_value])
    
    df = pd.DataFrame(param_data, columns=['Paramètre', 'Valeur'])
    print(df.to_string(index=False, justify='left', col_space={'Paramètre': 30, 'Valeur': 10}))

    total_pnl = 0.0
    total_invested_capital = 0.0
    daily_pnls = []
    positive_or_zero_pnl_days = 0
    negative_pnl_days = 0
    daily_results = []

    # Exécuter la simulation pour chaque fichier (jour) séquentiellement
    for data_file in data_files:
        result = simulation_runner.run_single_file_simulation(data_file, best_params)
        file_pnl = result['file_pnl']
        file_invested_capital = result['file_invested_capital']
        num_traded = result['num_traded']
        roi = result['roi']
        
        # Ajouter au total
        total_pnl += file_pnl
        total_invested_capital += file_invested_capital
        daily_pnls.append(file_pnl)
        if file_pnl >= 0:
            positive_or_zero_pnl_days += 1
        else:
            negative_pnl_days += 1
        
        # Afficher les détails pour ce jour
        file_pnl_color = Fore.GREEN if file_pnl >= 0 else Fore.RED
        day = os.path.basename(os.path.dirname(data_file)) + "/" + os.path.basename(data_file).replace("prices_data.lz4", "")
        print(f"{Fore.CYAN}{Style.BRIGHT}│ {day:<15} │ {file_pnl_color}{file_pnl:<15.2f}{Style.RESET_ALL} │ {file_invested_capital:<20.2f} │ {roi:<15.2f} │ {num_traded:<15} │")
        
        daily_results.append({
            'file_pnl': file_pnl,
            'file_invested_capital': file_invested_capital,
            'num_traded': num_traded,
            'roi': roi
        })

    # Calculer les métriques globales
    total_roi = (total_pnl / total_invested_capital * 100) if total_invested_capital != 0 else float('inf')
    daily_pnl_std = np.std(daily_pnls) if len(daily_pnls) > 1 else 0.0

    # Afficher les résultats globaux
    print(f"\n{Fore.CYAN}{Style.BRIGHT}Résultats globaux :")
    print(f"{Fore.CYAN}{Style.BRIGHT}├{'─' * 50}┤")
    print(f"{Fore.CYAN}PnL global cumulé : {Fore.GREEN if total_pnl >= 0 else Fore.RED}${total_pnl:.2f}")
    print(f"{Fore.CYAN}Capital investi total : ${total_invested_capital:.2f}")
    print(f"{Fore.CYAN}ROI total : {total_roi:.2f}%")
    print(f"{Fore.CYAN}Écart-type des PnL journaliers : ${daily_pnl_std:.2f}")
    print(f"{Fore.CYAN}Jours avec PnL positif ou nul : {positive_or_zero_pnl_days}")
    print(f"{Fore.CYAN}Jours avec PnL négatif : {negative_pnl_days}")
    print(f"{Fore.CYAN}{Style.BRIGHT}└{'─' * 50}┘")

    # Sauvegarder les métriques dans la mémoire
    metrics = {
        'total_pnl': total_pnl,
        'total_invested_capital': total_invested_capital,
        'total_roi': total_roi,
        'daily_pnl_std': daily_pnl_std,
        'positive_or_zero_pnl_days': positive_or_zero_pnl_days,
        'negative_pnl_days': negative_pnl_days
    }
    memoire.add_result(best_params, metrics)

if __name__ == "__main__":
    main_sequential()