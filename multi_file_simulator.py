"""
MultiFileSimulator — Exécuteur de simulations multi-fichiers pour le backtesting.

==== RÔLE DE LA CLASSE ====
MultiFileSimulator (NIVEAU 2) exécute les backtests de la stratégie AlgoEchappee sur plusieurs 
fichiers de données historiques et calcule les métriques de performance agrégées.

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
from multiprocessing import Pool
from single_file_simulator import SingleFileSimulator


class MultiFileSimulator:
    """★★★ NIVEAU 2 ★★★ Exécute les simulations sur TOUS les fichiers de données."""
    
    def __init__(self, data_files, parallel=True, verbose=True):
        self.data_files = data_files
        self.parallel = parallel
        self.verbose = verbose

    def run_single_file(self, data_file, params):
        """Délègue l'exécution à SingleFileSimulator (NIVEAU 3)."""
        return SingleFileSimulator.run_single_file(data_file, params, verbose=self.verbose)

    def run_all_files(self, params):
        """
        ★★★ NIVEAU 2 : SIMULATION SUR TOUS LES FICHIERS ★★★
        Exécute la stratégie avec les paramètres donnés sur TOUS les fichiers .lz4
        et agrège les résultats.
        
        Hiérarchie des appels :
        ParamOptimizer._test_params_on_all_files()      [Niveau 1 - Optimisation]
            └─> MultiFileSimulator.run_all_files()       [Niveau 2 - TOUS les fichiers] ★ VOUS ÊTES ICI
                  └─> SingleFileSimulator.run_single_file() [Niveau 3 - UN fichier]
        
        Args:
            params: Dictionnaire des paramètres de la stratégie
            
        Returns:
            Dictionnaire de métriques agrégées (total_pnl, total_roi, etc.)
        """
        from datetime import datetime
        start_time = datetime.now()
        
        total_pnl = 0.0
        total_invested_capital = 0.0
        daily_pnls = []
        positive_or_zero_pnl_days = 0
        negative_pnl_days = 0

        if self.parallel:
            # ═══════════════════════════════════════════════════════════
            # MODE PARALLÈLE : exécute TOUS les fichiers en même temps
            # ═══════════════════════════════════════════════════════════
            with Pool() as pool:
                # Préparer les arguments pour chaque fichier
                tasks = [(data_file, params, self.verbose) for data_file in self.data_files]
                # Appel au niveau 3 : SingleFileSimulator.run_single_file() pour CHAQUE fichier
                results = pool.starmap(SingleFileSimulator.run_single_file, tasks)
            
            # Agréger les résultats en parallèle (affichage à la fin uniquement)
            for result in results:
                file_pnl = result['file_pnl']
                total_pnl += file_pnl
                daily_pnls.append(file_pnl)
                if file_pnl >= 0:
                    positive_or_zero_pnl_days += 1
                else:
                    negative_pnl_days += 1
                total_invested_capital += result['file_invested_capital']
        else:
            # ═══════════════════════════════════════════════════════════
            # MODE SÉQUENTIEL : exécute les fichiers un par un
            # Affiche les métriques cumulées après CHAQUE fichier
            # ═══════════════════════════════════════════════════════════
            for data_file in self.data_files:
                # Appel au niveau 3 : SingleFileSimulator.run_single_file() pour UN fichier
                result = SingleFileSimulator.run_single_file(data_file, params, verbose=self.verbose)
                
                file_pnl = result['file_pnl']
                total_pnl += file_pnl
                daily_pnls.append(file_pnl)
                if file_pnl >= 0:
                    positive_or_zero_pnl_days += 1
                else:
                    negative_pnl_days += 1
                total_invested_capital += result['file_invested_capital']
                
                # Afficher les métriques cumulées après chaque fichier (mode verbose uniquement)
                if self.verbose:
                    current_total_roi = (total_pnl / total_invested_capital * 100) if total_invested_capital != 0 else float('inf')
                    current_daily_pnl_std = np.std(daily_pnls) if len(daily_pnls) > 1 else 0.0
                    
                    print(f"{Fore.YELLOW}  Métriques cumulées :")
                    print(f"{Fore.YELLOW}    Total PnL: {Fore.GREEN if total_pnl >= 0 else Fore.RED}${total_pnl:.2f}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}    Total Capital Investi: ${total_invested_capital:.2f}")
                    print(f"{Fore.YELLOW}    Total ROI: {current_total_roi:.2f}%")
                    print(f"{Fore.YELLOW}    Daily PnL Std: ${current_daily_pnl_std:.2f}")
                    print(f"{Fore.YELLOW}    Jours positifs/nuls: {positive_or_zero_pnl_days}")
                    print(f"{Fore.YELLOW}    Jours négatifs: {negative_pnl_days}\n")

        end_time = datetime.now()
        total_roi = (total_pnl / total_invested_capital * 100) if total_invested_capital != 0 else float('inf')
        daily_pnl_std = np.std(daily_pnls) if len(daily_pnls) > 1 else 0.0
        
        if self.verbose:
            # Affichage détaillé (mode par défaut)
            total_pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
            print(f"\n{Fore.CYAN}{Style.BRIGHT}PnL global cumulé pour l'itération: {total_pnl_color}${total_pnl:.2f}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Capital investi total: ${total_invested_capital:.2f}")
            print(f"{Fore.CYAN}ROI total (PnL/Capital Investi): {total_roi:.2f}%")
            print(f"{Fore.CYAN}Écart-type des PnL Journaliers: ${daily_pnl_std:.2f}")
            print(f"{Fore.CYAN}Jours avec PnL Positif ou Nul: {positive_or_zero_pnl_days}")
            print(f"{Fore.CYAN}Jours avec PnL Négatif: {negative_pnl_days}")
        else:
            # Affichage compact avec noms de paramètres
            duration = (end_time - start_time).total_seconds()
            pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
            
            print(f"\n{Fore.CYAN}{'═' * 80}")
            print(f"{Fore.CYAN}⏱  {start_time.strftime('%H:%M:%S')} → {end_time.strftime('%H:%M:%S')} ({duration:.0f}s) | {len(self.data_files)} fichiers | "
                  f"{positive_or_zero_pnl_days}+ {negative_pnl_days}-")
            print(f"{Fore.YELLOW}📊 start={params.get('trade_start_hour')} cut={params.get('trade_cutoff_hour')} "
                  f"minPnL={params.get('min_market_pnl')} TP={params.get('take_profit_market_pnl')} "
                  f"trail={params.get('trail_stop_market_pnl')} esc={params.get('min_escape_time')}s")
            print(f"{Fore.YELLOW}   maxTrades={params.get('max_trades_per_day')} "
                  f"val={params.get('trade_value_eur')}€ topN={params.get('top_n_threshold')} "
                  f"stop={params.get('stop_echappee_threshold')} start={params.get('start_echappee_threshold')}")
            print(f"{Fore.CYAN}💰 PnL: {pnl_color}${total_pnl:.2f}{Style.RESET_ALL} | "
                  f"ROI: {total_roi:.2f}% | Std: ${daily_pnl_std:.2f} | Capital: ${total_invested_capital:.2f}")
            print(f"{Fore.CYAN}{'═' * 80}{Style.RESET_ALL}")

        return {
            'total_pnl': total_pnl,
            'total_invested_capital': total_invested_capital,
            'total_roi': total_roi,
            'daily_pnl_std': daily_pnl_std,
            'positive_or_zero_pnl_days': positive_or_zero_pnl_days,
            'negative_pnl_days': negative_pnl_days
        }

    def run_all_files_display(self, params, iteration):
        """Affiche les paramètres et le PnL sous forme de tableau clair."""
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

        metrics = self.run_all_files(params)

        if metrics['total_pnl'] is not None:
            color = Fore.GREEN if metrics['total_pnl'] > 0 else Fore.RED
            print(f"{Fore.CYAN}{Style.BRIGHT}├{'─' * 50}┤")
            print(f"{Fore.CYAN}{Style.BRIGHT}│ PnL: {color}${metrics['total_pnl']:.2f}{' ' * (43 - len(f'${metrics['total_pnl']:.2f}'))}│")
        
        print(f"{Fore.CYAN}{Style.BRIGHT}└{'─' * 50}┘")

        return metrics['total_pnl']


def main():
    """Point d'entrée pour tester MultiFileSimulator."""
    import glob
    
    #data_files = glob.glob('../data/prices_data/**/*.lz4', recursive=True)
    data_files = glob.glob('../data/prices_data/dataset2/**/*.lz4', recursive=True)
    
    if not data_files:
        print(f"{Fore.RED}Aucun fichier de données trouvé dans ../data")
        print(f"{Fore.YELLOW}Veuillez vérifier que des fichiers .lz4 existent dans le répertoire ../data")
        return
    
    print(f"{Fore.CYAN}Fichiers de données trouvés: {len(data_files)}")
    for f in data_files[:3]:
        print(f"{Fore.CYAN}  - {f}")
    if len(data_files) > 3:
        print(f"{Fore.CYAN}  ... et {len(data_files) - 3} autres")
    
    simulator = MultiFileSimulator(data_files, parallel=False)  # Sans parallélisme par défaut
    
    test_params = {
        'take_profit_market_pnl': 84,
        'min_escape_time': 60.0,
        'trail_stop_market_pnl': 50, #40,
        'stop_echappee_threshold': 1,
        'start_echappee_threshold': 1.5,
        'min_market_pnl': 36, #38,
        'top_n_threshold': 1,
        'trade_interval_minutes': 150000,
        'trade_value_eur': 100.0,
        'max_pnl_timeout_minutes': 6000.0,
        'max_trades_per_day': 3,
        'trade_cutoff_hour': "12:30",
        'trade_start_hour': "09:30"
    }
    
    print(f"\n{Fore.GREEN}{Style.BRIGHT}=== Simulation multi-fichiers ==={Style.RESET_ALL}")
    total_pnl = simulator.run_all_files_display(test_params, iteration=1)
    
    print(f"\n{Fore.GREEN}{Style.BRIGHT}=== Résultat final ==={Style.RESET_ALL}")
    print(f"{Fore.CYAN}PnL total: {Fore.GREEN if total_pnl >= 0 else Fore.RED}${total_pnl:.2f}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()

