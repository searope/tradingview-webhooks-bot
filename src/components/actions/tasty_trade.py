import simplejson as json

from dataclasses import asdict
from datetime import datetime, date
from decimal import Decimal
from tastytrade import Account
from tastytrade.account import AccountBalance
from tastytrade.instruments import InstrumentType

from components.actions.base.action import Action
from components.utils.tastytrade import TastytradeSession, PositionsSummary, Position, WebHookData, OrderDirection, serializer
from utils.log import get_logger, log_ntfy, LogType

logger = get_logger(__name__)


class TastyTrade(Action):
    def __init__(self):
        super().__init__()
    
    async def run(self, *args, **kwargs):
        super().run(*args, **kwargs)  # this is required
        """
        Custom run method. Add your custom logic here.
        """
        print(self.name, '---> action has run!')
        # data = self.validate_data()   # always get data from webhook by calling this method!
        try:
            data = self.get_webhook_data()
            # {'ticker': 'S1!', 'price': '5935', 'timestamp': '2024-11-19T20:28:17Z', 'action': 'STO', 'quantity': 1, 'expiration': '2025-08-15', 'DTE': 365, 'strike': 650.0, 'key': 'WebhookReceived:f5f3f4'}
        except ValueError as e:
            log_ntfy(LogType.ERROR, str(self._raw_data), str(e.args[0]), logger=logger)
            return
        
        tt_session = TastytradeSession()
        account: Account = tt_session.get_account()
        balances: AccountBalance = account.get_balances(tt_session.session)
        ps:PositionsSummary = await tt_session.get_positions()

        self.loging(data, account, balances)

        # equity option positions
        ticker_positions = [p for p in ps.positions if p.underlying_symbol == data.ticker and p.instrument_type == InstrumentType.EQUITY_OPTION]
        err_msg = None
        if not ticker_positions:
            err_msg = f'No options positions found for {data.ticker}'
        else:
            strike_positions = [p for p in ticker_positions if p.strike_price == data.strike]
            if not strike_positions:
                err_msg = f'No options positions found for {data.ticker} ${data.strike}'
            else:
                expiration_positions = [p for p in strike_positions if p.expires_at.date() == data.expiration]
                if not expiration_positions:
                    err_msg = f'No options positions found for {data.ticker} ${data.strike} expr {data.expiration}'
                else:
                    quantity = sum([p.quantity for p in expiration_positions])
                    if (data.action == OrderDirection.STC or data.action == OrderDirection.BTC) and quantity < data.quantity:
                            err_msg = f'Not enough positions ({quantity}) to {data.action} {data.quantity} contracts.'
        if err_msg:
            log_ntfy(LogType.ERROR, err_msg + '\n' + json.dumps(asdict(data), indent=2, default=serializer), logger=logger)
        elif len(expiration_positions) != 1:
            log_ntfy(LogType.ERROR, json.dumps(expiration_positions, indent=2, default=serializer), 'More than one position found.', logger=logger)
        else:            
            log_ntfy(LogType.SUCCESS, json.dumps(expiration_positions, indent=2, default=serializer), 'No errors found.', logger=logger)
        return


    def get_webhook_data(self) -> WebHookData:
        """
        Validates the data received from the webhook.
        """
        data = self.validate_data()   # always get data from webhook by calling this method!
        err_msgs = []
        if 'key' in data:
            del data['key']
        if 'ticker' not in data:
            err_msgs.append('Ticker not found in data.' )
        if 'price' in data:
            try:
                data['price'] = Decimal(data['price'])
            except ValueError:
                err_msgs.append(f'Price is not a number: {data["price"]}.')
        else:
            err_msgs.append('Price not found in data.')
        if 'timestamp' in data:
            try:
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            except ValueError:
                err_msgs.append(f'Invalid timestamp format: {data["timestamp"]}.')
        else:
            err_msgs.append('Timestamp not found in data.')
        if 'action' not in data:
            err_msgs.append('Trade action not found in data.')
        else:
            if data['action'] not in [member.value for member in OrderDirection]:
                err_msgs.append(f'Invalid trade action: {data["action"]}.')
        if 'quantity' in data:
            try:
                data['quantity'] = int(data['quantity'])
            except ValueError:
                err_msgs.append(f'Quantity is not an integer: {data["quantity"]}.')
        else:
            err_msgs.append('Quantity not found in data.')
        if 'expiration' in data:
            try:
                data['expiration'] = date.fromisoformat(data['expiration'])
            except ValueError:
                err_msgs.append(f'Invalid expiration format: {data["expiration"]}.')
        else:
            err_msgs.append('Expiration not found in data.')
        if 'DTE' in data:
            try:
                data['DTE'] = int(data['DTE'])
            except ValueError:
                err_msgs.append(f'DTE is not an integer: {data["DTE"]}.')
        if 'strike' in data:
            try:
                data['strike'] = Decimal(data['strike'])
            except ValueError:
                err_msgs.append(f'Strike is not a number: {data["strike"]}.')
        else:
            err_msgs.append('Strike not found in data.')
        if err_msgs:
            raise ValueError('\n'.join(err_msgs))
        return WebHookData(**data)


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
        for pos in [p for p in positions if p.underlying_symbol == data.ticker]:
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

