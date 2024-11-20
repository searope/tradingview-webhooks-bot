import json
from components.actions.tasty_trade import TastyTrade

tt_action = TastyTrade()
tt_action.set_data(json.loads('''{
    "ticker": "S1!", 
    "price": "5935", 
    "timestamp": "2024-11-19T21:04:08Z", 
    "action": "STO", 
    "quantity": 1, 
    "expiration": "2025-08-15", 
    "DTE": 365, 
    "strike": 650.0,
    "key": "WebhookReceived:f5f3f4"
} '''))
tt_action.run()
pass