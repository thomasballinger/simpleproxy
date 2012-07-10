"""HTTP Proxy Event Loop with Kqueue"""



"""Notes on how nonblocking sockets work:

    error on recv when nothing to read

    error on write when write buffer is full

    '' on recv if socket closed on other end

    broken pipe error on write if receiver closes early


"""
import select
import socket
import time
import re

import cProfile

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
        self.read_done[fd] = False
        self.needs_parsing[fd] = True
        self.is_server_conn[fd] = False
        for d in [self.read_from_write, self.write_from_read]:
            try:
                del d[fd]
            except KeyError:
                pass 
        return True

    def read(self, fd):
        print 'reading!'
        read_buffer = self.read_buffer[fd]
        try:
            #print self.socket
            #print self.socket[fd]
            data = self.socket[fd].recv(SOCKET_READ_AMOUNT)
            print 'read data excerpt:', data[:50]
            read_buffer.append(data)
        except socket.error as ex:
            if str(ex) == "[Errno 35] Resource temporarily unavailable":
                return False
            else:
                raise ex
        if data == '':
            self.read_done[fd] = True
            self.kq.unreg_read(fd)
            if self.is_server_conn[fd]:
                self.socket[fd].close()
        if fd in self.write_from_read:
            assert self.needs_parsing[fd] == False
            print 'setting write flag, since we just made a successful read!'
            self.kq.reg_write(self.write_from_read[fd])
        else:
            print 'fd', fd, 'not in self.write_from_read!!!'
            if self.needs_parsing[fd]:
                self.try_make_request(fd)

    def write(self, fd):
        print 'writing!'
        read_buffer = self.read_buffer[self.read_from_write[fd]]
        if read_buffer:
            send_sock = self.socket[fd]
            print send_sock
            while True:
                print 'beginning write loop'
                l = len(read_buffer[0])
                try:
                    sent = send_sock.send(read_buffer[0])
                    print 'sent', sent, 'bytes of data'
                except socket.error as ex:
                    if str(ex) == "[Errno 35] Resource temporarily unavailable":
                        # remote buffer full!
                        return False
                    else:
                        raise ex
                if l == sent:
                    read_buffer.pop(0)
                else:
                    read_buffer[0] = read_buffer[sent:]
                break
        else:
            print 'but read buffer empty, so nothing to write! Unregistering event for fd', fd
            self.kq.unreg_write(fd)

    def parse(self, fd):
        """Figure out from a list of strings if we find the destination"""
        read_buffer = self.read_buffer[fd]
        for i in xrange(1,len(read_buffer)+1):
            print 'searching for host string in header:'
            #print "".join(read_buffer[:i])
            m = re.search(r'[\r\n]+Host:\s*([^\r\n:]+):(\d+)', "".join(read_buffer[:i]))
            if m:
                print 'found it!'
                (address, port) = m.groups()
                print address, port
                return (address, int(port))
            else:
                n = re.search(r'[\r\n]+Host:\s*([^\r\n]+)', "".join(read_buffer[:i]))
                if n:
                    print 'found it!'
                    port = 80
                    [address] = n.groups()
                    print address, port
                    return (address, int(port))
        else:
            if self.read_done[fd]:
                raise Exception("Don't know where to route request: "+"".join(read_buffer))
            else:
                return False

    def shuttle(self):
        events = self.kq.poll(0)
        if not events:
            return False
        event = events[0]
        #print 'got event', kq.pformat_kevent(event)
        if event.filter == select.KQ_FILTER_READ:
            print 'got read event'
            self.read(event.ident)
        elif event.filter == select.KQ_FILTER_WRITE:
            print 'got write event'
            self.write(event.ident)
        else:
            raise Exception("Not the filter we were expecting for this event")

    def try_make_request(self, fd):
        print 'trying to make request corresponding to',fd
        r = self.parse(fd)
        if r:
            print 'parsing, succeeded, making connection!'
            address, port = r

            self.needs_parsing[fd] = False

            host_sock = socket.socket()
            host_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            host_sock.setblocking(0)
            host_fd = host_sock.fileno()

            try:
                host_sock.connect((address, port))
            except socket.error as ex:
                if str(ex) == "[Errno 36] Operation now in progress":
                    pass
                else:
                    raise ex

            self.socket[host_fd] = host_sock
            self.read_done[host_fd] = False
            self.is_server_conn[host_fd] = True
            self.needs_parsing[host_fd] = False
            #TODO chanage is_server_conn and needs_parsing
            # to be is_server_conn and has_been_parsed
            # and just do the logic when we need to check
            self.kq.reg_write(host_sock)
            self.kq.reg_read(host_sock)

            self.read_from_write[host_fd] = fd
            self.write_from_read[host_fd] = fd
            self.read_from_write[fd] = host_fd

    def iter(self):
        self.accept()
        self.shuttle()

    def demo(self):
        while True:
            t0 = time.time()
            self.iter()
            t1 = time.time()
            raw_input('---loop took %.4f s---' % (t1-t0))

    def loop(self):
        while True:
            self.iter()

if __name__ == '__main__':
    a = AsyncProxy()
    a.loop()
