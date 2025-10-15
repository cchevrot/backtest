"""
SimulationRunner — Exécuteur de simulations pour le backtesting de stratégies de trading.

==== RÔLE DE LA CLASSE ====
SimulationRunner exécute les backtests de la stratégie AlgoEchappee sur plusieurs 
fichiers de données historiques et calcule les métriques de performance.

C'est le moteur d'exécution qui transforme des paramètres de stratégie en résultats 
mesurables (PnL, ROI, etc.).

==== RESPONSABILITÉS PRINCIPALES ====
1. Charger les données de prix compressées (format LZ4) depuis les fichiers
2. Exécuter la stratégie sur chaque journée de trading
3. Paralléliser l'exécution pour accélérer les tests (multiprocessing)
4. Calculer les métriques agrégées (PnL total, ROI, écart-type, etc.)
5. Utiliser une mémoire pour éviter de retester les mêmes configurations

==== ATTRIBUTS ====
- data_files : list[str] - Chemins vers les fichiers de données de prix (ex: ../data/06/17/prices_data.lz4)
  Chaque fichier contient les prix d'une journée de trading au format compressé LZ4
  
- memoire : SimulationMemoire - Cache des simulations déjà exécutées
  Évite de retester les mêmes configurations de paramètres

==== MÉTHODES PRINCIPALES ====
- run_single_file_simulation(data_file, params) : Exécute la simulation sur UN fichier
  * Charge les données de prix via PriceLogger
  * Crée une instance de AlgoEchappee avec les paramètres fournis
  * Itère sur chaque tick de prix (timestamp, ticker, price)
  * Met à jour la SortedPnlTable et exécute la stratégie
  * Ferme toutes les positions en fin de journée
  * Retourne les métriques : file_pnl, file_invested_capital, num_traded, roi
  
- run_simulation(params) : Exécute la simulation sur TOUS les fichiers (parallélisé)
  * Utilise multiprocessing.Pool pour exécuter en parallèle
  * Agrège les résultats de toutes les journées
  * Calcule les métriques totales :
    - total_pnl : PnL cumulé sur toutes les journées
    - total_invested_capital : Capital total investi
    - total_roi : Retour sur investissement global
    - daily_pnl_std : Écart-type des PnL journaliers (mesure de volatilité)
    - positive_or_zero_pnl_days : Nombre de jours rentables ou neutres
    - negative_pnl_days : Nombre de jours perdants
  * Retourne un dictionnaire avec toutes les métriques
  
- run_simulation_display(params, iteration) : Wrapper avec affichage et cache
  * Vérifie si la configuration a déjà été testée (via memoire)
  * Si déjà testée : récupère les métriques depuis le cache
  * Sinon : exécute run_simulation() et sauvegarde dans le cache
  * Affiche les paramètres et résultats dans un tableau formaté
  * Retourne uniquement le total_pnl (utilisé pour l'optimisation)

==== FICHIERS D'ENTRÉE ====
Format : prices_data.lz4 (fichiers compressés LZ4)
Structure : Chaque ligne contient (timestamp, ticker, price)
Exemple de fichiers :
  - ../data/06/17/prices_data.lz4 (17 juin 2025)
  - ../data/07/18/prices_data_2025-07-18.lz4 (18 juillet 2025)
  - etc.

Ces fichiers sont lus par PriceLogger qui décompresse et parse les données.

==== CLASSES UTILISÉES ====
- PriceLogger : Charge et décompresse les fichiers de prix LZ4
  Fournit un itérateur sur (timestamp, ticker, price)
  
- SortedPnlTable : Table de classement des tickers par performance
  Stocke les prix courants et calcule les PnL de marché
  
- AlgoEchappee : La stratégie de trading à tester
  Prend les décisions d'achat/vente selon ses paramètres
  
- SimulationMemoire : Cache des résultats de simulations
  Évite de recalculer les mêmes configurations

==== FLUX D'EXÉCUTION ====
1. Optimizer appelle run_simulation_display(params, iteration)
2. SimulationRunner vérifie le cache (memoire)
3. Si pas en cache : exécute run_simulation(params)
4. run_simulation() crée un Pool de processus
5. Chaque processus exécute run_single_file_simulation() sur un fichier
6. Les résultats sont agrégés et retournés
7. Les métriques sont sauvegardées dans le cache
8. Le total_pnl est retourné à Optimizer pour comparaison

==== PARALLÉLISATION ====
Utilise multiprocessing.Pool pour exécuter plusieurs journées en parallèle.
Exemple : Si 25 fichiers et 8 cœurs CPU, exécution ~3x plus rapide.

==== MÉTRIQUES CALCULÉES ====
- PnL (Profit and Loss) : Gains/pertes en valeur absolue ($)
- ROI (Return on Investment) : PnL / Capital Investi × 100 (%)
- Écart-type des PnL journaliers : Mesure de la volatilité/risque
- Taux de réussite : Proportion de jours positifs
"""

import os
import json
import pandas as pd
import numpy as np
from colorama import Fore, Style
from price_logger import PriceLogger
from sorted_pnl_table import SortedPnlTable
from algo_echappee import AlgoEchappee
from multiprocessing import Pool

class SimulationRunner:
    """Exécute les simulations pour une liste de fichiers de données avec des paramètres donnés."""
    
    def __init__(self, data_files, memoire):
        self.data_files = data_files
        self.memoire = memoire

    def run_single_file_simulation(self, data_file, params):
        """Exécute une simulation pour un seul fichier de données avec les paramètres donnés."""
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
            trade_start_hour=params.get('trade_start_hour', "09:30")
        )
        timestamp = 0.0

        for timestamp, ticker, price in logger.read_all():
            table.update_ticker(ticker, price, timestamp)
            algo.portfolio.refresh_prices(table)
            if table.has_been_resorted():
                algo.main(table, timestamp)
        algo.portfolio.close_all(table, timestamp)
        
        file_pnl = algo.portfolio.total_pnl
        traded_tickers = set(trade['ticker'] for trade in algo.portfolio.trades if trade['status'] == 'closed')
        num_traded = len(traded_tickers)
        file_invested_capital = sum(trade['invested_amount'] for trade in algo.portfolio.trades if trade['status'] == 'closed')
        roi = (file_pnl / file_invested_capital * 100) if file_invested_capital != 0 else float('inf')

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

    def run_simulation(self, params):
        """Exécute une simulation avec les paramètres donnés et retourne les métriques."""
        total_pnl = 0.0
        total_invested_capital = 0.0
        daily_pnls = []
        positive_or_zero_pnl_days = 0
        negative_pnl_days = 0

        # Créer un pool de processus
        with Pool() as pool:
            # Préparer les arguments pour chaque fichier
            tasks = [(data_file, params) for data_file in self.data_files]
            # Exécuter les simulations en parallèle
            results = pool.starmap(self.run_single_file_simulation, tasks)

        for result in results:
            file_pnl = result['file_pnl']
            total_pnl += file_pnl
            daily_pnls.append(file_pnl)
            if file_pnl >= 0:
                positive_or_zero_pnl_days += 1
            else:
                negative_pnl_days += 1
            total_invested_capital += result['file_invested_capital']

        total_roi = (total_pnl / total_invested_capital * 100) if total_invested_capital != 0 else float('inf')
        daily_pnl_std = np.std(daily_pnls) if len(daily_pnls) > 1 else 0.0

        total_pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
        print(f"\n{Fore.CYAN}{Style.BRIGHT}PnL global cumulé pour l'itération: {total_pnl_color}${total_pnl:.2f}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Capital investi total: ${total_invested_capital:.2f}")
        print(f"{Fore.CYAN}ROI total (PnL/Capital Investi): {total_roi:.2f}%")
        print(f"{Fore.CYAN}Écart-type des PnL Journaliers: ${daily_pnl_std:.2f}")
        print(f"{Fore.CYAN}Jours avec PnL Positif ou Nul: {positive_or_zero_pnl_days}")
        print(f"{Fore.CYAN}Jours avec PnL Négatif: {negative_pnl_days}")

        return {
            'total_pnl': total_pnl,
            'total_invested_capital': total_invested_capital,
            'total_roi': total_roi,
            'daily_pnl_std': daily_pnl_std,
            'positive_or_zero_pnl_days': positive_or_zero_pnl_days,
            'negative_pnl_days': negative_pnl_days
        }

    def run_simulation_display(self, params, iteration):
        """Affiche les paramètres et le PnL sous forme de tableau clair."""
        key = json.dumps(params, sort_keys=True)
        
        if self.memoire.has_been_tested(params):
            metrics = self.memoire.get_pnl(params)
            print(f"{Fore.MAGENTA}Configuration déjà testée. Métriques récupérées depuis la mémoire: total_pnl=${metrics['total_pnl']:.2f}, total_roi={metrics['total_roi']:.2f}%")
            return metrics['total_pnl']

        title = f"Configuration Itération {iteration}"
        print(f"\n{Fore.CYAN}{Style.BRIGHT}┌{'─' * 50}┐")
        print(f"{Fore.CYAN}{Style.BRIGHT}│ {title:^48} │")
        print(f"{Fore.CYAN}{Style.BRIGHT}├{'─' * 50}┤")

        param_data = []
        for param, value in params.items():
            formatted_value = f"{value:.0f}s" if param == 'min_escape_time' else str(value)
            param_data.append([param.replace('_', ' ').title(), formatted_value])
        
        df = pd.DataFrame(param_data, columns=['Paramètre', 'Valeur'])
        print(df.to_string(index=False, justify='left', col_space={'Paramètre': 30, 'Valeur': 10}))

        metrics = self.run_simulation(params)

        if metrics['total_pnl'] is not None:
            color = Fore.GREEN if metrics['total_pnl'] > 0 else Fore.RED
            print(f"{Fore.CYAN}{Style.BRIGHT}├{'─' * 50}┤")
            print(f"{Fore.CYAN}{Style.BRIGHT}│ PnL: {color}${metrics['total_pnl']:.2f}{' ' * (43 - len(f'${metrics['total_pnl']:.2f}'))}│")
        
        print(f"{Fore.CYAN}{Style.BRIGHT}└{'─' * 50}┘")

        # Écriture séquentielle dans memoire_config.json
        self.memoire.add_result(params, metrics)
        return metrics['total_pnl']