#!/usr/bin/python



import logging
import select
import socket
import sys

#import jsonlogger

from Loop import Loop

DEFAULT_PORT = 8000
DEFAULT_HOST = socket.gethostname()

log = logging.getLogger(__name__)
log_handler = logging.StreamHandler()

log.setLevel(logging.INFO)

def main():
    argv = sys.argv
    if len(argv) > 1:
        port = argv[1]
    else:
        port = DEFAULT_PORT

    host = DEFAULT_HOST

    #log_formatter = jsonlogger.JsonFormatter()
    #log_handler.setFormatter(log_formatter)
    #log.addHandler(log_handler)

    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind((socket.gethostname(), port))
    # log.info('Hostname: %s', socket.gethostbyname(host))
    print "Hostname: ", socket.gethostbyname(host)
    print "Connected on port", port
    serversocket.listen(5)

    loop = Loop()
    loop.listening_sockets.append(serversocket)
    loop.add_socket(serversocket, select.KQ_FILTER_READ)
    loop.run()

if __name__ == "__main__":
    main()
