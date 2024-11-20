from datetime import datetime, date
from components.actions.base.action import Action
from components.utils.tastytrade import TastytradeSession

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

        session = TastytradeSession()
        account = session.get_account()
        positions = account.get_positions(TastytradeSession.session, include_marks=True)
        for pos in [p for p in positions if p.underlying_symbol == data['ticker']]:
            print(pos)        
