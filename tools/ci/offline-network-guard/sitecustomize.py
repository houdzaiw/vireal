"""Loaded only by the disposable local regression process, never production."""

import socket
import sys


def reject_tcp(event, args):
    if event == "socket.connect" and args[0].family in (
        socket.AF_INET,
        socket.AF_INET6,
    ):
        raise RuntimeError("TCP is forbidden in isolated prelaunch regression")


sys.addaudithook(reject_tcp)

import httpx  # noqa: E402


def reject_http(*_args, **_kwargs):
    raise RuntimeError(
        "Real HTTP transport is forbidden in isolated prelaunch regression"
    )


httpx.HTTPTransport.handle_request = reject_http
httpx.AsyncHTTPTransport.handle_async_request = reject_http
