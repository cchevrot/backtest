import json
import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

PORT = 7777  # Port du serveur web

def load_memoire_data(filename="memoire_config.json"):
    """Charge les données depuis memoire_config.json."""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        # Convertir les clés en dictionnaires de paramètres et extraire les métriques
        results = []
        for param_key, metrics in data.items():
            params = json.loads(param_key)
            result = {
                'min_escape_time': params.get('min_escape_time', 0.0),
                'min_market_pnl': params.get('min_market_pnl', 0.0),
                'start_echappee_threshold': params.get('start_echappee_threshold', 0.0),
                'stop_echappee_threshold': params.get('stop_echappee_threshold', 0.0),
                'take_profit_market_pnl': params.get('take_profit_market_pnl', 0.0),
                'top_n_threshold': params.get('top_n_threshold', 0.0),
                'trail_stop_market_pnl': params.get('trail_stop_market_pnl', 0.0),
                'trade_interval_minutes': params.get('trade_interval_minutes', 0.0),
                'trade_value_eur': params.get('trade_value_eur', 0.0),
                'max_pnl_timeout_minutes': params.get('max_pnl_timeout_minutes', 60.0),
                'max_trades_per_day': params.get('max_trades_per_day', 3),
                'trade_cutoff_hour': params.get('trade_cutoff_hour', "14:00"),
                'trade_start_hour': params.get('trade_start_hour', "09:30"),
                'total_pnl': metrics.get('total_pnl', 0.0) if isinstance(metrics, dict) else metrics,
                'total_invested_capital': metrics.get('total_invested_capital', 0.0) if isinstance(metrics, dict) else 0.0,
                'total_roi': metrics.get('total_roi', 0.0) if isinstance(metrics, dict) else 0.0,
                'daily_pnl_std': metrics.get('daily_pnl_std', 0.0) if isinstance(metrics, dict) else 0.0,
                'positive_or_zero_pnl_days': metrics.get('positive_or_zero_pnl_days', 0) if isinstance(metrics, dict) else 0,
                'negative_pnl_days': metrics.get('negative_pnl_days', 0) if isinstance(metrics, dict) else 0
            }
            results.append(result)
        return results
    except Exception as e:
        print(f"Erreur lors de la lecture de {filename}: {e}")
        return []

def generate_html(data):
    """Génère le contenu HTML avec quatre onglets et tableaux Tabulator."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simulation Results</title>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <link href="https://unpkg.com/tabulator-tables@5.5.0/dist/css/tabulator.min.css" rel="stylesheet">
    <script src="https://unpkg.com/tabulator-tables@5.5.0/dist/js/tabulator.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: Arial, sans-serif; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .tabulator { margin-top: 1rem; }
    </style>
</head>
<body class="bg-gray-100">
    <div class="container mx-auto p-4">
        <h1 class="text-2xl font-bold mb-4 text-center">Simulation Results</h1>
        <ul class="flex border-b border-gray-200">
            <li class="mr-1">
                <a class="tab-link inline-block py-2 px-4 font-semibold rounded-t-lg bg-white border border-b-0" href="#tab-roi">Sorted by Total ROI</a>
            </li>
            <li class="mr-1">
                <a class="tab-link inline-block py-2 px-4 font-semibold rounded-t-lg bg-gray-200 border border-b-0" href="#tab-pnl">Sorted by Total PnL</a>
            </li>
            <li class="mr-1">
                <a class="tab-link inline-block py-2 px-4 font-semibold rounded-t-lg bg-gray-200 border border-b-0" href="#tab-std">Sorted by Daily PnL Std</a>
            </li>
            <li class="mr-1">
                <a class="tab-link inline-block py-2 px-4 font-semibold rounded-t-lg bg-gray-200 border border-b-0" href="#tab-positive-days">Sorted by Positive/Negative Days</a>
            </li>
        </ul>
        <div id="tab-roi" class="tab-content active">
            <div id="table-roi" class="tabulator"></div>
        </div>
        <div id="tab-pnl" class="tab-content">
            <div id="table-pnl" class="tabulator"></div>
        </div>
        <div id="tab-std" class="tab-content">
            <div id="table-std" class="tabulator"></div>
        </div>
        <div id="tab-positive-days" class="tab-content">
            <div id="table-positive-days" class="tabulator"></div>
        </div>
    </div>

    <script>
        $(document).ready(function() {
            $('.tab-link').click(function(e) {
                e.preventDefault();
                $('.tab-content').removeClass('active');
                $('.tab-link').removeClass('bg-white').addClass('bg-gray-200');
                $(this).removeClass('bg-gray-200').addClass('bg-white');
                $($(this).attr('href')).addClass('active');
            });

            // Données des simulations
            const data = """ + json.dumps(data) + """;

            // Configuration commune pour les tableaux
            const tableConfig = {
                layout: "fitColumns",
                pagination: "local",
                paginationSize: 10,
                columns: [
                    { title: "Min Escape Time (s)", field: "min_escape_time", sorter: "number", formatter: "number", formatterParams: { precision: 0 } },
                    { title: "Min Market PnL", field: "min_market_pnl", sorter: "number", formatter: "number", formatterParams: { precision: 2 } },
                    { title: "Start Echappee", field: "start_echappee_threshold", sorter: "number", formatter: "number", formatterParams: { precision: 2 } },
                    { title: "Stop Echappee", field: "stop_echappee_threshold", sorter: "number", formatter: "number", formatterParams: { precision: 2 } },
                    { title: "Take Profit", field: "take_profit_market_pnl", sorter: "number", formatter: "number", formatterParams: { precision: 2 } },
                    { title: "Top N Threshold", field: "top_n_threshold", sorter: "number", formatter: "number", formatterParams: { precision: 2 } },
                    { title: "Trail Stop", field: "trail_stop_market_pnl", sorter: "number", formatter: "number", formatterParams: { precision: 2 } },
                    { title: "Trade Interval (min)", field: "trade_interval_minutes", sorter: "number", formatter: "number", formatterParams: { precision: 0 } },
                    { title: "Trade Value (€)", field: "trade_value_eur", sorter: "number", formatter: "money", formatterParams: { decimal: ".", thousand: ",", symbol: "€", precision: 2 } },
                    { title: "Max PnL Timeout (min)", field: "max_pnl_timeout_minutes", sorter: "number", formatter: "number", formatterParams: { precision: 2 } },
                    { title: "Max Trades/Day", field: "max_trades_per_day", sorter: "number", formatter: "number", formatterParams: { precision: 0 } },
                    { title: "Trade Cutoff Hour", field: "trade_cutoff_hour", sorter: "string" },
                    { title: "Trade Start Hour", field: "trade_start_hour", sorter: "string" },
                    { title: "Total PnL ($)", field: "total_pnl", sorter: "number", formatter: "money", formatterParams: { decimal: ".", thousand: ",", symbol: "$", precision: 2 } },
                    { title: "Invested Capital ($)", field: "total_invested_capital", sorter: "number", formatter: "money", formatterParams: { decimal: ".", thousand: ",", symbol: "$", precision: 2 } },
                    { title: "Total ROI (%)", field: "total_roi", sorter: "number", formatter: "number", formatterParams: { precision: 2 } },
                    { title: "Daily PnL Std ($)", field: "daily_pnl_std", sorter: "number", formatter: "money", formatterParams: { decimal: ".", thousand: ",", symbol: "$", precision: 2 } },
                    { title: "Positive/Zero Days", field: "positive_or_zero_pnl_days", sorter: "number" },
                    { title: "Negative Days", field: "negative_pnl_days", sorter: "number" }
                ]
            };

            // Tableau trié par total_roi
            new Tabulator("#table-roi", {
                ...tableConfig,
                data: data,
                initialSort: [
                    { column: "total_roi", dir: "desc" },
                    { column: "total_pnl", dir: "desc" }
                ]
            });

            // Tableau trié par total_pnl
            new Tabulator("#table-pnl", {
                ...tableConfig,
                data: data,
                initialSort: [
                    { column: "total_pnl", dir: "desc" },
                    { column: "total_roi", dir: "desc" }
                ]
            });

            // Tableau trié par daily_pnl_std
            new Tabulator("#table-std", {
                ...tableConfig,
                data: data,
                initialSort: [
                    { column: "daily_pnl_std", dir: "desc" },
                    { column: "total_roi", dir: "desc" }
                ]
            });

            // Tableau trié par positive_or_zero_pnl_days
            new Tabulator("#table-positive-days", {
                ...tableConfig,
                data: data,
                initialSort: [
                    { column: "positive_or_zero_pnl_days", dir: "desc" },
                    { column: "total_roi", dir: "desc" }
                ]
            });
        });
    </script>
</body>
</html>
"""
    return html_content

def main():
    # Charger les données
    data = load_memoire_data()
    if not data:
        print("Aucune donnée à afficher.")
        return

    # Générer le HTML
    html_content = generate_html(data)

    # Écrire le fichier HTML
    output_path = Path("index.html")
    output_path.write_text(html_content, encoding="utf-8")
    print(f"Page web générée : {output_path.resolve()}")

    # Lancer le serveur web
    os.chdir(output_path.parent)  # Se placer dans le répertoire du fichier HTML
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serveur démarré sur http://localhost:{PORT}")
        webbrowser.open(f"http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nArrêt du serveur.")
            httpd.server_close()

if __name__ == "__main__":
    main()