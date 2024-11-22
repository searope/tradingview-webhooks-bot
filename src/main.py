# initialize our Flask application
import os

from flask import Flask, request, render_template, Response

from components.actions.base.action import am
from components.events.base.event import em
from components.schemas.trading import Order, Position
from utils.log import get_logger
from utils.register import register_action, register_event, register_link

# register actions, events, links
from settings import REGISTERED_ACTIONS, REGISTERED_EVENTS, REGISTERED_LINKS

registered_actions = [register_action(action) for action in REGISTERED_ACTIONS]
registered_events = [register_event(event) for event in REGISTERED_EVENTS]
registered_links = [register_link(link, em, am) for link in REGISTERED_LINKS]

app = Flask(__name__)

# configure logging
logger = get_logger(__name__)

schema_list = {
    'order': Order().as_json(),
    'position': Position().as_json()
}


@app.route("/", methods=["GET"])
def dashboard():
    if request.method == 'GET':

        gui_key = os.getenv('GUI_KEY')
        if gui_key is None or gui_key != request.args.get('gui_key'):
            logger.error('Invalid or missing GUI_KEY.')
            return 'Access Denied', 401
        
        '''
        import secrets
        token = secrets.token_urlsafe(24)
        logger.info(f'Generated new GUI key: {token}')
        open('.gui_key', 'w').write(token)
        '''

        # serve the dashboard
        action_list = am.get_all()
        return render_template(
            template_name_or_list='dashboard.html',
            schema_list=schema_list,
            action_list=action_list,
            event_list=registered_events,
            version=0.5
        )


@app.route("/webhook", methods=["POST"])
async def webhook():
    if request.method == 'POST':
        data = request.get_json()
        if data is None:
            logger.error(f'Error getting JSON data from request...')
            logger.error(f'Request data: {request.data}')
            logger.error(f'Request headers: {request.headers}')
            return 'Error getting JSON data from request', 415

        logger.info(f'Request Data: {data}')
        triggered_events = []
        for event in em.get_all():
            if event.webhook:
                if event.key == data['key']:
                    event.trigger(data=data)
                    triggered_events.append(event.name)

        if not triggered_events:
            logger.warning(f'No events triggered for webhook request {request.get_json()}')
        else:
            logger.info(f'Triggered events: {triggered_events}')

    return Response(status=200)


if __name__ == '__main__':
    app.run(debug=True)
