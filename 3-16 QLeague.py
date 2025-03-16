# region imports
from AlgorithmImports import *
import time
# endregion

class MultiAssetMomentum(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2024, 1, 1)  # Set Start Date
        self.SetEndDate(2025, 3, 26)
        self.SetCash(100000)  # Set Strategy Cash
        self.SetWarmUp(30, Resolution.Daily)  # 30 days of historical data
        # Set sector allocation at initialization (25% each sector)
        # self.sector_allocation = 0.25  # 25% for each sector
        # self.asset_allocation = 0.05  # 5% of the sector allocation per asset (i.e., 1.25% of total portfolio per asset)

        self.rsi_buy_top = self.GetParameter("rsi_buy_top", 80)  # Default 70
        self.rsi_buy_bot = self.GetParameter("rsi_buy_bot", 50)  # Default 30

        self.rsi_sell_top = self.GetParameter("rsi_sell_top", 90)  # Default 80
        self.rsi_sell_bot = self.GetParameter("rsi_sell_bot", 40)  # Default 40
        
        self.ema_short_period = self.GetParameter("ema_short_period", 12)  # Default 12
        self.ema_long_period = self.GetParameter("ema_long_period", 26)  # Default 26

        self.atr_multiplier = 2  # ATR Stop Loss Multiplier
        self.max_holding_days = 10  # Time-based Stop Loss (Exit after 10 days)


        # Configure brokerage and security initializer
        # Universe settings
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.Asynchronous = True

        # Define fixed universes
        # BTCUSD  - Bitcoin, ETHUSD  - Ethereum , SOLUSD  - Solana, XRPUSD  - XRP (Ripple), ADAUSD  - Cardano , DOGEUSD - Dogecoin  
        self.crypto_symbols = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ADAUSD", "DOGEUSD"]
    #    apple, microsoft, nvidia, google, amazon, meta, tesla, boardcome, taiwan semiconductor, ali baba
        self.tech_symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "TSM", "BABA"]
        # XOM  - ExxonMobil, CVX  - Chevron Corporation, BP   - BP Plc  , TOT  - TotalEnergies, COP  - ConocoPhillips , SHEL - Shell Plc
        self.energy_symbols = ["XOM", "CVX", "BP", "TOT", "COP", "SHEL"]
        # EURUSD - Euro / US Dollar, USDJPY - US Dollar / Japanese Yen, GBPUSD - British Pound / US Dollar, AUDUSD - Australian Dollar / US Dollar  
        # USDCAD - US Dollar / Canadian Dollar, EURJPY - Euro / Japanese Yen, GBPJPY - British Pound / Japanese Yen, EURGBP - Euro / British Pound  
        self.fx_symbols = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "EURJPY", "GBPJPY", "EURGBP"]

        # Add securities and initialize indicators
        self.rsi = {}
        self.ema_short = {}
        self.ema_long = {}
        self.macd = {}
        self.atr = {}
        self.entry_prices = {}
        self.entry_dates = {}  # Track entry time for time-based stop loss
        self.stop_losses = {}  # Track ATR-based stop loss levels
        self.trailing_stop_losses = {}  # Track trailing stop losses

        for symbol in self.crypto_symbols:
            self.AddCrypto(symbol, Resolution.Daily)
        for symbol in self.tech_symbols + self.energy_symbols:
            self.AddEquity(symbol, Resolution.Daily)
        for symbol in self.fx_symbols:
            self.AddForex(symbol, Resolution.Daily)

        for symbol in self.crypto_symbols + self.tech_symbols + self.energy_symbols + self.fx_symbols:
            self.rsi[symbol] = self.RSI(symbol, 14, MovingAverageType.Simple, Resolution.Daily)
            self.ema_short[symbol] = self.EMA(symbol, 12, Resolution.Daily)
            self.ema_long[symbol] = self.EMA(symbol, 26, Resolution.Daily)
            self.macd[symbol] = self.MACD(symbol, 12, 26, 9, MovingAverageType.Exponential, Resolution.Daily)
            self.atr[symbol] = self.ATR(symbol, 14, MovingAverageType.Simple, Resolution.Daily)

    def OnData(self, data):
        # Exit positions if conditions are met
        if self.IsWarmingUp:
            return

        current_time = self.Time
        
        for symbol in list(self.entry_prices.keys()):
            if symbol not in data.Bars:
                #self.Debug(f"{symbol} No data available at this time.") ###
                continue  # Skip if no data

            current_price = data.Bars[symbol].Close
            atr_value = self.atr[symbol].Current.Value
            
            # Time-based stop-loss
            if (current_time - self.entry_dates[symbol]).days >= self.max_holding_days:
                self.Debug(f"Time-based stop-loss triggered for {symbol}")
                self.Liquidate(symbol)
                self.RemovePositionTracking(symbol)
                continue
            
            # ATR-based stop-loss
            if current_price < self.stop_losses[symbol]:
                self.Debug(f"ATR stop-loss triggered for {symbol}")
                self.Liquidate(symbol)
                self.RemovePositionTracking(symbol)
                continue
            
            # Update trailing stop loss
            if current_price > self.entry_prices[symbol]:  # Adjust only when price increases
                self.trailing_stop_losses[symbol] = max(self.trailing_stop_losses[symbol], current_price - 1.5 * atr_value)
            
            # Check trailing stop loss
            if current_price < self.trailing_stop_losses[symbol]:
                self.Debug(f"Trailing stop-loss triggered for {symbol}")
                self.Liquidate(symbol)
                self.RemovePositionTracking(symbol)
        
        for symbol in self.rsi.keys():
            if symbol not in data.Bars:
                continue

            current_price = data.Bars[symbol].Close
            rsi_value = self.rsi[symbol].Current.Value
            ema_short_value = self.ema_short[symbol].Current.Value
            ema_long_value = self.ema_long[symbol].Current.Value
            macd_line = self.macd[symbol].Current.Value
            signal_line = self.macd[symbol].Signal.Current.Value
            histogram = macd_line - signal_line
            atr_value = self.atr[symbol].Current.Value

            if (
                self.entry_prices.get(symbol) is None and  # Not already holding
                ema_short_value > ema_long_value and
                self.rsi_buy_bot <= rsi_value <= self.rsi_buy_top and 
                histogram > 0
            ):
                self.Debug(f"Buying {symbol}")
                self.SetHoldings(symbol, 0.05)
                self.entry_prices[symbol] = current_price
                self.entry_dates[symbol] = current_time  # Track entry date
                
                # Set ATR-based stop loss
                self.stop_losses[symbol] = current_price - self.atr_multiplier * atr_value
                # Initialize trailing stop loss
                self.trailing_stop_losses[symbol] = current_price - 1.5 * atr_value
    
    def RemovePositionTracking(self, symbol):
        """Removes tracking data for a symbol when a position is closed."""
        del self.entry_prices[symbol]
        del self.entry_dates[symbol]
        del self.stop_losses[symbol]
        del self.trailing_stop_losses[symbol]