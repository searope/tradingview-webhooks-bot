import asyncio
import os
import pickle

from datetime import date
from dataclasses import dataclass
from importlib.resources import as_file, files

from tastytrade import Account, Session, DXLinkStreamer
from tastytrade.instruments import get_option_chain, Option, OptionType
from tastytrade.dxfeed import Greeks, Quote
from tastytrade.utils import today_in_new_york


TOKEN_PATH = '.session'


class RenewableSession(Session):
    def __init__(self):
        token_path = os.path.join(os.getcwd(), TOKEN_PATH)

        logged_in = False
        # try to load token
        if os.path.exists(token_path):
            with open(token_path, 'rb') as f:
                self.__dict__ = pickle.load(f)

            # make sure token hasn't expired
            logged_in = self.validate()

        if not logged_in:
            # either the token expired or doesn't exist
            username, password = self._get_credentials()
            Session.__init__(self, username, password)

            accounts = Account.get_accounts(self)
            self.accounts = [acc for acc in accounts if not acc.is_closed]
            # write session token to cache
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, 'wb') as f:
                pickle.dump(self.__dict__, f)
            print('Logged in with new session, cached for next login.')
        else:
            print('Logged in with cached session.')

    def _get_credentials(self):
        username = os.getenv('TT_USERNAME')
        password = os.getenv('TT_PASSWORD')

        if not username:
            raise Exception('Username is not provided!')
        if not password:
            raise Exception('Password is not provided!')

        return username, password

    def get_account(self) -> Account:
        account = os.getenv('TT_ACCOUNT')
        if not account:
            raise Exception('Account number is not provided!')        
        try:
            return next(a for a in self.accounts if a.account_number == account)
        except StopIteration:
            err_msg = f'Account {account} is provided, but the account doesn\'t appear to exist!'
            print(err_msg)
            raise Exception(err_msg)
    

@dataclass
class LivePrices:
    quotes: dict[str, Quote]
    greeks: dict[str, Greeks]
    streamer: DXLinkStreamer
    puts: list[Option]
    calls: list[Option]

    @classmethod
    async def create(
        cls,
        session: Session,
        symbol: str = 'SPY',
        expiration: date = today_in_new_york()
    ):
        chain = get_option_chain(session, symbol)
        options = [o for o in chain[expiration]]
        # the `streamer_symbol` property is the symbol used by the streamer
        streamer_symbols = [o.streamer_symbol for o in options]

        streamer = await DXLinkStreamer.create(session)
        puts = [o for o in options if o.option_type == OptionType.PUT]
        calls = [o for o in options if o.option_type == OptionType.CALL]
        self = cls({}, {}, streamer, puts, calls)

        tasks = []
        # subscribe to quotes and greeks for all options on that date
        await streamer.subscribe(Quote, [symbol] + streamer_symbols)
        tasks.append(asyncio.create_task(self._update_quotes()))
        # await streamer.subscribe(Greeks, streamer_symbols)
        # tasks.append(asyncio.create_task(self._update_greeks()))

        asyncio.gather(*tasks)

        # wait we have quotes and greeks for each option
        while len(self.greeks) != len(options) or len(self.quotes) != len(options):
            await asyncio.sleep(1)

        return self

    async def _update_greeks(self):
        async for e in self.streamer.listen(Greeks):
            self.greeks[e.eventSymbol] = e

    async def _update_quotes(self):
        async for e in self.streamer.listen(Quote):
            self.quotes[e.eventSymbol] = e


async def main():
    session = Session('searope', 'ZuXmkk7wtr3qvVk')
    live_prices = await LivePrices.create(session, 'SPY')
    # symbol = live_prices.calls.items[0].streamer_symbol
    
    while True:
        #expiration = live_prices.calls.values()[0].expiration
        # live_prices.trades.price
        await asyncio.sleep(1)


    print(live_prices.quotes[symbol], live_prices.greeks[symbol])


if __name__ == '__main__':
    asyncio.run(main())