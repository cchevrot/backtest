class SortedPnlTable:
    def __init__(self):
        self.ticker_map = {}
        self.sorted_tickers = []
        self.updates_since_last_sort = 0

    def update_ticker(self, ticker, price, timestamp):
        if ticker not in self.ticker_map:
            entry = self.TickerEntry(price, timestamp)
            self.ticker_map[ticker] = entry
        else:
            entry = self.ticker_map[ticker]
            entry.update(price, timestamp)
        self.updates_since_last_sort += 1

    def resort(self):
        self.sorted_tickers = sorted(
            self.ticker_map.items(),
            key=lambda item: item[1].get_pnl(),
            reverse=True
        )
        self.updates_since_last_sort = 0

    def has_been_resorted(self, threshold=1000):
        if self.updates_since_last_sort >= threshold:
            self.resort()
            return True
        return False

    def get_top_n(self, n=20):
        return self.sorted_tickers[:n]

    def get_last_price(self, ticker):
        if ticker in self.ticker_map:
            return self.ticker_map[ticker].last_price
        return None

    def reset(self):
        self.ticker_map = {}
        self.sorted_tickers = []
        self.updates_since_last_sort = 0

    class TickerEntry:
        def __init__(self, first_price, first_time):
            self.first_price = first_price
            self.last_price = first_price
            self.first_time = first_time
            self.last_time = first_time

            self.current_pnl = 0.0
            self.highest_pnl_so_far = 0.0
            self.highest_pnl_time = first_time
            self.highest_pnl_price = first_price

            self.max_drawdown = 0.0
            self.peak_pnl = 0.0
            self.peak_price = first_price
            self.peak_time = first_time

            self.trough_pnl = 0.0
            self.trough_price = first_price
            self.trough_time = first_time

            self.global_max_pnl = 0.0
            self.global_max_price = first_price
            self.global_max_time = first_time

        def update(self, price, timestamp):
            self.last_price = price
            self.last_time = timestamp
            self.current_pnl = (self.last_price - self.first_price) / self.first_price * 100

            if self.current_pnl > self.global_max_pnl:
                self.global_max_pnl = self.current_pnl
                self.global_max_price = self.last_price
                self.global_max_time = timestamp

            if self.current_pnl > self.highest_pnl_so_far:
                self.highest_pnl_so_far = self.current_pnl
                self.highest_pnl_price = self.last_price
                self.highest_pnl_time = timestamp

            drawdown = self.current_pnl - self.highest_pnl_so_far
            if drawdown < self.max_drawdown:
                self.max_drawdown = drawdown
                self.peak_pnl = self.highest_pnl_so_far
                self.peak_price = self.highest_pnl_price
                self.peak_time = self.highest_pnl_time
                self.trough_pnl = self.current_pnl
                self.trough_price = self.last_price
                self.trough_time = timestamp

        def get_pnl(self):
            return self.current_pnl