#!/usr/bin/env python3
from logging_setup import setup_logger
from api import app

logger = setup_logger('wsgi')
logger.info('WSGI application startup')

application = app

def post_fork(server, worker):
    logger.info(f'Worker spawned (pid: {worker.pid})')
