import os
import schwabdev
import simplejson as json

from datetime import datetime, date
from decimal import Decimal
from enum import Enum

from components.actions.base.action import Action
from components.utils.tastytrade import WebHookData
from utils.log import get_logger, log_ntfy, LogType

logger = get_logger(__name__)


class OptionType(str, Enum):
    CALL = "C"
    PUT = "P"

class OrderDirection(str, Enum):
    BTO = 'BTO'
    STO = 'STO'
    BTC = 'BTC'
    STC = 'STC'
    BUY = 'BUY'
    SELL = 'SELL'

    
class Schwab(Action):
    def __init__(self):
        super().__init__()
    
    
    async def run(self, *args, **kwargs):
        super().run(*args, **kwargs)  # this is required
        """
        Custom run method. Add your custom logic here.
        """
        logger.info(self.name + ' ---> action has run!')
        try:
            data = self.get_webhook_data()
            # {'ticker': 'S1!', 'price': '5935', 'timestamp': '2024-11-19T20:28:17Z', 'action': 'STO', 'quantity': 1, 'expiration': '2025-08-15', 'dte': 365, 'strike': 650.0, 'key': 'WebhookReceived:f5f3f4'}
        except Exception as e:
            log_ntfy(LogType.ERROR, str(self._raw_data), str(e.args[0]), logger=logger)
            return
        
        app_key = os.getenv('SCHWAB_APP_KEY')
        app_secret = os.getenv('SCHWAB_APP_SECRET')
        callback_url = os.getenv('SCHWAB_CALLBACK_URL')
        client = schwabdev.Client(app_key, app_secret, callback_url)
        
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
        if 'option_type' in data:
            if str(data['option_type']).upper()[0] not in [member.value for member in OptionType]:
                err_msgs.append(f'Invalid option type: {data["option_type"]}.')
            else:
                data['option_type'] = OptionType.CALL if str(data['option_type']).upper()[0] == 'C' else OptionType.PUT
        else:
            err_msgs.append('Option type not found in data. Expected: CALL | PUT')
        if 'action' in data:
            if data['action'] not in [member.value for member in OrderDirection]:
                err_msgs.append(f'Invalid trade action: {data["action"]}. Expected: STO | BTC | STC | BTC')
        else:
            err_msgs.append('Trade action not found in data.')
        if 'quantity' in data:
            try:
                qty = int(data['quantity'])
                if qty <= 0:
                    err_msgs.append(f'Quantity must be a positive integer: {data["quantity"]}.')
                else:
                    data['quantity'] = qty
            except ValueError:
                err_msgs.append(f'Quantity is not an integer: {data["quantity"]}.')
        else:
            err_msgs.append('Quantity not found in data.')
        if 'expiration' in data:
            try:
                data['expiration'] = date.fromisoformat(data['expiration'])
            except ValueError:
                err_msgs.append(f'Invalid expiration format: {data["expiration"]}.')
        if 'dte' in data:
            try:
                data['dte'] = int(data['dte'])
            except ValueError:
                err_msgs.append(f'dte is not an integer: {data["dte"]}.')
        if 'expiration' not in data and 'dte' not in data:
            err_msgs.append('Either expiration or dte must be provided.')
        if 'strike' in data:
            try:
                data['strike'] = Decimal(data['strike'])
            except ValueError:
                err_msgs.append(f'Strike is not a number: {data["strike"]}.')
        if 'delta' in data:
            try:
                data['delta'] = int(data['delta'])
            except ValueError:
                err_msgs.append(f'Delta is not an integer: {data["delta"]}. Expected: 5-95')
        if data['action'] in [OrderDirection.STO.value, OrderDirection.BTO.value]:
            if 'strike' not in data and 'delta' not in data:
                err_msgs.append('Either strike or delta must be provided for opening positions.')     
            if 'expiration' not in data and 'dte' not in data:
                err_msgs.append('Either expiration or dte must be provided for opening positions.')
        if data['action'] in [OrderDirection.STC.value, OrderDirection.BTC.value]:
            if 'strike' not in data:
                err_msgs.append('Strike must be provided for closing positions.')
            if 'expiration' not in data:
                err_msgs.append('Expiration must be provided for closing positions.')
        if err_msgs:
            raise ValueError('\n'.join(err_msgs))
        exclude_extra_data = {k: v for k, v in data.items() if k in WebHookData.__dataclass_fields__}
        return WebHookData(**exclude_extra_data)

""" def account_data_logging(self, data:WebHookData, account:Account, balances:AccountBalance):
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
"""