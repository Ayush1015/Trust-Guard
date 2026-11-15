"""Targeted regressions; mocked DNS/socket tests are not a penetration test."""
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.public_transport import public_addresses, PublicHTTPConnection
from trust_extras import typosquat_check, redirect_chain_check

class URLTransportTests(unittest.TestCase):
    def test_brand_labels(self):
        cases = {'example.com':None,'www.apple.com':None,'mail.google.com':None,
                 'pineapple.com':None,'g00gle.com':None,'gooogle.com':'google.com',
                 'paypa1.com':'paypal.com','micros0ft.com':'microsoft.com',
                 'gogle.com':'google.com','notpaypal.com':None}
        for host, expected in cases.items():
            with self.subTest(host=host):self.assertEqual(typosquat_check(host),expected)

    def test_no_unguarded_redirect(self):
        with patch('requests.head',side_effect=AssertionError('must not fetch')):
            self.assertFalse(redirect_chain_check('http://169.254.169.254')['checked'])

    def test_mixed_dns_is_rejected(self):
        records=[(2,1,6,'',('93.184.216.34',80)),(2,1,6,'',('127.0.0.1',80))]
        with patch('socket.getaddrinfo',return_value=records):
            with self.assertRaises(ValueError):public_addresses('attacker.example',80)

    def test_numeric_socket_pinning(self):
        records=[(2,1,6,'',('93.184.216.34',80))]
        with patch('socket.getaddrinfo',return_value=records) as dns, patch('socket.socket') as sock:
            conn=PublicHTTPConnection('example.com',port=80,timeout=5)
            conn._new_conn()
            self.assertEqual(dns.call_count,1)
            sock.return_value.connect.assert_called_once_with(('93.184.216.34',80))

if __name__=='__main__':unittest.main()
