"""
Portfolio — Gestionnaire de portefeuille pour le backtesting de stratégies de trading.

==== RÔLE DE LA CLASSE ====
La classe Portfolio gère toutes les positions de trading (ouvertes et fermées), 
le cash disponible, et calcule les profits/pertes (PnL) en temps réel.

Elle sert d'interface entre la stratégie (AlgoEchappee) et les données de marché (SortedPnlTable).

==== RESPONSABILITÉS PRINCIPALES ====
1. Suivre en temps réel les prix des actifs (via refresh_prices) pour calculer les 
   profits/pertes non réalisés
2. Gérer l'ouverture et la fermeture des trades en mettant à jour le cash et les 
   statistiques de PnL
3. Maintenir un historique complet pour analyser la performance et prendre des décisions 
   (fermer la meilleure position, ouvrir de nouvelles, etc.)

==== ATTRIBUTS PRINCIPAUX ====
- trades : list[dict] - Liste de tous les trades (ouverts et fermés)
  Chaque trade contient :
  * ticker : nom de l'action (ex: "AAPL")
  * quantity : nombre d'actions achetées
  * entry_price : prix d'achat
  * entry_time : timestamp d'ouverture
  * last_price : dernier prix connu (mis à jour par refresh_prices)
  * unrealized_pnl : PnL non réalisé actuel (pour positions ouvertes)
  * unrealized_pnl_max : PnL non réalisé maximum atteint
  * status : "open" ou "closed"
  * invested_amount : montant total investi (quantity × entry_price)
  * exit_price : prix de vente (si fermé)
  * exit_time : timestamp de fermeture (si fermé)
  * realized_pnl : PnL réalisé (si fermé)

- cash : float - Solde en cash disponible (commence à 1 000 000€)
- total_pnl : float - PnL total réalisé (somme de tous les trades fermés)

==== MÉTHODES PRINCIPALES ====
- refresh_prices(table) : Met à jour les prix et PnL de toutes les positions ouvertes
  Appelée à chaque nouveau prix reçu par la stratégie
  
- open_trade(ticker, quantity, table, timestamp) : Ouvre une nouvelle position
  Vérifie que le cash est suffisant avant d'acheter
  Retourne True si succès, False sinon
  
- close_position(ticker, last_price, timestamp, table) : Ferme tous les trades d'un ticker
  Calcule le PnL réalisé et recrédite le cash
  
- close_all(table, timestamp) : Ferme toutes les positions ouvertes
  Utilisée en fin de journée de trading
  
- is_ticker_in_portfolio(ticker) : Vérifie si un ticker a déjà une position ouverte
  Évite d'ouvrir deux fois la même position
  
- get_open_tickers() : Retourne la liste des tickers avec positions ouvertes
  
- get_open_trade_best_pnl(table) : Retourne le ticker ouvert avec le meilleur classement
  Utilisé pour les trades périodiques (prendre le meilleur du moment)
  
- display_portfolio() : Affiche un résumé du portefeuille (positions, PnL, cash)

==== CLASSES UTILISÉES ====
- SortedPnlTable : Fournit les prix des actifs via get_last_price(ticker)
  Contient les données de marché nécessaires pour calculer les PnL

==== FLUX D'UTILISATION ====
1. AlgoEchappee appelle refresh_prices() à chaque nouveau prix
2. AlgoEchappee décide d'ouvrir/fermer selon sa stratégie
3. Portfolio met à jour cash, trades, et calcule les PnL
4. Les statistiques sont utilisées pour optimiser les paramètres

==== EXEMPLE DE CYCLE DE VIE D'UN TRADE ====
1. open_trade("AAPL", 10, table, t0) → Achète 10 actions, cash diminue
2. refresh_prices(table) → Met à jour unrealized_pnl à chaque tick
3. close_position("AAPL", last_price, t1, table) → Vend, cash augmente, PnL réalisé
"""

from datetime import datetime, timedelta

from sorted_pnl_table import SortedPnlTable

def fmt(ts):
    return (datetime.fromtimestamp(ts) + timedelta(hours=-6)).strftime("%Y-%m-%d %H:%M:%S")

class Portfolio:
    def __init__(self):
        self.trades = []  # Liste de tous les trades (ouverts et fermés)
        self.cash = 1000000.0  # Solde initial en dollars
        self.total_pnl = 0.0

    def refresh_prices(self, table):
        """Mise à jour des derniers prix et PnL pour tous les trades ouverts"""
        for trade in self.trades:
            if trade["status"] == "open":
                last_price = table.get_last_price(trade["ticker"])
                if last_price is None:
                    continue
                trade["last_price"] = last_price
                trade["unrealized_pnl"] = (
                    (last_price - trade["entry_price"]) * trade["quantity"]
                )
                trade["unrealized_pnl_max"] = max(
                    trade["unrealized_pnl_max"], trade["unrealized_pnl"]
                )

    def open_trade(self, ticker, quantity, table, timestamp):
        """Ouvre un nouveau trade"""
        last_price = table.get_last_price(ticker)
        if last_price is None:
            print(f"Erreur: Prix indisponible pour {ticker}")
            return False

        cost = last_price * quantity
        if cost > self.cash:
            print(f"Erreur: Fonds insuffisants pour acheter {quantity} {ticker} à {last_price}")
            return False

        trade = {
            "ticker": ticker,
            "quantity": quantity,
            "entry_price": last_price,
            "entry_time": timestamp,
            "last_price": last_price,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_max": 0.0,
            "status": "open",
            "invested_amount": cost
        }
        self.trades.append(trade)
        self.cash -= cost
        return True

    def close_position(self, ticker, last_price, timestamp, table):
        """Ferme tous les trades associés à un ticker spécifique"""
        closed_any = False
        for trade in self.trades:
            if trade["ticker"] == ticker and trade["status"] == "open":
                realized_pnl = (last_price - trade["entry_price"]) * trade["quantity"]
                self.total_pnl += realized_pnl
                self.cash += last_price * trade["quantity"]
                
                market_pnl_max = table.ticker_map[ticker].global_max_pnl if ticker in table.ticker_map else 0.0
                
                trade.update({
                    "exit_price": last_price,
                    "exit_time": timestamp,
                    "realized_pnl": realized_pnl,
                    "market_pnl_max": market_pnl_max,
                    "status": "closed"
                })
                closed_any = True
        return closed_any

    def close_all(self, table, timestamp):
        """Ferme tous les trades ouverts"""
        for trade in self.trades:
            if trade["status"] == "open":
                last_price = table.get_last_price(trade["ticker"])
                if last_price is None:
                    print(f"Erreur: Prix indisponible pour fermer {trade['ticker']}")
                    continue
                self.close_position(trade["ticker"], last_price, timestamp, table)

    def is_ticker_in_portfolio(self, ticker):
        """Vérifie si un ticker est présent dans les trades ouverts"""
        return any(trade["ticker"] == ticker and trade["status"] == "open" for trade in self.trades)

    def get_open_tickers(self):
        """Retourne une liste de tous les tickers avec des positions ouvertes"""
        return sorted(list(set(trade["ticker"] for trade in self.trades if trade["status"] == "open")))

    def get_open_trade_best_pnl(self, table):
        """Retourne le ticker avec le trade ouvert ayant la meilleure position dans SortedPnlTable."""
        table.resort()  # Assurer que sorted_tickers est à jour
        open_tickers = set(self.get_open_tickers())  # Ensemble des tickers avec trades ouverts

        # Parcourir sorted_tickers pour trouver le premier ticker avec un trade ouvert
        for ticker, _ in table.sorted_tickers:
            if ticker in open_tickers:
                return ticker

        return None  # Aucun trade ouvert trouvé dans sorted_tickers

    def display_portfolio(self):
        """Affiche l'état actuel du portefeuille et un résumé des positions"""
        print("Portefeuille - Résumé")
        print("-" * 80)
        
        print("Positions Ouvertes:")
        print("-" * 80)
        open_trades_by_ticker = {}
        for trade in self.trades:
            if trade["status"] == "open":
                ticker = trade["ticker"]
                if ticker not in open_trades_by_ticker:
                    open_trades_by_ticker[ticker] = []
                open_trades_by_ticker[ticker].append(trade)
        
        if not open_trades_by_ticker:
            print("Aucune position ouverte.")
        else:
            print(f"{'Ticker':<10} {'Quantité':<10} {'Prix Entrée':<15} {'Dernier Prix':<12} {'PnL Non Réalisé':<15} {'PnL Max Non Réalisé':<15}")
            print("-" * 80)
            for ticker, trades in open_trades_by_ticker.items():
                total_quantity = sum(t["quantity"] for t in trades)
                if total_quantity == 0:
                    continue
                avg_entry_price = sum(t["quantity"] * t["entry_price"] for t in trades) / total_quantity
                last_price = trades[-1]["last_price"]
                unrealized_pnl = sum(t["unrealized_pnl"] for t in trades)
                unrealized_pnl_max = sum(t["unrealized_pnl_max"] for t in trades)
                print(f"{ticker:<10} {total_quantity:<10} {avg_entry_price:<15.2f} {last_price:<12.2f} {unrealized_pnl:<15.2f} {unrealized_pnl_max:<15.2f}")
        
        print("\nHistorique des Positions Fermées:")
        print("-" * 80)
        closed_trades = [t for t in self.trades if t["status"] == "closed"]
        if not closed_trades:
            print("Aucune position fermée.")
        else:
            print(f"{'Ticker':<10} {'Quantité':<10} {'Prix Entrée':<12} {'Prix Sortie':<12} {'PnL Réalisé':<12} {'Date Entrée':<20} {'Date Sortie':<20}")
            print("-" * 80)
            for pos in closed_trades:
                print(f"{pos['ticker']:<10} {pos['quantity']:<10} {pos['entry_price']:<12.2f} {pos['exit_price']:<12.2f} {pos['realized_pnl']:<12.2f} {fmt(pos['entry_time']):<20} {fmt(pos['exit_time']):<20}")
        
        print("-" * 80)
        print(f"Solde cash: ${self.cash:.2f}")
        print(f"PnL total réalisé: ${self.total_pnl:.2f}")
        invested_total = sum(t["invested_amount"] for t in self.trades if t["status"] == "closed")
        print(f"Total investi (positions fermées): ${invested_total:.2f}")
        print("-" * 80)

def main():
    """Test de la simulation de portefeuille"""
    portfolio = Portfolio()
    table = SortedPnlTable()
    
    # Temps initial
    current_time = datetime.now().timestamp()
    
    # Initialiser quelques tickers dans la table pour le test
    table.update_ticker("AAPL", 150.0, current_time)
    table.update_ticker("GOOGL", 2800.0, current_time)
    
    # Test 1: Ouvrir plusieurs trades sur AAPL
    print("Test 1: Ouverture de plusieurs trades sur AAPL")
    portfolio.open_trade("AAPL", 3, table, current_time)
    portfolio.open_trade("AAPL", 5, table, current_time + 3600)
    print(f"Tickers ouverts: {portfolio.get_open_tickers()}")
    portfolio.display_portfolio()
    
    # Test 2: Mettre à jour les prix
    print("\nTest 2: Mise à jour des prix")
    table.update_ticker("AAPL", 155.0, current_time + 7200)
    portfolio.refresh_prices(table)
    print(f"Tickers ouverts: {portfolio.get_open_tickers()}")
    portfolio.display_portfolio()
    
    # Test 3: Fermer tous les trades pour AAPL
    print("\nTest 3: Fermer tous les trades pour AAPL")
    portfolio.close_position("AAPL", 155.0, current_time + 7200, table)
    print(f"Tickers ouverts: {portfolio.get_open_tickers()}")
    portfolio.display_portfolio()
    
    # Test 4: Ouvrir un trade sur GOOGL
    print("\nTest 4: Ouverture d'un trade sur GOOGL")
    portfolio.open_trade("GOOGL", 2, table, current_time + 10800)
    print(f"Tickers ouverts: {portfolio.get_open_tickers()}")
    portfolio.display_portfolio()
    
    # Test 5: Fermer tous les trades
    print("\nTest 5: Fermer tous les trades")
    table.update_ticker("GOOGL", 2850.0, current_time + 14400)
    portfolio.close_all(table, current_time + 14400)
    print(f"Tickers ouverts: {portfolio.get_open_tickers()}")
    portfolio.display_portfolio()
    
    # Test 6: Tester get_open_trade_best_pnl
    print("\nTest 6: Tester le ticker avec le meilleur PnL dans SortedPnlTable")
    table.update_ticker("AAPL", 160.0, current_time + 18000)
    table.update_ticker("GOOGL", 2900.0, current_time + 18000)
    portfolio.open_trade("AAPL", 4, table, current_time + 18000)
    portfolio.open_trade("GOOGL", 1, table, current_time + 18000)
    table.update_ticker("AAPL", 165.0, current_time + 18100)  # market_pnl = (165-160)/160 * 100 = 3.125%
    table.update_ticker("GOOGL", 3000.0, current_time + 18100)  # market_pnl = (3000-2900)/2900 * 100 = 3.448%
    best_ticker = portfolio.get_open_trade_best_pnl(table)
    print(f"Ticker avec le meilleur PnL dans SortedPnlTable: {best_ticker}")

if __name__ == "__main__":
    main()
