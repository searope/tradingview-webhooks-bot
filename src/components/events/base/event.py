import os
from utils.log import get_logger

logger = get_logger(__name__)


class EventManager:
    def __init__(self):
        self._events = []

    def get_all(self):
        """
        Gets all events from manager
        :return: list of Event()
        """
        return self._events

    def get(self, event_name: str):
        """
        Gets event from manager that matches given name
        :param event_name: name of event
        :return: Event()
        """
        for event in self._events:
            if event.name == event_name:
                return event

        raise ValueError(f'Cannot find event with name {event_name}')


em = EventManager()


class Event:
    objects = em

    def __init__(self):
        self.name = self.get_name()
        self.active = True
        self.webhook = True  # all events are webhooks by default
        self.key = os.getenv('WEBHOOK_KEY')
        self._actions = []

    def get_name(self):
        return type(self).__name__

    def add_action(self, action):
        self._actions.append(action)

    def register(self):
        self.objects._events.append(self)

    def __str__(self):
        return f'{self.name}'

    def get_last_log_time(self):
        return self.logs[-1].get_event_time()

    def register_action(self, action):
        """
        Will implement checking here eventually (tm)
        :param action: Action() to register
        """
        self._actions.append(action)

    async def trigger(self, *args, **kwargs):
        if self.active:
            logger.info(f'EVENT TRIGGERED --->\t{str(self)}')

            # pass data
            data = kwargs.get('data')

            for action in self._actions:
                action.set_data(data)
                await action.run()
        else:
            logger.info(f'EVENT NOT TRIGGERED (event is inactive) --->\t{str(self)}')
