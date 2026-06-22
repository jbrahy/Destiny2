from fastapi import Request


def get_pool(request: Request):
    return request.app.state.pool
