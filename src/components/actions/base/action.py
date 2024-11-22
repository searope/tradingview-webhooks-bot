from utils.log import get_logger

logger = get_logger(__name__)


class ActionManager:
    def __init__(self):
        self._actions = []

    def get_all(self):
        """
        Gets all actions from manager
        :return: list of Action()
        """
        return self._actions

    def get(self, action_name: str):
        """
        Gets action from manager that matches given name
        :param action_name: name of action
        :return: Action()
        """
        for action in self._actions:
            if action.name == action_name:
                return action

        raise ValueError(f'Cannot find action with name {action_name}')


am = ActionManager()


class Action:
    objects = am

    def __init__(self):
        self.name = self.get_name()
        self.logs = []
        self._raw_data = None

    def get_name(self):
        return type(self).__name__

    def __str__(self):
        return f'{self.name}'

    def get_logs(self):
        """
        Gets run logs in descending order
        :return: list
        """
        return self.logs

    def register(self):
        """
        Registers action with manager
        """
        self.objects._actions.append(self)
        logger.info(f'ACTION REGISTERED --->\t{str(self)}')

    def set_data(self, data):
        """Sets data for action"""
        self._raw_data = data

    def validate_data(self):
        """Ensures data is valid"""
        if not self._raw_data:
            raise ValueError('No data provided to action')
        return self._raw_data

    def run(self, *args, **kwargs):
        """
        Runs, logs action
        """
        logger.info(f'ACTION TRIGGERED --->\t{str(self)}')
