"""Resolve and validate immediately before connecting, then pin the socket
connection to that numeric address. HTTPS retains the original hostname for
SNI and certificate checks. No ambient HTTP proxy can bypass this guard.
"""
import ipaddress
import socket
import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError


def public_addresses(host, port):
    records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not records:
        raise ValueError('SSRF blocked: no address resolved')
    for _, _, _, _, address in records:
        if not ipaddress.ip_address(address[0]).is_global:
            raise ValueError('SSRF blocked: non-public destination')
    return records


class PublicSocketMixin:
    def _new_conn(self):
        records = public_addresses(self._dns_host, self.port)
        last_error = None
        for family, socktype, proto, _, address in records:
            sock = socket.socket(family, socktype, proto)
            try:
                sock.settimeout(self.timeout)
                if self.source_address:
                    sock.bind(self.source_address)
                for opt in self.socket_options or []:
                    sock.setsockopt(*opt)
                # address is already numeric: do not resolve the hostname again.
                sock.connect(address)
                return sock
            except OSError as exc:
                last_error = exc
                sock.close()
        raise NewConnectionError(self, str(last_error))


class PublicHTTPConnection(PublicSocketMixin, HTTPConnection):
    pass


class PublicHTTPSConnection(PublicSocketMixin, HTTPSConnection):
    pass


class PublicHTTPPool(HTTPConnectionPool):
    ConnectionCls = PublicHTTPConnection


class PublicHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = PublicHTTPSConnection


class PublicAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        # Instance-local mapping: never change urllib3's global defaults.
        self.poolmanager.pool_classes_by_scheme = {
            'http': PublicHTTPPool, 'https': PublicHTTPSPool,
        }


def public_session():
    session = requests.Session()
    session.trust_env = False
    session.mount('http://', PublicAdapter())
    session.mount('https://', PublicAdapter())
    return session
