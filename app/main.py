import logging
from http import HTTPStatus

import sqlalchemy
from fastapi import FastAPI, BackgroundTasks
from fastapi.param_functions import Depends
from fastapi.responses import Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket, WebSocketDisconnect

from api.requests import PostCreationFromShortcode
from services.entities import ProfileListResult
from services.exceptions import PostNotFound
from services.post import PostService
from services.profile import ProfileService
from services.schema import create_connection

app = FastAPI()
app.mount('/web', StaticFiles(directory='/web', html=True), name='web')
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@app.get('/')
def root():
    return RedirectResponse(url='web/index.html')


@app.get('/index.html')
def index():
    return RedirectResponse(url='web/index.html')


@app.get('/api/profiles/', response_model=ProfileListResult)
async def list_profiles(connection: sqlalchemy.engine.Connection = Depends(create_connection)):
    return await ProfileService(connection).list()


@app.post('/api/posts/from_shortcode/')
def create_post_from_url(
        request: PostCreationFromShortcode,
        background_tasks: BackgroundTasks,
        connection: sqlalchemy.engine.Connection = Depends(create_connection)
):
    background_tasks.add_task(PostService(connection).create_from_shortcode, request.shortcode)
    return Response(status_code=HTTPStatus.ACCEPTED)


@app.websocket('/web_socket/posts/')
async def posts(
        web_socket: WebSocket,
        connection: sqlalchemy.engine.Connection = Depends(create_connection)
):
    await web_socket.accept()
    try:
        while True:
            data = await web_socket.receive_json()
            if shortcode := data.get('shortcode'):
                try:
                    post = await PostService(connection).create_from_shortcode(shortcode)
                    await web_socket.send_json({'event': 'post.saved', 'shortcode': shortcode, 'post': post.response})
                except PostNotFound as e:
                    await web_socket.send_json(e.response)
    except WebSocketDisconnect:
        logger.debug('Web socket disconnected.')
