"""HTTP Proxy Event Loop with Kqueue"""


"""
Notes on how nonblocking sockets work in Python
error on recv when nothing to read
error on write when write buffer is full
'' on recv if socket closed on other end
broken pipe error on write if receiver closes early
"""
import select
import socket
import time
import re

import kq

KQ = kq.KQ()
SOCKET_READ_AMOUNT = 1024

class Connection(object):
    """A socket that knows what to do when given a kq read or write event.

    Contains a socket and a read_buffer where data is stored.
    On kq_read event, reads data (if any) into read_buffer.
      If socket.recv returns an empty string (done or closed or something),
      it unregisters kq_read event.
    On kq_write event, writes data from corresponding
      connection's (self.relay_cxn) read_buffer.
      If that read_buffer is empty, it unregisters kq_read event.
    """
    def __init__(self, socket, cxn_map):
        self.cxn_map = cxn_map
        self.socket = socket
        self.fd = socket.fileno()
        self.cxn_map[self.fd] = self
        self.done_reading = False
        self.read_buffer = []

    def __repr__(self):
        s = '<'+str(self.__class__.__name__)+(', fd %s' % self.fd)+'>'
        return s

    def close(self):
        print 'should have closed socket'
        pass

    def reg_read(self): KQ.reg_read(self.socket)
    def reg_write(self): KQ.reg_write(self.socket)
    def unreg_read(self): KQ.unreg_read(self.socket)
    def unreg_write(self): KQ.unreg_write(self.socket)

    def read_event(self):
        """Returns number of bytes of data read, or None if closed"""
        try:
            #print 'reading from', self.socket
            data = self.socket.recv(SOCKET_READ_AMOUNT)
            #print 'read data excerpt:', data[:50]
        except socket.error as ex:
            if str(ex) in ["[Errno 35] Resource temporarily unavailable"]:
                return 0
            elif str(ex) in ["socket.error: [Errno 54] Connection reset by peer"]:
                print 'connection reset by peer (dunno what to do about that)'
                pass
            else:
                raise ex
        if data == '':
            self.done_reading = True
            self.unreg_read()
            return None
        else:
            self.read_buffer.append(data)
            print 'read', len(data), 'bytes on', self
            return len(data)

    def write_event(self):
        """Returns the number of bytes written"""
        buff = self.relay_cxn.read_buffer
        if buff:
            l = len(buff[0])
            try:
                sent = self.socket.send(buff[0])
            except socket.error as ex:
                if str(ex) == "[Errno 35] Resource temporarily unavailable":
                    # remote buffer full!
                    return 0
                else:
                    raise ex
            if l == sent:
                buff.pop(0)
            else:
                buff[0] = buff[0][sent:]
            print 'wrote', sent, 'bytes on', self
            return sent
        else:
            #print 'self.relay_cxn.read_buffer empty!'
            self.unreg_write()
            return 0

class ClientConnection(Connection):
    """Connection between client browser and the proxy.

    ClientConnection tries to parse out HTTP headers on each read event
    and create a corresponding ServerConnection (self.relay_cxn) with that parsed information
    until the parsing successfully happens. It closes connection
    if read says remote socket is closed.
    """

    def __init__(self, socket, cxn_map):
        super(ClientConnection, self).__init__(socket, cxn_map)
        self.relay_cxn = None
        KQ.reg_read(self.socket)

    def read_event(self):
        read = super(ClientConnection, self).read_event()
        if read is None:
            self.close()
        if self.relay_cxn:
            self.relay_cxn.reg_write()
        else:
            r = self.parse()
            if r:
                address, port = r
                ServerConnection(self, address, port, self.cxn_map)

    def write_event(self):
        written = super(ClientConnection, self).write_event()

    def parse(self):
        """Find a request's dest. from a list of string in buffer"""
        for i in xrange(1,len(self.read_buffer)+1):
            s = "".join(self.read_buffer[:i])
            m = re.search(r'[\r\n]+Host:\s*([^\r\n:]+):(\d+)', s)
            if m:
                (address, port) = m.groups()
                print "".join()
                return (address, int(port))
            n = re.search(r'[\r\n]+Host:\s*([^\r\n]+)', s)
            if n:
                port = 80
                [address] = n.groups()
                print 'outgoing request parsed:'
                print (address, port)
                return (address, int(port))
        else:
            if self.done_reading:
                #raise Exception("Don't know where to route request from "+str(self.socket.getsockname())+":".join(self.read_buffer))
                print 'lost connection we didn\'t know how to parse'
                print ''.join(self.read_buffer)
                self.socket.close()
            else:
                return False

class ServerConnection(Connection):
    """Connection between proxy and server on the internet.

    ServerConnection always must be passed its corresponding
    ClientConnection on instantiation. On reading data, it triggers
    its pair ServerConnection (self.relay_cxn) to register for kq read events.
    """
    def __init__(self, client_cxn, address, port, cxn_map):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setblocking(0)
        super(ServerConnection, self).__init__(s, cxn_map)
        self.relay_cxn = client_cxn
        self.relay_cxn.relay_cxn = self
        try:
            self.socket.connect((address, port))
        except socket.error as ex:
            if str(ex) == "[Errno 36] Operation now in progress":
                pass
            else:
                raise ex
        self.reg_write()
        self.reg_read()

    def write_event(self):
        written = super(ServerConnection, self).write_event()

    def read_event(self):
        read = super(ServerConnection, self).read_event()

        # Don't worry about it, I imagine servers are allowed to close
        #if read is None:
        #    self.close()

        if read:
            self.relay_cxn.reg_write()


class AsyncHTTPProxy(object):
    """Async HTTP proxy"""
    def __init__(self, port=8000, address='localhost'):
        self.address = address
        self.port = port
        self.listensock = socket.socket()
        self.listensock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listensock.setblocking(0)
        self.listensock.bind((address, port))
        self.listensock.listen(5)
        print 'listening on', address, 'at port', port
        self.cxns = {}

    def accept(self):
        try:
            s, (address, port) = self.listensock.accept()
        except socket.error:
            return False
        fd = s.fileno()
        self.cxns[fd] = ClientConnection(s, self.cxns)
        return True

    def shuttle(self):
        events = KQ.poll(0)
        if not events:
            return False
        event = events[0]
        if event.filter == select.KQ_FILTER_READ:
            self.cxns[event.ident].read_event()
        elif event.filter == select.KQ_FILTER_WRITE:
            self.cxns[event.ident].write_event()
        else:
            raise Exception("Not the filter we were expecting for this event")

    def iter(self):
        self.accept()
        self.shuttle()

    def loop(self):
        while True:
            self.iter()

    def demoloop(self):
        while True:
            t0 = time.time()
            self.iter()
            t1 = time.time()
            raw_input('---loop took %.4f s---' % (t1-t0))

if __name__ == '__main__':
    a = AsyncHTTPProxy()
    a.loop()
