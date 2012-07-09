"""HTTP Proxy Event Loop with Kqueue"""

import select
import socket
import time

from collections import defaultdict

import kq

SOCKET_READ_AMOUNT = 1024
class AsyncProxy(object):
    def __init__(self, port=8000, address='localhost'):
        self.address = address
        self.port = port
        self.listensock = socket.socket()
        self.listensock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listensock.setblocking(0)
        self.listensock.bind((address, port))
        self.listensock.listen(5)
        print 'listening on', address, 'at port', port
        self.kq = kq.KQ()

        self.socket = {}
        self.read_from_write = {}
        self.write_from_read = {}
        self.is_server_conn = {}
        self.needs_parsing = {}
        self.read_buffer = defaultdict(list)
        self.read_done = {}

    def accept(self):
        try:
            s, (address, port) = self.listensock.accept()
        except socket.error:
            return False
        fd = s.fileno()
        self.socket[fd] = s
        self.kq.reg_read(s)
        self.client_requests.append(fileno())
        self.read_done[fd] = False
        self.needs_parsing[fd] = True
        self.is_server_conn[fd] = False
        return True

    def read(self, fd):
        read_buffer = self.read_buffer[fd]
        while True:
            read_buffer.append(self.fd_to_socket[fd].read(SOCKET_READ_AMOUNT))
            break
        if 'done reading':
            self.read_done[fd] = True
            self.kq.unreg_read(fd)
            if self.is_server_conn[fd]:
                self.socket[fd].close()
        if fd in self.write_from_read:
            assert self.needs_parsing[fd] == False
            self.kq.reg_write(self.write_from_read[fd])
        else:
            assert self.needs_parsing[fd] == True

    def write(self, fd):
        read_buffer = self.read_buffer[self.read_from_write[event.ident]]
        if read_buffer:
            send_sock = self.fd_to_socket[event.ident]
            while True:
                l = len(read_buffer[0])
                sent = send_sock.send(read_buffer[0])
                if l == sent:
                    read_buffer.pop(0)
                else:
                    read_buffer[0] = read_buffer[sent:]
                break
        else:
            self.kq.unreg_write(fd)

    def parse(self, fd):
        """Figure out from a list of strings if we find the destination"""
        pass # TODO current stopping point

    def shuttle(self):
        events = self.kq.poll(0)
        if not events:
            return False
        event = events[0]
        print 'got event', kq.pformat_kevent(event)
        if event.filter == select.KQ_FILTER_READ:
            self.read(event.ident)
        elif event.filter == select.KQ_FILTER_WRITE:

    def make_pending_requests(self):
        # check self.client_requests for buffers with enough data to start passing them along
        # if so, add 

    def loop(self):
        while True:
            print 'loop start'
            self.accept()
            self.shuttle()
            self.make_pending_requests()
            raw_input()

if __name__ == '__main__':
    a = AsyncProxy()
    a.loop()
