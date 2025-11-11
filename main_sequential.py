import os
import pandas as pd
import numpy as np
from colorama import init, Fore, Style
from config_manager import ConfigManager
from multi_file_simulator import MultiFileSimulator
from memoire_config import SimulationMemoire
import glob

# Initialiser colorama pour les couleurs dans la console
init(autoreset=True)

def main_sequential():
    """Exécute la simulation séquentielle avec la meilleure configuration de best_config.json."""
    
    # Liste des fichiers de données (identique à celle dans main.py)
    data_files = glob.glob('C:/projets/bot/data/prices_data/dataset3/**/*.lz4', recursive=True)

    # Initialisation des composants
    simulation_runner = MultiFileSimulator(data_files, parallel=True)

    best_params = {'trade_start_hour': '09:30', 'trade_cutoff_hour': '13:45', 'min_market_pnl': 43.0, 'take_profit_market_pnl': 70.0, 'trail_stop_market_pnl': 1000, 'min_escape_time': 83.0, 'max_trades_per_day': 10, 'trade_value_eur': 100.0, 'top_n_threshold': 1, 'stop_echappee_threshold': 1, 'start_echappee_threshold': 1.5, 'trade_interval_minutes': 150000, 'max_pnl_timeout_minutes': 6000.0}

    result = simulation_runner.run_all_files(best_params)
    print(result)
    return



if __name__ == "__main__":
    main_sequential()