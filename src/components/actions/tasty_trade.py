import asyncio
import json

from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from tastytrade import Account
from tastytrade.account import AccountBalance

from components.actions.base.action import Action
from components.utils.tastytrade import TastytradeSession, PositionSummary
from utils.log import get_logger, log_error

logger = get_logger(__name__)

class Action(Enum):
    BTO = 'BTO'
    STO = 'STO'
    BTC = 'BTC'
    STC = 'STC'

@dataclass
class WebHookData:
    ticker: str
    price: Decimal
    timestamp: datetime
    action: Action
    quantity: int
    expiration: date
    # DTE: int
    strike: Decimal

class TastyTrade(Action):
    def __init__(self):
        super().__init__()
    
    def validate_data(self) -> WebHookData:
        """
        Validates the data received from the webhook.
        """
        data = super().validate_data()
        err_msgs = []
        if 'ticker' not in data:
            err_msgs.append('Ticker not found in data.' )
        if 'price' in data:
            try:
                data['price'] = Decimal(data['price'])
            except ValueError:
                err_msgs.append('Price is not a number.')
        else:
            err_msgs.append('Price not found in data.')
        if 'timestamp' in data:
            try:
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            except ValueError:
                err_msgs.append('Invalid timestamp format.')
        else:
            err_msgs.append('Timestamp not found in data.')
        if 'action' not in data:
            err_msgs.append('Action not found in data.')
        else:
            if data['action'] not in [member.value for member in Action]:
                err_msgs.append('Invalid action.')
        if 'quantity' in data:
            try:
                data['quantity'] = int(data['quantity'])
            except ValueError:
                err_msgs.append('Quantity is not an integer.')
        else:
            err_msgs.append('Quantity not found in data.')
        if 'expiration' in data:
            try:
                data['expiration'] = date.fromisoformat(data['expiration'])
            except ValueError:
                err_msgs.append('Invalid expiration format.')
        else:
            err_msgs.append('Expiration not found in data.')
        # if 'DTE' not in data:
        #     err_msgs.append('DTE not found in data.')
        if 'strike' in data:
            try:
                data['strike'] = Decimal(data['strike'])
            except ValueError:
                err_msgs.append('Strike is not a number.')
        else:
            err_msgs.append('Strike not found in data.')
        if err_msgs:
            raise ValueError('\n'.join(err_msgs))
        return WebHookData(**data)

    def run(self, *args, **kwargs):
        super().run(*args, **kwargs)  # this is required
        """
        Custom run method. Add your custom logic here.
        """
        print(self.name, '---> action has run!')
        try:
            data = self.validate_data()  # always get data from webhook by calling this method!
            # {'ticker': 'S1!', 'price': '5935', 'timestamp': '2024-11-19T20:28:17Z', 'action': 'STO', 'quantity': 1, 'expiration': '2025-08-15', 'DTE': 365, 'strike': 650.0, 'key': 'WebhookReceived:f5f3f4'}
        except ValueError as e:
            log_error(e.args[0], json.dumps(self.data, indent=4), logger)
            return
        
        tt_session = TastytradeSession()
        account: Account = tt_session.get_account()
        balances: AccountBalance = account.get_balances(tt_session.session)
        ps:PositionSummary = asyncio.run(tt_session.get_positions())

        self.loging(data, account, balances)

        # equity option positions
        ticker_positions = [p for p in ps.positions if p.underlying_symbol == data.ticker and p.instrument_type == 'EQUITY_OPTION']
        err_msg = None
        if not ticker_positions:
            err_msg = f'No options positions found for {data.ticker}'
        else:
            strike_positions = [p for p in ticker_positions if p.strike_price == data.strike]
            if not strike_positions:
                err_msg = f'No options positions found for {data.ticker} with strike {data.strike}'
            else:
                expiration_positions = [p for p in strike_positions if p.expiration == data.expiration]
                if not expiration_positions:
                    err_msg = f'No options positions found for {data.ticker} with strike {data.strike} and expiration {data.expiration}'
        if err_msg:
            log_error(err_msg, json.dumps(data, indent=4,))
        return
 


    def loging(self, data:WebHookData, account:Account, balances:AccountBalance):
        logger.info(f'Cash balance:     {balances.cash_balance}')
        logger.info(f'Net liquidity:    {balances.net_liquidating_value}')
        logger.info(f'Options BP:       {balances.equity_buying_power}')
        logger.info(f'Options BP:       {balances.derivative_buying_power}')
        logger.info(f'Mainenance req:   {balances.maintenance_requirement}')
        logger.info(f'Cash to withdraw: {balances.cash_available_to_withdraw}')
        logger.info(f'Cash pending:     {balances.pending_cash}')
        logger.info('')

        positions = account.get_positions(TastytradeSession.session, include_marks=True)
        logger.info('POSITIONS')
        for pos in [p for p in positions if p.underlying_symbol == data['ticker']]:
            logger.info('===================================')
            logger.info(f'Symbol:     {pos.symbol}')
            logger.info(f'Type:       {pos.instrument_type}')
            logger.info(f'Quantity:   {pos.quantity}')
            logger.info(f'Direction:  {pos.quantity_direction}')
            logger.info(f'Last price: {pos.close_price}')
            logger.info(f'Avrg cost:  {pos.average_open_price}')
            logger.info(f'PnL:        {(pos.close_price - pos.average_open_price) * pos.quantity * pos.multiplier}')
            logger.info(f'Multiplier: {pos.multiplier}')
        logger.info('===================================')

