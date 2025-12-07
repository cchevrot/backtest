import numpy as np
from portfolio import Portfolio
from datetime import datetime, timedelta

"""
AlgoEchappee — Stratégie de trading basée sur l'identification de tickers « en échappée ».

==== PRINCIPE DE LA STRATÉGIE ====
Identifie les actions "en échappée" = actions qui progressent fortement par rapport 
à la moyenne du marché. Utilise une approche statistique basée sur l'écart-type.

==== DÉTECTION DES ÉCHAPPÉES ====
1. Calcule la moyenne et l'écart-type des PnL des 15 meilleurs tickers
2. Seuil d'entrée = moyenne + (start_echappee_threshold × écart-type)
3. Un ticker est "en échappée" si :
   - Son PnL dépasse le seuil d'entrée
   - Il reste dans le top N pendant min_escape_time secondes
   - Son PnL dépasse min_market_pnl

==== GESTION DES POSITIONS OUVERTES ====
Fermeture automatique si :
- Take profit : market_pnl >= take_profit_market_pnl (objectif atteint)
- Trailing stop : (market_pnl_max - market_pnl) >= trail_stop_market_pnl (protection gains)
- Timeout : pas de nouveau max PnL depuis max_pnl_timeout_minutes
- Perte du statut : market_pnl <= seuil_sortie (moyenne - stop_echappee_threshold × écart-type)

==== LIMITATIONS ET CONTRÔLES ====
- Fenêtre horaire : trades uniquement entre trade_start_hour et trade_cutoff_hour
- Max trades par jour : max_trades_per_day
- Intervalle entre trades : trade_interval_minutes
- Valeur fixe par trade : trade_value_eur (ex: 100€)
- Pas de double position sur le même ticker

==== DONNÉES UTILISÉES ====
Entrées : 
- table : SortedPnlTable contenant les données de marché (prix, PnL, etc.)
- timestamp : horodatage courant (timestamp Unix)

Sorties : 
- Ouverture/fermeture de positions dans self.portfolio (classe Portfolio)
- Logs d'ouverture/fermeture de trades

==== ATTRIBUTS PRINCIPAUX ====
- portfolio : Portfolio - Gère les positions et le cash
- traded_tickers : set - Tickers déjà tradés (pour éviter les doublons)
- escape_start_times : dict - Timestamp du début d'échappée par ticker
- top_n_start_times : dict - Timestamp d'entrée dans le top N par ticker
- trades_today : dict - Compteur de trades par jour (format: 'YYYY-MM-DD': count)
- last_trade_time : timestamp du dernier trade ouvert

==== PARAMÈTRES DE LA STRATÉGIE ====
- take_profit_market_pnl : Objectif de gain pour fermer (ex: 50€)
- trail_stop_market_pnl : Protection des gains (ex: 20€)
- min_market_pnl : PnL minimum requis pour ouvrir (ex: 15€)
- start_echappee_threshold : Multiplicateur d'écart-type pour entrer (ex: 0.78)
- stop_echappee_threshold : Multiplicateur d'écart-type pour sortir (ex: 0.0)
- top_n_threshold : Position max dans le classement (ex: top 5)
- min_escape_time : Durée minimale d'échappée en secondes (ex: 300s = 5min)
- trade_interval_minutes : Intervalle entre trades périodiques (ex: 30min)
- max_pnl_timeout_minutes : Timeout si pas de nouveau max (ex: 60min)
- max_trades_per_day : Limite quotidienne de trades (ex: 3)
- trade_cutoff_hour : Heure de fin de trading (ex: "14:00")
- trade_start_hour : Heure de début de trading (ex: "09:30")
"""

def fmt(ts):
    return (datetime.fromtimestamp(ts) + timedelta(hours=-6)).strftime("%Y-%m-%d %H:%M:%S")

class AlgoEchappee:
    def __init__(self, take_profit_market_pnl=50.0, min_escape_time=300,
                 trail_stop_market_pnl=20.0, stop_echappee_threshold=0.0,
                 start_echappee_threshold=0.78, min_market_pnl=15.0,
                 top_n_threshold=5, trade_interval_minutes=30, trade_value_eur=100.0,
                 max_pnl_timeout_minutes=60.0, max_trades_per_day=3,
                 trade_cutoff_hour="14:00", trade_start_hour="09:30",
                 max_trade_duration_minutes=60, verbose=True):
        self.portfolio = Portfolio()
        self.traded_tickers = set()
        self.take_profit_market_pnl = take_profit_market_pnl
        self.min_escape_time = min_escape_time
        self.trail_stop_market_pnl = trail_stop_market_pnl
        self.stop_echappee_threshold = stop_echappee_threshold
        self.start_echappee_threshold = start_echappee_threshold
        self.min_market_pnl = min_market_pnl
        self.top_n_threshold = top_n_threshold
        self.trade_interval_minutes = trade_interval_minutes
        self.trade_value_eur = trade_value_eur
        self.max_pnl_timeout_minutes = max_pnl_timeout_minutes
        self.max_trades_per_day = max_trades_per_day
        self.trade_cutoff_hour = trade_cutoff_hour
        self.trade_start_hour = trade_start_hour
        self.max_trade_duration_minutes = max_trade_duration_minutes
        self.verbose = verbose
        self.escape_start_times = {}
        self.top_n_start_times = {}
        self.last_trade_time = None
        self.trades_today = {}  # Suivi des trades par jour (format: 'YYYY-MM-DD': count)

    def _get_date(self, timestamp):
        """Retourne la date au format 'YYYY-MM-DD' à partir d'un timestamp."""
        return (datetime.fromtimestamp(timestamp) + timedelta(hours=-6)).strftime("%Y-%m-%d")

    def _get_hour(self, timestamp):
        """Retourne l'heure (en heures décimales) à partir d'un timestamp."""
        dt = datetime.fromtimestamp(timestamp) + timedelta(hours=-6)
        return dt.hour + dt.minute / 60.0

    def _parse_time(self, time_str):
        """Convertit une chaîne HH:MM en heures décimales."""
        hours, minutes = map(int, time_str.split(':'))
        return hours + minutes / 60.0

    def _can_open_trade(self, timestamp):
        """Vérifie si un nouveau trade peut être ouvert (limite par jour et fenêtre horaire)."""
        current_date = self._get_date(timestamp)
        current_hour = self._get_hour(timestamp)
        cutoff_hour = self._parse_time(self.trade_cutoff_hour)
        start_hour = self._parse_time(self.trade_start_hour)

        # Vérifier la fenêtre horaire
        if not (start_hour <= current_hour < cutoff_hour):
            # print(f"Trade blocked at {fmt(timestamp)}: Current hour ({current_hour:.2f}) outside trading window [{self.trade_start_hour}, {self.trade_cutoff_hour})")
            return False

        # Vérifier le nombre maximum de trades par jour
        trades_count = self.trades_today.get(current_date, 0)
        if trades_count >= self.max_trades_per_day:
            # print(f"Trade blocked at {fmt(timestamp)}: Max trades per day ({self.max_trades_per_day}) reached for {current_date}")
            return False

        return True

    def calculate_echappees(self, table, current_timestamp):
        """Calcule les tickers en échappée basés sur les market_pnl des 15 premiers tickers."""
        top_15 = table.get_top_n(15)
        tickers_data = [
            {
                'Ticker': ticker,
                'market_pnl': entry.get_pnl(),
                'market_pnl_max': entry.global_max_pnl
            }
            for ticker, entry in top_15
        ]

        if not tickers_data:
            return []

        pnls = np.array([ticker_data['market_pnl'] for ticker_data in tickers_data])
        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls) if len(pnls) > 2 else 0

        if std_pnl < 5:
            return []

        seuil_echappee = mean_pnl + self.start_echappee_threshold * std_pnl

        echappees = []
        for i, ticker_data in enumerate(tickers_data):
            ticker = ticker_data['Ticker']
            market_pnl = ticker_data['market_pnl']
            market_pnl_max = ticker_data['market_pnl_max']

            # Check if ticker is in top N
            is_in_top_n = i < self.top_n_threshold
            if is_in_top_n:
                if ticker not in self.top_n_start_times:
                    self.top_n_start_times[ticker] = current_timestamp
            else:
                if ticker in self.top_n_start_times:
                    del self.top_n_start_times[ticker]

            if (market_pnl > seuil_echappee):
                if ticker not in self.escape_start_times:
                    self.escape_start_times[ticker] = current_timestamp
                elif (current_timestamp - self.escape_start_times[ticker] >= self.min_escape_time and
                      ticker in self.top_n_start_times and
                      current_timestamp - self.top_n_start_times[ticker] >= self.min_escape_time):
                    echappees.append(ticker)
            else:
                if ticker in self.escape_start_times:
                    del self.escape_start_times[ticker]

        return echappees

    def main(self, table, timestamp):
        """Exécute la stratégie d'échappée."""
        # Iterate over tickers with open positions using get_open_tickers
        for ticker in self.portfolio.get_open_tickers():
            last_price = table.get_last_price(ticker)
            if last_price is None:
                continue

            market_pnl = table.ticker_map[ticker].get_pnl() if ticker in table.ticker_map else 0.0
            market_pnl_max = table.ticker_map[ticker].global_max_pnl if ticker in table.ticker_map else 0.0
            global_max_time = table.ticker_map[ticker].global_max_time if ticker in table.ticker_map else timestamp

            # Aggregate unrealized PNL for the ticker
            unrealized_pnl = sum(
                trade["unrealized_pnl"] for trade in self.portfolio.trades
                if trade["ticker"] == ticker and trade["status"] == "open"
            )
            unrealized_pnl_max = sum(
                trade["unrealized_pnl_max"] for trade in self.portfolio.trades
                if trade["ticker"] == ticker and trade["status"] == "open"
            )

            # Check take-profit conditions
            if market_pnl >= self.take_profit_market_pnl:
                self.portfolio.close_position(ticker, last_price, timestamp, table)
                continue

            # Trailing stop for market PNL
            if market_pnl_max > 0 and (market_pnl_max - market_pnl) >= self.trail_stop_market_pnl:
                self.portfolio.close_position(ticker, last_price, timestamp, table)
                continue

            # Vérifier si le global_max_pnl n'a pas été dépassé depuis max_pnl_timeout_minutes
            max_pnl_timeout_seconds = self.max_pnl_timeout_minutes * 60
            if (timestamp - global_max_time) >= max_pnl_timeout_seconds:
                self.portfolio.close_position(ticker, last_price, timestamp, table)
                print(f"Closed position on {ticker} at {fmt(timestamp)} due to max PNL timeout (no new max PNL for {self.max_pnl_timeout_minutes} minutes)")
                continue

            # Vérifier si la durée max du trade est dépassée
            max_duration_seconds = self.max_trade_duration_minutes * 60
            for trade in self.portfolio.trades:
                if trade["ticker"] == ticker and trade["status"] == "open":
                    if (timestamp - trade["entry_time"]) >= max_duration_seconds:
                        self.portfolio.close_position(ticker, last_price, timestamp, table)
                        if self.verbose:
                            print(f"Closed position on {ticker} at {fmt(timestamp)} due to max duration ({self.max_trade_duration_minutes} min)")
                        break

        # Close Trade: Calculate echappees and check stop echappee
        top_15 = table.get_top_n(15)
        tickers_data = {ticker: entry.get_pnl() for ticker, entry in top_15}
        mean_pnl = np.mean(list(tickers_data.values())) if tickers_data else 0.0
        std_pnl = np.std(list(tickers_data.values())) if len(tickers_data) > 2 else 0.0
        seuil_echappee = mean_pnl - std_pnl * self.stop_echappee_threshold

        for ticker in self.portfolio.get_open_tickers():
            market_pnl = table.ticker_map[ticker].get_pnl() if ticker in table.ticker_map else 0.0
            if market_pnl <= seuil_echappee:
                last_price = table.get_last_price(ticker)
                if last_price is not None:
                    self.portfolio.close_position(ticker, last_price, timestamp, table)

        # Open new trades based on echappees
        if self._can_open_trade(timestamp):
            echappees = self.calculate_echappees(table, timestamp)
            for ticker in echappees:
                if ticker not in self.traded_tickers and not self.portfolio.is_ticker_in_portfolio(ticker):
                    last_price = table.get_last_price(ticker)
                    if last_price is not None and last_price > 0:
                        market_pnl = table.ticker_map[ticker].get_pnl() if ticker in table.ticker_map else 0.0
                        quantity = int(self.trade_value_eur / last_price)
                        if market_pnl > self.min_market_pnl and quantity > 0:
                            success = self.portfolio.open_trade(ticker, quantity, table, timestamp)
                            if success:
                                self.traded_tickers.add(ticker)
                                self.last_trade_time = timestamp
                                current_date = self._get_date(timestamp)
                                self.trades_today[current_date] = self.trades_today.get(current_date, 0) + 1
                                if self.verbose:
                                    print(f"Opened echappee trade on {ticker} for {quantity} shares at {fmt(timestamp)} (Trades today: {self.trades_today[current_date]}/{self.max_trades_per_day})")

        # Periodic trade opening based on trade_interval_minutes
        interval_seconds = self.trade_interval_minutes * 60
        if self.last_trade_time is None or (timestamp - self.last_trade_time) >= interval_seconds:
            if self._can_open_trade(timestamp):
                best_ticker = self.portfolio.get_open_trade_best_pnl(table)
                if best_ticker:
                    last_price = table.get_last_price(best_ticker)
                    if last_price is not None and last_price > 0:
                        quantity = int(self.trade_value_eur / last_price)
                        if quantity > 0:
                            success = self.portfolio.open_trade(best_ticker, quantity, table, timestamp)
                            if success:
                                self.traded_tickers.add(best_ticker)
                                self.last_trade_time = timestamp
                                current_date = self._get_date(timestamp)
                                self.trades_today[current_date] = self.trades_today.get(current_date, 0) + 1
                                print(f"Opened periodic trade on {best_ticker} for {quantity} shares at {fmt(timestamp)} (interval: {self.trade_interval_minutes} min, Trades today: {self.trades_today[current_date]}/{self.max_trades_per_day})")

    def close_all(self, table, timestamp):
        """Ferme toutes les positions."""
        self.portfolio.close_all(table, timestamp)