# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
#import numpy as np
import pandas as pd
from math import fabs
from pandas import DataFrame
from datetime import datetime, timezone
from typing import Optional

from freqtrade.strategy import (BooleanParameter, CategoricalParameter, DecimalParameter,
                                IntParameter, IStrategy)

# --------------------------------
# Add your lib to import here
import logging
from freqtrade.constants import Config
from freqtrade.exchange import timeframe_to_minutes
from freqtrade.persistence import Order, PairLocks, Trade

class BaseStrategy(IStrategy):
    """
    This is a strategy template to get you started.
    More information in https://www.freqtrade.io/en/latest/strategy-customization/

    You can:
        :return: a Dataframe with all mandatory indicators for the strategies
    - Rename the class name (Do not forget to update class_name)
    - Add any methods you want to build your strategy
    - Add any lib you need to build your strategy

    You must keep:
    - the lib in the section "Do not remove these libs"
    - the methods: populate_indicators, populate_entry_trend, populate_exit_trend
    You should keep:
    - timeframe, minimal_roi, stoploss, trailing_*
    """

    # Logger used for specific logging for this strategy
    logger = None

    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3

    STRATEGY_VERSION_BASE = '1.11.0'

    # Optimal timeframe for the strategy.
    timeframe = '1h'

    # Can this strategy go short?
    can_short = False

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    # Exit trade at profit of 1%
    minimal_roi = {
        "0": 0.01
    }

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    # Set to -99% to actually disable the stoploss
    stoploss = -0.99

    # Minimum profit used for checking exit of trades
    min_profit = 0.0025 # 0.25%

    # Stoploss configuration
    use_custom_stoploss = False

    # Trailing stoploss
    trailing_stop = False

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = False
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 1

    # Leverage configuration
    leverage_configuration = {}

    # Create custom dictionary for storing run-time data
    custom_info = {}

    # Config related
    config_max_trades = 0

    # Optimize trades (allow new trade when stoploss is activated)
    enable_improved_trade_count = False

    # Set option for logging dataframe and make sure all columns are visible
    pd.set_option('display.max_columns', None)


    def version(self) -> Optional[str]:
        """
        Returns version of the strategy.
        """

        return self.STRATEGY_VERSION_BASE


    def __init__(self, config: Config) -> None:
        """
        Called upon construction of this class. Validate data and initialize
        all attributes,
        """

        # Call to super
        super().__init__(config)

        # Initialize logger
        self.logger = logging.getLogger('freqtrade.strategy')

        # Read config
        if 'max_open_trades' in config:
            if isinstance(config['max_open_trades'], int):
                self.config_max_trades = config['max_open_trades']

        # Make sure the contents of the Leverage configuration is correct
        for k, v in self.leverage_configuration.items():
            self.leverage_configuration[k] = float(v)
       
        # Update minimum ROI table keeping leverage into account
        # TODO: improve later on with custom exit with profit and leverage calculation for each pair
        leverage = min(self.leverage_configuration.values()) if len(self.leverage_configuration) > 0 else 1.0

        for k, v in self.minimal_roi.items():
            self.minimal_roi[k] = round(v * leverage, 4)

        self.stoploss *= leverage


    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """
    
        # Setup cache for dataframes
        self.custom_info['cache'] = {}

        # Setup removal of autolocks
        self.custom_info['remove-autolock'] = []

        # Call to super first
        super().bot_start()
        self.log(f"Version - Base Strategy: '{BaseStrategy.version(self)}'")
        self.log(f"Running with leverage configuration: '{self.leverage_configuration}'")

        # Determine max number of trades
        self.update_max_trade_count()


    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        """
        Called at the start of the bot iteration (one loop).
        Might be used to perform pair-independent tasks
        (e.g. gather some remote resource for comparison)
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """

        # Run some tasks once every five minutes
        if current_time.minute % 5 == 0 and current_time.second <= 8:
            # Clean cache
            self.cleanup_cache()

            # Determine max number of active trades
            self.update_max_trade_count()

        # Check if there are pairs set for which the Auto lock should be reoved
        if len(self.custom_info['remove-autolock']) > 0:
            self.unlock_reason('Auto lock')

            # Sanity check to alert when removing the lock failed
            for pair in self.custom_info['remove-autolock']:
                lock = self.is_locked_until(pair)
                if lock:
                    self.log(
                        f"{pair} has still an active lock until {lock}, while it should have been removed!",
                        level="ERROR"
                    )

            # Clear the list
            self.custom_info['remove-autolock'].clear()

        return super().bot_loop_start(current_time)


    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your memory and CPU usage.
        :param dataframe: Dataframe with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: a Dataframe with all mandatory indicators for the strategies
        """

        return dataframe


    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """

        dataframe.loc[:,'enter_long'] = 0
        dataframe.loc[:,'enter_short'] = 0

        return dataframe


    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """

        dataframe.loc[:,'exit_long'] = 0
        dataframe.loc[:,'exit_short'] = 0

        return dataframe


    def confirm_trade_exit(self, pair: str, trade: 'Trade', order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:
        """
        Called right before placing a regular exit order.
        Timing for this function is critical, so avoid doing heavy computations or
        network requests in this method.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns True (always confirming).

        :param pair: Pair for trade that's about to be exited.
        :param trade: trade object.
        :param order_type: Order type (as configured in order_types). usually limit or market.
        :param amount: Amount in base currency.
        :param rate: Rate that's going to be used when using limit orders
                     or current rate for market orders.
        :param time_in_force: Time in force. Defaults to GTC (Good-til-cancelled).
        :param exit_reason: Exit reason.
            Can be any of ['roi', 'stop_loss', 'stoploss_on_exchange', 'trailing_stop_loss',
                           'exit_signal', 'force_exit', 'emergency_exit']
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return bool: When True, then the exit-order is placed on the exchange.
            False aborts the process
        """

        confirmed = super().confirm_trade_exit(pair, trade, order_type, amount,
                                             rate, time_in_force, exit_reason,
                                             current_time)

        # Calculate profit and reject if lower than minimum profit.
        # Allow force_exit and emergency_exit to bypass this check.
        if exit_reason in ('roi', 'stop_loss', 'stoploss_on_exchange', 'trailing_stop_loss', 'exit_signal'):
            current_profit = trade.calc_profit_ratio(rate)
            if current_profit <= self.min_profit:
                confirmed = False

                self.log(
                    f"{pair}: Reject exit ('{exit_reason}') on rate {rate} as the profit is {current_profit}.",
                    "WARNING"
                )

        return confirmed


    def order_filled(self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs) -> None:
        """
        Called right after an order fills. 
        Will be called for all order types (entry, exit, stoploss, position adjustment).
        :param pair: Pair for trade
        :param trade: trade object.
        :param order: Order object.
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """

        super().order_filled(pair, trade, order, current_time)

        # Remove custom data when the 'sell' order has filled and the trade is closed
        # Checking if the trade is closed, should take partially sells into account, as
        # the trade will only be closed when the total amount has been sold
        # TODO: monitor what will happen with partially filled 'sell' orders
        if order.ft_order_side == trade.exit_side and not trade.is_open:
            custompairkey = self.get_custom_pairkey(trade.pair, trade.trade_direction)

            if custompairkey in self.custom_info:
                del self.custom_info[custompairkey]

                self.log(f"Removed custom data storage for '{custompairkey}'")

        # Determine max number of trades
        self.update_max_trade_count()

        return None


    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        Customize leverage for each new trade. This method is only called in futures mode.

        :param pair: Pair that's currently analyzed
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param proposed_leverage: A leverage proposed by the bot.
        :param max_leverage: Max leverage allowed on this pair
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :return: A leverage amount, which is between 1.0 and max_leverage.
        """

        leverage = 1.0

        pairkey = f"{pair}_{side}"
        if pairkey in self.leverage_configuration:
            leverage = self.leverage_configuration[pairkey]
        elif 'default' in self.leverage_configuration:
            leverage =  self.leverage_configuration['default']

        self.log(f"Returning leverage '{leverage}' for pair {pair} and side {side}. Configuration = {self.leverage_configuration}")

        return leverage


    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                        current_profit: float, after_fill: bool, **kwargs) -> Optional[float]:
        """
        Custom stoploss logic, returning the new distance relative to current_rate (as ratio).
        e.g. returning -0.05 would create a stoploss 5% below current_rate.
        The custom stoploss can never be below self.stoploss, which serves as a hard maximum loss.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns the initial stoploss value
        Only called when use_custom_stoploss is set to True.

        :param pair: Pair that's currently analyzed
        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param current_profit: Current profit (as ratio), calculated based on current_rate.
        :param after_fill: True if the stoploss is called after the order was filled.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float: New stoploss value, relative to the current rate
        """

        return None


    def create_custom_data(self, pair_key):
        """
        Create the custom data contact for storage during the runtime of this bot.

        :param pair_key: The key to create the data for.
        """

        if not pair_key in self.custom_info:
            # Create empty entry for this trade
            self.custom_info[pair_key] = {}

            self.log(f"Created custom data storage for pair {pair_key}.")


    def get_custom_pairkey(self, pair: str, side: str) -> str:
        """
        Get the custom pairkey used for runtime storage of trade data

        :param pair: Trading pair
        :param side: Direction of the trade (long/short)
        :return str: The composed pairkey
        """

        return f"{pair}_{side}"


    def get_round_digits(self, pair: str) -> int:
        """
        Get the number of digits to use for logging purposes based on the pair

        :param pair: the pair
        :return int: number of digits to use
        """

        numberofdigits = 4

        base = pair.split('/')[1]

        if base in ('BTC', 'ETH'):
            numberofdigits = 8

        return numberofdigits


    def log(self, message: str, level='INFO', notify=None):
        """
        Function for logging data on a certain level Can also send
        a notification. For WARNING and ERROR the nofication is always send.

        :param message: Message to log and optionally send in a notification
        :param level: The level of the message
        :param notify: Indication if a notification should be send
        """

        send_notification = False if notify is None else notify

        if self.logger:
            dt_utc = datetime.now(timezone.utc)

            timedmsg = f"UTC {dt_utc.strftime('%Y-%m-%d %H:%M:%S')} - {message}"

            match level:
                case 'INFO':
                    self.logger.info(timedmsg)
                case 'DEBUG':
                    self.logger.debug(timedmsg)
                case 'WARNING':
                    self.logger.warning(timedmsg)
                    send_notification = True if notify is None else notify # Force notification
                case 'ERROR':
                    self.logger.error(timedmsg)
                    send_notification = True if notify is None else notify # Force notification

        if send_notification:
            self.dp.send_msg(message)


    def log_dataframe(self, df: DataFrame, msg="", number_of_rows=5):
        """
        Log a number of rows of the dataframe to the logger.

        :param df: Dataframe
        :param msg: Option message
        :param number_of_rows: The number of rows to log
        """
        
        self.log(
            f"{msg}: {df.tail(number_of_rows)}"
        )


    def store_dataframe(self, df: DataFrame, path: str):
        """
        Store dataframe to disk on the specified location.

        :param df: Dataframe to be stored
        :param path: Location to store the dataframe
        """

        df.to_csv(path, index=False, encoding='utf-8')


    def schedule_remove_autolock(self, pair: str):
        """
        Freqtrade locks a pair after closing a trade, thus preventing 
        entering a new trade within the same candle. Sometimes it's
        desired to adopt a ASAP strategy, and there is the need to
        remove this Auto lock. Derived strategies can use this function
        to schedule such removal.

        :param pair: Pair to remove the Auto lock for
        """

        self.custom_info['remove-autolock'].append(pair)
        self.log(
            f"Scheduled {pair} for removal of Auto Lock."
        )


    def is_locked_until(self, pair: str) -> str:
        """
        Get the readable time till the specified pair is locked

        :param pair: the pair to get the lock time for
        :return str: readable date/time
        """

        until = ""

        pl = PairLocks.get_pair_longest_lock(pair)
        if pl is not None:
            until = pl.lock_end_time.strftime('%Y-%m-%d %H:%M:%S')

        return until


    def cache_dataframe(self, df: DataFrame, pair: str, tf: str):
        """
        Store (or update) a dataframe for a certain pair and timeframe in the cache.
        The dataframe is copied to make sure no alternations are made, and the 
        current time will be stored in order to clean-up things later.

        :param df: Dataframe to store
        :param pair: Pair the Dataframe belongs to
        :param tf: Timeframe the Dataframe belongs to
        """

        key = f"{pair}_{tf}"
        if not key in self.custom_info['cache']:
            # Create empty entry for this trade
            self.custom_info['cache'][key] = {}
            self.custom_info['cache'][key]['tf'] = tf

            self.log(f"Created custom cache storage for {key}.")

        self.custom_info['cache'][key]['df'] = df.copy()
        self.custom_info['cache'][key]['datetime'] = datetime.now()


    def get_dataframe_from_cache(self, pair: str, tf: str) -> DataFrame:
        """
        Get a dataframe from the cache, if present.

        :param pair: The pair to get the dataframe for
        :param tf: The timeframe to the dataframe for
        :return DataFrame: Dataframe for the pair and specified timeframe, or None of not found
        """

        key = f"{pair}_{tf}"
        if key in self.custom_info['cache']:
            return self.custom_info['cache'][key]['df']

        return None


    def refresh_data_required(self, old_df: DataFrame, new_df: DataFrame) -> bool:
        """
        Determine if the cached dataframe needs to be refreshed (and data needs to be 
        recalculated). Last candle of both dataframes is compared for this.

        :param old_df: Previous DataFrame
        :param new_df: Current DataFrame
        :return bool: True if the last candle doesn't match, otherwise False        
        """

        refresh = False
        if old_df is None:
            refresh = True
        else:
            last_old_candle = old_df.iloc[-1].squeeze()
            last_new_candle = new_df.iloc[-1].squeeze()

            if last_old_candle['date'] != last_new_candle['date']:
                refresh = True

        return refresh


    def cleanup_cache(self):
        """
        Cleanup the cache with stored dataframes if the last updated time has passed (with a margin of two minutes).
        """

        outdatedkeys = []

        currentdatetime = datetime.now()
        for key in self.custom_info['cache']:
            minutes = (currentdatetime - self.custom_info['cache'][key]['datetime']).total_seconds() / 60
            
            if (minutes - 2) > timeframe_to_minutes(self.custom_info['cache'][key]['tf']):
                outdatedkeys.append(key)

                self.log(f"Removing cache storage for '{key}' because last update was {minutes} minutes ago")

        for key in outdatedkeys:
            del self.custom_info['cache'][key]


    def update_max_trade_count(self):
        """
        Update the max number of active trades. A new trade is allowed to start when another trade is
        running in stoploss, meaning no funds are required for additional orders. These funds can be
        used to open already a new trade, optimizing the performance of the wallet.
        """

        if not self.enable_improved_trade_count:
            return

        sl_trade_count = self.get_trade_stoploss_count()
        current_trade_count = self.max_open_trades

        new_trade_count = self.config_max_trades + sl_trade_count

        if current_trade_count != new_trade_count:
            self.log(
                f"Changing max allowed open trades from {current_trade_count} to {new_trade_count} based on "
                f"config {self.config_max_trades} and currently {sl_trade_count} trades running in stoploss.",
                notify=True
            )
            self.max_open_trades = new_trade_count
            self.config['max_open_trades'] = new_trade_count
        else:
            self.log(
                f"Leaving max allowed open trades on {new_trade_count} based on "
                f"config {self.config_max_trades} and currently {sl_trade_count} trades running in stoploss."
            )


    def get_trade_stoploss_count(self):
        """
        Get the number of trades with an active stoploss
        """

        trade_count = 0

        opentrades = Trade.get_trades_proxy(is_open=True)
        for opentrade in opentrades:
            ticker = self.dp.ticker(opentrade.pair)
            current_rate = ticker['last']

            # calculate distance to stoploss
            stoploss_current_dist = opentrade.stop_loss - current_rate
            stoploss_current_dist_ratio = stoploss_current_dist / current_rate

            self.log(
                f"{opentrade.pair}: current_rate is {current_rate}. Stoploss is {opentrade.stop_loss} ({opentrade.stop_loss_pct}%). SL distance is {stoploss_current_dist} with ratio {stoploss_current_dist_ratio}.",
                "DEBUG"
            )

            if fabs(opentrade.initial_stop_loss_pct - stoploss_current_dist_ratio) > 0.1:
                self.log(
                    f"{opentrade.pair}: stoploss is active!",
                    "DEBUG"
                )
                trade_count += 1

        return trade_count