"""
SingleFileSimulator — Exécuteur de simulation sur un seul fichier de données.

==== RÔLE DE LA CLASSE ====
SingleFileSimulator exécute un backtest de la stratégie AlgoEchappee sur un seul 
fichier de données historiques et calcule les métriques de performance pour ce fichier.

C'est l'unité de base d'exécution utilisée par MultiFileSimulator pour paralléliser 
les tests sur plusieurs journées de trading.

==== RESPONSABILITÉS ====
1. Charger un fichier de prix compressé (format LZ4)
2. Exécuter la stratégie AlgoEchappee tick par tick
3. Calculer les métriques de performance pour le fichier
4. Retourner un dictionnaire de résultats (PnL, ROI, capital investi, etc.)

==== MÉTHODE PRINCIPALE ====
- run(data_file, params) : Méthode statique qui exécute la simulation
  * Charge les données via PriceLogger
  * Crée une SortedPnlTable et une instance AlgoEchappee
  * Itère sur chaque tick de prix (timestamp, ticker, price)
  * Met à jour la table et exécute la stratégie
  * Ferme toutes les positions en fin de fichier
  * Retourne : file_pnl, file_invested_capital, num_traded, roi

==== CLASSES UTILISÉES ====
- PriceLogger : Charge et décompresse les fichiers de prix LZ4
- SortedPnlTable : Table de classement des tickers par performance
- AlgoEchappee : La stratégie de trading à tester
- Portfolio : Gère les positions et calcule le PnL (via AlgoEchappee)

==== UTILISATION ====
Cette classe est conçue pour être utilisée par multiprocessing.Pool dans MultiFileSimulator.
Elle est stateless (pas d'attributs d'instance) pour faciliter la sérialisation.
"""

import os
from colorama import Fore, Style
from price_logger import PriceLogger
from sorted_pnl_table import SortedPnlTable
from algo_echappee import AlgoEchappee


class SingleFileSimulator:
    """★★★ NIVEAU 3 ★★★ Exécute une simulation sur un seul fichier de données."""
    
    @staticmethod
    def run_single_file(data_file, params, verbose=True):
        """
        ★★★ NIVEAU 3 : SIMULATION SUR UN SEUL FICHIER ★★★
        Exécute la stratégie sur UN SEUL fichier .lz4 (une journée de trading)
        
        Hiérarchie des appels :
        ParamOptimizer._test_params_on_all_files()      [Niveau 1 - Optimisation]
            └─> MultiFileSimulator.run_all_files()       [Niveau 2 - TOUS les fichiers]
                  └─> SingleFileSimulator.run_single_file() [Niveau 3 - UN fichier] ★ VOUS ÊTES ICI
        
        Args:
            data_file: Chemin vers le fichier .lz4 à traiter
            params: Dictionnaire des paramètres de la stratégie
            
        Returns:
            Dictionnaire avec métriques du fichier (file_pnl, roi, num_traded, etc.)
        """
        if not os.path.exists(data_file):
            print(f"{Fore.RED}Erreur: Fichier {data_file} n'existe pas")
            return {
                'file_pnl': 0.0,
                'file_invested_capital': 0.0,
                'num_traded': 0,
                'roi': 0.0
            }

        logger = PriceLogger(data_file, flush_interval=10)
        table = SortedPnlTable()
        algo = AlgoEchappee(
            take_profit_market_pnl=params['take_profit_market_pnl'],
            min_escape_time=params['min_escape_time'],
            trail_stop_market_pnl=params['trail_stop_market_pnl'],
            stop_echappee_threshold=params['stop_echappee_threshold'],
            start_echappee_threshold=params['start_echappee_threshold'],
            min_market_pnl=params['min_market_pnl'],
            top_n_threshold=params['top_n_threshold'],
            trade_interval_minutes=params['trade_interval_minutes'],
            trade_value_eur=params['trade_value_eur'],
            max_pnl_timeout_minutes=params.get('max_pnl_timeout_minutes', 60.0),
            max_trades_per_day=params.get('max_trades_per_day', 3),
            trade_cutoff_hour=params.get('trade_cutoff_hour', "14:00"),
            trade_start_hour=params.get('trade_start_hour', "09:30"),
            verbose=verbose
        )
        timestamp = 0.0

        for timestamp, ticker, price in logger.read_all():
            try:
                table.update_ticker(ticker, price, timestamp)
            except Exception as e:
                # Logger l'erreur dans un fichier
                with open('error_ticks.log', 'a', encoding='utf-8') as f:
                    f.write(f"ERROR: {e.__class__.__name__}: {e}\n")
                    f.write(f"  File: {data_file}\n")
                    f.write(f"  Timestamp: {timestamp}, Ticker: {ticker}, Price: {price} (type: {type(price).__name__})\n\n")
                continue
            
            algo.portfolio.refresh_prices(table)
            if table.has_been_resorted():
                algo.main(table, timestamp)
        algo.portfolio.close_all(table, timestamp)
        
        file_pnl = algo.portfolio.total_pnl
        traded_tickers = set(trade['ticker'] for trade in algo.portfolio.trades if trade['status'] == 'closed')
        num_traded = len(traded_tickers)
        file_invested_capital = sum(trade['invested_amount'] for trade in algo.portfolio.trades if trade['status'] == 'closed')
        roi = (file_pnl / file_invested_capital * 100) if file_invested_capital != 0 else float('inf')

        if verbose:
            file_pnl_color = Fore.GREEN if file_pnl >= 0 else Fore.RED
            print(f"\n{Fore.CYAN}{Style.BRIGHT}Résultats pour le fichier: {data_file}")
            print(f"{Fore.CYAN}PnL global: {file_pnl_color}${file_pnl:.2f}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Nombre d'actions tradées: {num_traded}")
            print(f"{Fore.CYAN}Capital investi: ${file_invested_capital:.2f}")
            print(f"{Fore.CYAN}ROI (PnL/Capital Investi): {roi:.2f}%" if file_invested_capital != 0 else f"{Fore.CYAN}ROI (PnL/Capital Investi): N/A")

        return {
            'file_pnl': file_pnl,
            'file_invested_capital': file_invested_capital,
            'num_traded': num_traded,
            'roi': roi
        }


def main():
    """Point d'entrée pour tester SingleFileSimulator."""
    import glob
    
    data_files = glob.glob('../data/**/*.lz4', recursive=True)
    
    if not data_files:
        print(f"{Fore.RED}Aucun fichier de données trouvé dans ../data")
        print(f"{Fore.YELLOW}Veuillez vérifier que des fichiers .lz4 existent dans le répertoire ../data")
        return
    
    test_params = {
        'take_profit_market_pnl': 0.015,
        'min_escape_time': 120.0,
        'trail_stop_market_pnl': 0.008,
        'stop_echappee_threshold': 0.012,
        'start_echappee_threshold': 0.010,
        'min_market_pnl': 0.005,
        'top_n_threshold': 10,
        'trade_interval_minutes': 5.0,
        'trade_value_eur': 1000.0,
        'max_pnl_timeout_minutes': 60.0,
        'max_trades_per_day': 3,
        'trade_cutoff_hour': "14:00",
        'trade_start_hour': "09:30"
    }
    
    print(f"{Fore.GREEN}{Style.BRIGHT}=== Test SingleFileSimulator ==={Style.RESET_ALL}")
    print(f"{Fore.CYAN}Fichier testé: {data_files[0]}")
    
    result = SingleFileSimulator.run_single_file(data_files[0], test_params)
    
    print(f"\n{Fore.GREEN}{Style.BRIGHT}=== Résumé ==={Style.RESET_ALL}")
    print(f"{Fore.CYAN}PnL: {Fore.GREEN if result['file_pnl'] >= 0 else Fore.RED}${result['file_pnl']:.2f}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}ROI: {result['roi']:.2f}%")
    print(f"{Fore.CYAN}Tickers tradés: {result['num_traded']}")
    print(f"{Fore.CYAN}Capital investi: ${result['file_invested_capital']:.2f}")


if __name__ == "__main__":
    main()
