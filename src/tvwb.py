import json
import os
from subprocess import run

import typer

from utils.copy_template import copy_from_template
from utils.formatting import snake_case
from utils.log import get_logger
from utils.modify_settings import add_action, delete_action, add_event, link_action_to_event, unlink_action_to_event
from utils.validators import CustomName

app = typer.Typer()

# configure logging
logger = get_logger(__name__)


@app.command('start')
def start(
        host: str = typer.Option(
            default='0.0.0.0'
        ),
        port: int = typer.Option(
            default=5000
        ),
        workers: int = typer.Option(
            default=1,
            help='Number of workers to run the server with.',
        ),
        waitress: bool = typer.Option(
            default=False,
            help='Run the server using the Waitress WSGI server.',
        )
):
    def output_gui_info():
        logger.info('GUI is served at the path /?guiKey=<unique_key>')
        logger.info(f'\n\tView GUI dashboard here: http://{host}:{port}?guiKey=your_gui_key_set_as_env_var\n')

    def run_server():
        logger.info("Close server with Ctrl+C in terminal.")
        run(f'uvicorn --host {host} --port {port} --workers {workers} main:app'.split(' '))
        #run(f'gunicorn --bind {host}:{port} wsgi:app --workers {workers} -k uvicorn.workers.UvicornWorker'.split(' '))
        # if waitress:
        #     run(f'waitress-serve --listen={host}:{port} wsgi:app')
        # else:
        #     run(f'gunicorn --bind {host}:{port} wsgi:app --workers {workers}'.split(' '))

    # print info regarding GUI and run the server
    output_gui_info()
    if os.getenv('GUI_KEY') is None or os.getenv('WEBHOOK_KEY') is None \
        or os.getenv('TT_ACCOUNT') is None or os.getenv('TT_USERNAME') is None or os.getenv('TT_PASSWORD') is None: 
        logger.error('Missing environment variables. Please set GUI_KEY, WEBHOOK_KEY, TT_ACCOUNT, TT_USERNAME, TT_PASSWORD')
    else:
        run_server()


@app.command('action:create')
def create_action(
        name: str,
        register: bool = typer.Option(
            ...,
            prompt='Register action?',
            help="Automatically register this event upon creation.",
        ),
):
    """
    Creates a new action.
    """
    logger.info(f'Creating new action --->\t{name}')

    # validate name
    custom_name = CustomName(name)

    # begin copying of template to new target file
    copy_from_template(
        source=f'components/actions/base/template/action_template.py',
        target=f'components/actions/{custom_name.snake_case()}.py',
        tokens=['_TemplateAction_', 'TemplateActionClass', 'template_action'],
        replacements=[custom_name.snake_case(), custom_name.camel_case(), custom_name.snake_case()])

    logger.info(f'Event "{name}" created successfully!')

    if register:
        add_action_to_settings(name)

    return True


@app.command('action:register')
def add_action_to_settings(
        name: str
):
    """
    Registers an action to the actions registry. (Adds to settings.py)
    """
    logger.info(f'Registering action --->\t{name}')
    add_action(name)
    return True


@app.command('action:link')
def action_link(
        action_name: str,
        event_name: str
):
    """
    Links an action to an event.
    """
    logger.info(f'Setting {event_name} to trigger --->\t{action_name}')
    link_action_to_event(action_name, event_name)


@app.command('action:unlink')
def action_unlink(
        action_name: str,
        event_name: str
):
    """
    Unlinks an action from an event.
    """
    logger.info(f'Unlinking {action_name} from {event_name}')
    unlink_action_to_event(action_name, event_name)


@app.command('action:remove')
def remove_action_from_settings(
        name: str,
        force: bool = typer.Option(
            ...,
            prompt="Are you sure you want to remove this action from settings.py?",
            help="Force deletion without confirmation.",
        ),
):
    """
    Removes action from settings.py (unregisters it)
    If you wish to delete the action file, that must be done manually.
    """
    logger.info(f'Deleting action --->\t{name}')
    if force:
        delete_action(name)
    else:
        typer.echo("Aborted!")
    return True


@app.command('event:create')
def create_event(name: str):
    logger.info(f'Creating new event --->\t{name}')

    # validate name
    custom_name = CustomName(name)

    # begin copying of template to new target file
    copy_from_template(
        source=f'components/events/base/template/event_template.py',
        target=f'components/events/{custom_name.snake_case()}.py',
        tokens=['_TemplateEvent_', 'TemplateEventClass', 'template_event'],
        replacements=[f'{custom_name.snake_case()}', custom_name.camel_case(), custom_name.snake_case()])

    logger.info(f'Event "{name}" created successfully!')
    return True


@app.command('event:register')
def register_event(name: str):
    """
    Registers an event to the events registry. (Adds to settings.py)
    """
    logger.info(f'Registering event --->\t{name}')
    try:
        add_event(name)
    except Exception as e:
        logger.error(e)


@app.command('event:trigger')
def trigger_event(name: str):
    logger.info(f'Triggering event --->\t{name}')
    # import event
    event = getattr(__import__(f'components.events.{snake_case(name)}', fromlist=['']), name)()
    event.trigger({})
    return True


@app.command('util:send-webhook')
def send_webhook(key: str):
    logger.info(f'Sending webhook')
    post_data = json.dumps({
        "test": "data",
        "key": key})
    # send with curl
    run(['curl', '-X', 'POST', '-H', 'Content-Type: application/json', '-d', post_data,
         'http://localhost:5000/webhook'])


if __name__ == "__main__":
    app()
