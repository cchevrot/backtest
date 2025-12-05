#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
from colorama import init, Fore, Style
from param_optimizer_chat4 import TradingSimulator

# Initialisation de colorama (nécessaire sous Windows)
init(autoreset=True)

# ==========================================================
# CONFIGURATION FIXE (issue de best_config.json)
# ==========================================================
# CONFIG = {
#     "min_market_pnl": 39.0,
#     "take_profit_market_pnl": 100.0,
#     "trail_stop_market_pnl": 41.0,
#     "trade_start_hour": "09:15",
#     "trade_cutoff_hour": "13:00",
#     "min_escape_time": 83.0,
#     "max_trades_per_day": 3.0,
#     "stop_echappee_threshold": 1.5,
#     "start_echappee_threshold": 2.0,
#     "top_n_threshold": 1,
#     "trade_value_eur": 100.0,
#     "trade_interval_minutes": 150000,
#     "max_pnl_timeout_minutes": 6000.0
# }


CONFIG = {
    "min_market_pnl": 21.0,
    "take_profit_market_pnl": 97.0,
    "trail_stop_market_pnl": 37.0,
    "trade_start_hour": "09:00",
    "trade_cutoff_hour": "14:51",
    "min_escape_time": 83.0,
    "max_trades_per_day": 10.0,
    "stop_echappee_threshold": 1.5,
    "start_echappee_threshold": 2.0,
    "top_n_threshold": 1,
    "trade_value_eur": 100.0,
    "trade_interval_minutes": 150000,
    "max_pnl_timeout_minutes": 6000.0
}


# ==========================================================
# PROGRAMME PRINCIPAL
# ==========================================================
def main():

    # Liste des fichiers .lz4
    data_files = glob.glob("../data/prices_data/dataset3/**/*.lz4", recursive=True)

    print(Style.BRIGHT + Fore.MAGENTA + "==============================================")
    print(Style.BRIGHT + Fore.MAGENTA + "        🚀 TEST D'UN JEU DE PARAMÈTRES        ")
    print(Style.BRIGHT + Fore.MAGENTA + "==============================================\n")

    print(Fore.CYAN + "Nombre de fichiers chargés : " + Style.BRIGHT + str(len(data_files)))

    print("\n" + Fore.YELLOW + "Paramètres utilisés :" + Style.RESET_ALL + "\n")

    for k, v in CONFIG.items():
        print("  " + Fore.CYAN + "{:<25s}".format(k) + Style.RESET_ALL + " : " + str(v))

    print("\n" + Fore.YELLOW + "⏳ Exécution du backtest..." + Style.RESET_ALL + "\n")

    sim = TradingSimulator(data_files=data_files, parallel=True)
    pnl = sim.run(CONFIG)

    print(Style.BRIGHT + Fore.MAGENTA + "==============================================")
    print(Style.BRIGHT + Fore.MAGENTA + "                 📊 RÉSULTAT                  ")
    print(Style.BRIGHT + Fore.MAGENTA + "==============================================")

    print(Style.BRIGHT + Fore.GREEN + "PNL total : {:.2f} €".format(pnl) + Style.RESET_ALL)

    print(Style.BRIGHT + Fore.MAGENTA + "==============================================" + Style.RESET_ALL)


if __name__ == "__main__":
    main()
