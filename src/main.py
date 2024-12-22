import os
import uvicorn

from fastapi import FastAPI, Request, Response
from starlette.templating import Jinja2Templates

from components.actions.base.action import am
from components.events.base.event import em
from components.schemas.trading import Order, Position
from utils.log import get_logger, log_ntfy, LogType
from utils.register import register_action, register_event, register_link

# register actions, events, links
from settings import REGISTERED_ACTIONS, REGISTERED_EVENTS, REGISTERED_LINKS

registered_actions = [register_action(action) for action in REGISTERED_ACTIONS]
registered_events = [register_event(event) for event in REGISTERED_EVENTS]
registered_links = [register_link(link, em, am) for link in REGISTERED_LINKS]

#app = Flask(__name__)
app = FastAPI()
templates = Jinja2Templates(directory='templates')

# configure logging
logger = get_logger(__name__)

schema_list = {
    'order': Order().as_json(),
    'position': Position().as_json()
}

@app.get("/")
async def dashboard(request: Request):
    gui_key = os.getenv('GUI_KEY')
    if gui_key is None or gui_key != request.query_params['gui_key']:
        log_ntfy(LogType.ERROR, 'Invalid or missing GUI_KEY.', 'Access Denied', logger=logger)
        return 'Access Denied', 401
    
    '''
    import secrets
    token = secrets.token_urlsafe(24)
    logger.info(f'Generated new GUI key: {token}')
    open('.gui_key', 'w').write(token)
    '''

    # serve the dashboard
    action_list = am.get_all()

    return templates.TemplateResponse(
        request=request,
        name='dashboard.html',
        context={
            'schema_list': schema_list,
            'action_list': action_list,
            'event_list': registered_events,
            'version': 0.5
        }
    )


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if data is None:
        err_msg = \
            f'''Error getting JSON data from request...
                Request data: {await request.body()}
                Request headers: {request.headers}'''
        log_ntfy(LogType.ERROR, err_msg, 'No JSON data in request', logger=logger)
        return 'Error getting JSON data from request', 415
    if 'key' not in data:
        err_msg = \
            f'''Webhook request missing key...
                Request data: {data}'''
        log_ntfy(LogType.ERROR, err_msg, 'Webhook request missing key', logger=logger)
        return 'Webhook request missing key', 400

    logger.info(f'Request Data: {data}')
    triggered_events = []
    for event in em.get_all():
        if event.webhook:
            if event.key == data['key']:
                await event.trigger(data=data)
                triggered_events.append(event.name)

    if not triggered_events:
        log_ntfy(LogType.ERROR, f'No events triggered for webhook request {request.json()}', 'No Events Triggered', logger=logger)
    else:
        logger.info(f'Triggered events: {triggered_events}')

    return Response(status_code=200)


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=5000)
