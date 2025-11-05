import os
import pandas as pd
import numpy as np
from colorama import init, Fore, Style
from config_manager import ConfigManager
from simulation_runner import SimulationRunner
from memoire_config import SimulationMemoire
import glob

# Initialiser colorama pour les couleurs dans la console
init(autoreset=True)

def main_sequential():
    """Exécute la simulation séquentielle avec la meilleure configuration de best_config.json."""
    
    # Liste des fichiers de données (identique à celle dans main.py)
    data_files = glob.glob('C:/projets/bot/data/prices_data/dataset3/**/*.lz4', recursive=True)
    # Liste des fichiers de données (identique à celle dans main.py)

    # Initialisation des composants
    config_manager = ConfigManager()
    simulation_runner = SimulationRunner(data_files, parallel=True)


    #best_params = config_manager.get_default_params() # config_manager.load_best_config()
    best_params = {'trade_start_hour': '09:30', 'trade_cutoff_hour': '13:45', 'min_market_pnl': 43.0, 'take_profit_market_pnl': 70.0, 'trail_stop_market_pnl': 1000, 'min_escape_time': 83.0, 'max_trades_per_day': 10, 'trade_value_eur': 100.0, 'top_n_threshold': 1, 'stop_echappee_threshold': 1, 'start_echappee_threshold': 1.5, 'trade_interval_minutes': 150000, 'max_pnl_timeout_minutes': 6000.0}
    print(best_params)
    # best_params =  {
    #         'trade_start_hour': {  # Nouveau paramètre
    #             'initial_value': "09:30", 
    #             'min_value': "09:30", 
    #             'max_value': "18:00", 
    #             'step': 30  # Pas de 1 heure, en minutes
    #         },
    #         'trade_cutoff_hour': {
    #             'initial_value': "13:45", # "13:45", 
    #             'min_value': "09:00", 
    #             'max_value': "18:00", 
    #             'step': 30  # Pas de 1 heure, en minutes
    #         },


    #         'min_market_pnl': {
               
    #             'initial_value': 43.0,
    #             'min_value':0.0, 'max_value': 200.0, 'step': 1.0
    #         },
    #         'take_profit_market_pnl': {
    #             'initial_value': 70.0,
    #             'min_value': 0.0, 'max_value': 200.0, 'step': 4
    #         },
    #         'trail_stop_market_pnl': {
    #             'initial_value': 1000,
    #             'min_value': 0.0, 'max_value': 200.0, 'step': 5
    #         },
  
    #         'min_escape_time': {
    #             'initial_value':83.0,
    #             'min_value': 0, 'max_value': 200.0, 'step': 60
    #         },
    #         'max_trades_per_day': {
    #             'initial_value': 10,
    #             'min_value': 0, 'max_value': 200, 'step': 2
    #         },
    #         'trade_value_eur': {
    #             'initial_value': 100.0,
    #             'min_value': 100.0, 'max_value': 100.0, 'step': 1.0
    #         },
    #         'top_n_threshold': {
    #             'initial_value': 1,
    #             'min_value': 0, 'max_value': 200, 'step': 1
    #         },
    #         'stop_echappee_threshold': {
    #             'initial_value': 1,
    #             'min_value': 0, 'max_value': 200, 'step': 0.5
    #         },
    #         'start_echappee_threshold': {
    #             'initial_value': 1.5,
    #             'min_value': 0, 'max_value': 200, 'step': 0.5
    #         },

    #         'trade_interval_minutes': {
    #             'initial_value': 150000,
    #             'min_value': 150000, 'max_value': 150000, 'step': 50
    #         },

    #         'max_pnl_timeout_minutes': {
    #             'initial_value': 6000.0,
    #             'min_value': 6000.0, 'max_value': 6000.0, 'step': 6000.0
    #         },



    #     }
    # param_data = []
    # for param, value in best_params.items():
    #     formatted_value = f"{value:.0f}s" if param == 'min_escape_time' else str(value)
    #     param_data.append([param.replace('_', ' ').title(), formatted_value])
    
    # df = pd.DataFrame(param_data, columns=['Paramètre', 'Valeur'])
    # print(df.to_string(index=False, justify='left', col_space={'Paramètre': 30, 'Valeur': 10}))

    result = simulation_runner.run_simulation( best_params)
    print(result)
    return



if __name__ == "__main__":
    main_sequential()