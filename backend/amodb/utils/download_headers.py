"""Normalize legacy UUID download names without touching files or streamed bodies."""
from email.message import Message
from pathlib import PurePath

from starlette.types import ASGIApp, Receive, Scope, Send, Message as ASGIMessage

from .download_names import _UUID, attachment_header, download_name


class DownloadFilenameMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def normalized_send(message: ASGIMessage):
            if message["type"] == "http.response.start":
                headers = []
                for key, value in message.get("headers", []):
                    if key.lower() == b"content-disposition":
                        header = Message()
                        header["Content-Disposition"] = value.decode("latin1")
                        filename = header.get_filename() or ""
                        if _UUID.search(filename):
                            name = download_name(filename, extension=PurePath(filename).suffix)
                            disposition = attachment_header(name)
                            if header.get_content_disposition() == "inline":
                                disposition = disposition.replace("attachment;", "inline;", 1)
                            value = disposition.encode("latin1")
                    headers.append((key, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, normalized_send)
