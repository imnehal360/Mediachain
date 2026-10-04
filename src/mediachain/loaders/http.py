"""Opt-in HTTPS downloads with hostname allowlists and pinned public DNS results."""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import socket
import ssl
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from mediachain.core.errors import UnsupportedMediaError
from mediachain.core.models import MediaAsset
from mediachain.loaders.local import FORMATS, LocalLoader


class HTTPSLoader:
    """Caller must explicitly allow every remote host; redirects and proxies are disabled.

    Downloads persist in download_dir so processors can read them. SDK ingestion copies them
    to managed storage; callers own download staging retention.
    """

    def __init__(
        self, allowed_hosts: set[str], download_dir: Path, max_bytes: int = 100 * 1024 * 1024
    ):
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.download_dir, self.max_bytes = download_dir, max_bytes
        self.local = LocalLoader(max_bytes)

    async def load(self, source: str, owner_id: str = "local") -> MediaAsset:
        url = urlsplit(source)
        if (
            url.scheme != "https"
            or url.hostname not in self.allowed_hosts
            or url.username
            or url.password
            or url.port not in (None, 443)
        ):
            raise UnsupportedMediaError(
                "URL must use HTTPS on an explicitly permitted host and port"
            )
        suffix = Path(url.path).suffix.lower()
        if suffix not in FORMATS:
            raise UnsupportedMediaError("URL must identify a supported media file")
        host = str(url.hostname)

        def download() -> Path:
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise UnsupportedMediaError("Remote host resolved to a non-public address")
            # Pin validated IP for connection while TLS still authenticates the allowed hostname.
            address = str(addresses[0][4][0])
            connection = http.client.HTTPSConnection(
                host, timeout=30, context=ssl.create_default_context()
            )
            connection._create_connection = lambda target, timeout, source_address=None: (  # type: ignore[attr-defined]
                socket.create_connection((address, 443), timeout, source_address)
            )
            self.download_dir.mkdir(parents=True, exist_ok=True)
            target = self.download_dir / (uuid4().hex + suffix)
            try:
                path = url.path or "/"
                connection.request(
                    "GET",
                    path + ("?" + url.query if url.query else ""),
                    headers={"Accept-Encoding": "identity"},
                )
                response = connection.getresponse()
                if response.status != 200:
                    raise UnsupportedMediaError(
                        "Remote response was not HTTP 200; redirects are not followed"
                    )
                total = 0
                with target.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise UnsupportedMediaError("Download exceeds file-size limit")
                        output.write(chunk)
                return target
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            finally:
                connection.close()

        path = await asyncio.to_thread(download)
        asset = await self.local.load(str(path), owner_id)
        asset.metadata["remote_source"] = source
        return asset
