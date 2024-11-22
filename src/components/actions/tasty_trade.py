from datetime import datetime, date
from tastytrade import Account
from tastytrade.account import AccountBalance

from components.actions.base.action import Action
from components.utils.tastytrade import TastytradeSession
from utils.log import get_logger

logger = get_logger(__name__)

class TastyTrade(Action):
    def __init__(self):
        super().__init__()

    def run(self, *args, **kwargs):
        super().run(*args, **kwargs)  # this is required
        """
        Custom run method. Add your custom logic here.
        """
        print(self.name, '---> action has run!')
        data = self.validate_data()  # always get data from webhook by calling this method!
        # {'ticker': 'S1!', 'price': '5935', 'timestamp': '2024-11-19T20:28:17Z', 'action': 'STO', 'quantity': 1, 'expiration': '2025-08-15', 'DTE': 365, 'strike': 650.0, 'key': 'WebhookReceived:f5f3f4'}
        
        #data['ticker']
        data['price'] = float(data['price'])
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        #data['action']
        data['quantity'] = int(data['quantity'])
        data['expiration'] = date.fromisoformat(data['expiration'])
        data['DTE'] = int(data['DTE'])
        data['strike'] = float(data['strike'])

        tt_session = TastytradeSession()

        account: Account = tt_session.get_account()
        balances: AccountBalance = account.get_balances(tt_session.session)

        self.loging(data, account, balances)

    def loging(self, data, account, balances):
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

