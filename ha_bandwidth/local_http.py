"""Hulp voor tests: één verzoek aan een testserver op 127.0.0.1, zonder urllib."""
import http.client


def local_request(port, method, path, data=None, headers=None):
    """Geeft (statuscode, antwoord als bytes) terug. Een foutstatus is geen uitzondering."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=data, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()
