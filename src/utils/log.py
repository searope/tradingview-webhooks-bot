import logging
import os
import requests 
import __main__
from enum import Enum

NTFY_TOPIC = os.getenv('NTFY_TOPIC')
default_logger = logging.getLogger(__main__.__name__)


class LogType(int, Enum):
    CRITICAL = logging.CRITICAL
    FATAL = logging.FATAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    WARN = logging.WARN
    INFO = logging.INFO
    DEBUG = logging.DEBUG    
    NOTSET = logging.NOTSET
    SUCCESS = -1    


class LogTag(str, Enum):
    # see https://docs.ntfy.sh/publish/#tags-emojis
    CRITICAL = 'fire'
    FATAL = 'fire'
    ERROR = 'rotating_light'
    WARNING = 'warning'
    WARN = 'warning'
    INFO = 'information_source'
    DEBUG = 'lady_beetle'
    SUCCESS = 'white_check_mark'


def get_logger(name, level=logging.DEBUG) -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    logger = logging.getLogger(name)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    logger.setLevel(level)
    return logger


def log_ntfy(log_type:LogType, message: str, title: str = None, log_tags:list[LogTag] = None, logger: logging.Logger = None):
    if logger is None: logger = default_logger
    if log_tags is None: log_tags = []
    
    log_message = (title + ':\t') if title else '' + message
    if log_type == LogType.CRITICAL or log_type == LogType.FATAL:        
        logger.critical(log_message)
        log_tags.insert(0, LogTag.FATAL)
    elif log_type == LogType.ERROR:
        logger.error(log_message)
        log_tags.insert(0, LogTag.ERROR)        
    elif log_type == LogType.WARNING or log_type == LogType.WARN:
        logger.warning(log_message)
        log_tags.insert(0, LogTag.WARNING)        
    elif log_type == LogType.INFO:
        logger.info(log_message)
        log_tags.insert(0, LogTag.INFO)        
    elif log_type == LogType.DEBUG:
        logger.debug(log_message)
        log_tags.insert(0, LogTag.DEBUG)
    elif log_type == LogType.SUCCESS:
        logger.info(log_message)
        log_tags.insert(0, LogTag.SUCCESS)
        title = 'SUCCESS' if title is None else title

    headers = {}
    headers['Title'] = title or logging.getLevelName(log_type)
    headers['Tags'] = ','.join([tag.value for tag in log_tags])

    if NTFY_TOPIC:
        requests.post(f'https://ntfy.sh/{NTFY_TOPIC}', data=(message).encode(encoding='utf-8'), headers=headers)
        # TODO: add markdown formatting to the message https://docs.ntfy.sh/publish/#__tabbed_7_7
        
