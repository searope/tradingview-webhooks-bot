import os
import json
from components.actions.schwab import Schwab

schwab_action = Schwab()
schwab_action.set_data(json.loads(f'''{{
    "ticker": "SPY", 
    "price": "5935", 
    "timestamp": "2024-11-19T21:04:08Z", 
    "option_type": "PUT",
    "action": "STO", 
    "quantity": 1, 
    "expiration": "2025-08-15", 
    "dte": 365, 
    "strike": 650.0,
    "key": "{os.getenv('WEBHOOK_KEY')}"
    }}'''))
schwab_action.run()
pass