"""HTTPS GET with DNS pinning, TLS hostname verification and bounded HTTP/1.1.

No proxy environment, credentials, cookies, automatic redirects or decompression.
The numeric address validated here is the address actually connected to.
"""
import asyncio
from contextlib import asynccontextmanager
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit

import h11

from app.acquisition import AcquisitionError, AcquisitionBudget

HOSTS = {"api.github.com", "codeload.github.com"}


def target(url: str):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc not in HOSTS
                or parsed.username or parsed.password or parsed.fragment or parsed.query
                or not parsed.path.startswith("/") or "\\" in url
                or any(ord(c) < 33 or ord(c) > 126 for c in url)):
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        raise AcquisitionError("unsafe_snapshot") from None


def public_addresses(records):
    addresses = []
    for family, _, _, _, address in records:
        ip = ipaddress.ip_address(address[0])
        if (family not in (socket.AF_INET, socket.AF_INET6) or not ip.is_global
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified
                or getattr(ip, "ipv4_mapped", None) is not None
                or (ip.version == 6 and (ip.sixtofour is not None or ip.teredo is not None))):
            raise AcquisitionError("unsafe_snapshot")
        if address[0] not in addresses:
            addresses.append(address[0])
    if not addresses:
        raise AcquisitionError("network_unavailable")
    return addresses


class Response:
    def __init__(self, reader, writer, connection, expires, budget):
        self.reader, self.writer, self.connection = reader, writer, connection
        self.expires, self.budget = expires, budget
        self.status = None
        self.headers = {}

    async def event(self):
        while True:
            event = self.connection.next_event()
            if event is not h11.NEED_DATA:
                return event
            remaining = min(self.expires - time.monotonic(), self.budget.remaining())
            if remaining <= 0:
                raise AcquisitionError("upstream_timeout")
            data = await asyncio.wait_for(self.reader.read(16384), remaining)
            self.connection.receive_data(data)

    async def begin(self):
        informationals = 0
        while True:
            event = await self.event()
            if isinstance(event, (h11.InformationalResponse, h11.Response)) and (
                    sum(len(k) + len(v) + 4 for k, v in event.headers) + 32 > 32768):
                # h11's incomplete-event cap alone does not reject a large complete header.
                raise AcquisitionError("upstream_unavailable")
            if isinstance(event, h11.InformationalResponse):
                informationals += 1
                if informationals > 4:
                    raise AcquisitionError("upstream_unavailable")
                continue
            if not isinstance(event, h11.Response):
                raise AcquisitionError("upstream_unavailable")
            self.status = event.status_code
            for key, value in event.headers:
                key, value = key.decode("ascii").lower(), value.decode("ascii")
                if key in self.headers:
                    raise AcquisitionError("upstream_unavailable")
                self.headers[key] = value
            if self.headers.get("content-encoding", "identity").lower() != "identity":
                raise AcquisitionError("upstream_unavailable")
            return

    async def chunks(self):
        while True:
            event = await self.event()
            if isinstance(event, h11.Data):
                self.budget.consume(len(event.data))
                yield bytes(event.data)
            elif isinstance(event, h11.EndOfMessage):
                if sum(len(k) + len(v) + 4 for k, v in event.headers) > 32768:
                    raise AcquisitionError("upstream_unavailable")
                return
            else:
                raise AcquisitionError("upstream_unavailable")


class GitHubTransport:
    def __init__(self, resolver=None, connector=None):
        self.resolver = resolver
        self.connector = connector or asyncio.open_connection
        self.tls = ssl.create_default_context()

    @asynccontextmanager
    async def get(self, url: str, budget: AcquisitionBudget, expires: float):
        parsed = target(url)
        budget.request()
        writer = None
        try:
            connect_timeout = min(budget.remaining(), expires - time.monotonic(),
                                  budget.limits["connect_seconds"])
            if connect_timeout <= 0:
                raise AcquisitionError("upstream_timeout")
            async with asyncio.timeout(connect_timeout):
                resolve = self.resolver or asyncio.get_running_loop().getaddrinfo
                records = await resolve(parsed.hostname, 443, type=socket.SOCK_STREAM)
                addresses = public_addresses(records)
                # No re-resolution by TLS/HTTP. One address per physical try.
                reader, writer = await self.connector(
                    addresses[0], 443, ssl=self.tls, server_hostname=parsed.hostname,
                    ssl_handshake_timeout=connect_timeout,
                )
            connection = h11.Connection(h11.CLIENT, max_incomplete_event_size=32768)
            request = h11.Request(method=b"GET", target=parsed.path.encode("ascii"),
                                 headers=[(b"Host", parsed.hostname.encode("ascii")),
                                          (b"User-Agent", b"AI-Software-Engineer/0.1"),
                                          (b"Accept", b"application/vnd.github+json"),
                                          (b"Accept-Encoding", b"identity"),
                                          (b"Connection", b"close")])
            writer.write(connection.send(request) + connection.send(h11.EndOfMessage()))
            await asyncio.wait_for(writer.drain(), min(budget.remaining(), expires - time.monotonic()))
            response = Response(reader, writer, connection, expires, budget)
            await response.begin()
            yield response
        except (TimeoutError, asyncio.IncompleteReadError):
            raise AcquisitionError("upstream_timeout") from None
        except (OSError, h11.ProtocolError, UnicodeError):
            raise AcquisitionError("network_unavailable") from None
        finally:
            if writer is not None:
                writer.close()
                # No unbounded TLS shutdown wait after cancellation/deadline.
