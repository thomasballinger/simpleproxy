"""HTTP Proxy Event Loop with Kqueue"""

import socket

import kq

kq = kq.KQ()

class AsyncProxy(object):
    def __init__(self, port=8000, address='localhost'):
        self.address = address
        self.port = port
        self.listensock = socket.socket()
        self.listensock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listensock.bind((address, port))

    def loop():
        pass
