import logging
import os
import requests 
import __main__

NTFY_TOPIC = os.getenv('NTFY_TOPIC')
default_logger = logging.getLogger(__main__.__name__)


def get_logger(name, level=logging.DEBUG) -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    logger = logging.getLogger(name)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    logger.setLevel(level)
    return logger


def log_error(message: str, header: str = None, logger: logging.Logger = None):
    if logger is None:
        logger = default_logger
    if header is None:
        error_msg = 'ERROR: ' + message
    else:
        error_msg = header + '\n' + message
    logger.error(error_msg)
    if NTFY_TOPIC:
        requests.post(f'https://ntfy.sh/{NTFY_TOPIC}', data=(error_msg).encode(encoding='utf-8'))
        # TODO: add markdown formatting to the message https://docs.ntfy.sh/publish/#__tabbed_7_7
        
