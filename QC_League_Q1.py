from AlgorithmImports import *
from scipy.optimize import brentq
import math
from scipy.stats import norm

class StraddleStrategy(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2024, 1, 1)
        self.SetEndDate(2025, 1, 1)
        self.SetCash(100000)

        equity = "TSLA"
        self.equity = self.AddEquity(equity, Resolution.Minute).Symbol
        
        # Add options for the underlying equity and set up the option universe filter
        self.option = self.AddOption(equity, Resolution.Minute)
        self.option.SetFilter(self.UniverseFilter)

        # Schedule the Evaluate method to run every day 30 minutes after market open
        self.Schedule.On(self.DateRules.EveryDay(self.equity), 
                         self.TimeRules.AfterMarketOpen(self.equity, 30), 
                         self.Evaluate)

    def UniverseFilter(self, universe):
        # Select strikes within +/- 2 of the ATM strike and expirations up to 30 days
        return universe.Strikes(-2, 2).Expiration(timedelta(0), timedelta(30))

    def Evaluate(self):
        # Fetch the current option chain for the underlying symbol
        chain = self.CurrentSlice.OptionChains.get(self.option.Symbol)
        if not chain:
            return

        # Calculate underlying price and identify ATM call and put options
        underlying_price = self.Securities[self.equity].Price
        atm_call, atm_put = self.GetATMOptions(chain, underlying_price)
        if not atm_call or not atm_put:
            self.Debug("No ATM options found")
            return

        # Calculate and log the implied volatilities of the ATM options
        call_iv = self.CalculateIV(atm_call, underlying_price)
        put_iv = self.CalculateIV(atm_put, underlying_price)
        if call_iv is None or put_iv is None:
            self.Debug("Could not calculate implied volatility")
            return

        avg_iv = (call_iv + put_iv) / 2
        self.Debug(f"{self.equity} ATM Call IV: {call_iv:.2%}, Put IV: {put_iv:.2%}, Avg IV: {avg_iv:.2%}")

        # Check if the average implied volatility is below 0.5 and place a straddle if it is
        if avg_iv < 0.5:
            self.PlaceStraddle(atm_call, atm_put)

    def GetATMOptions(self, chain, underlying_price):
        # Select the option contracts that are closest to being ATM
        atm_contract = min(chain, key=lambda x: abs(x.Strike - underlying_price))
        atm_calls = [o for o in chain if o.Strike == atm_contract.Strike and o.Right == OptionRight.Call]
        atm_puts = [o for o in chain if o.Strike == atm_contract.Strike and o.Right == OptionRight.Put]
        
        return (atm_calls[0] if atm_calls else None, atm_puts[0] if atm_puts else None)

    def CalculateIV(self, contract, underlying_price):
        # Calculate implied volatility using the Black-Scholes model and brentq numerical method
        market_price = (contract.BidPrice + contract.AskPrice) / 2
        if market_price <= 0:
            return None

        T = (contract.Expiry - self.Time).days / 365.0
        if T <= 0:
            self.Debug("Skipping contract with non-positive time to expiry")
            return None

        def bs_price(sigma):
            # Define the Black-Scholes pricing formula dependent on sigma
            d1 = (math.log(underlying_price / contract.Strike) + (0.01 + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)
            if contract.Right == OptionRight.Call:
                return underlying_price * norm.cdf(d1) - contract.Strike * math.exp(-0.01 * T) * norm.cdf(d2)
            else:  # Put
                return contract.Strike * math.exp(-0.01 * T) * norm.cdf(-d2) - underlying_price * norm.cdf(-d1)

        # Use brentq to find the sigma that makes the theoretical price equal to the market price
        try:
            return brentq(lambda sigma: bs_price(sigma) - market_price, 0.01, 2)
        except ValueError:
            return None

    def PlaceStraddle(self, atm_call, atm_put):
        # Place orders for both ATM call and put, creating a straddle position
        self.MarketOrder(atm_call.Symbol, 1)
        self.MarketOrder(atm_put.Symbol, 1)
        self.Debug(f"Placed straddle: Call {atm_call.Symbol}, Put {atm_put.Symbol}")
