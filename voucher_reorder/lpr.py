"""Bounded, loopback-only RFC 1179 receive-job subset for Windows TCP/IP monitor."""
import os
from pathlib import Path
import socketserver
import tempfile

MAX_JOB = 100 * 1024 * 1024


def line(stream):
    value = stream.readline(1025)
    if not value.endswith(b"\n") or len(value) > 1024:
        raise ValueError("Invalid command line")
    return value[:-1]


def receive(stream, ack, spool: Path, accept):
    # Never use the untrusted job name, host name, or user name as a filesystem path.
    if line(stream) != b"\x02voucher":
        raise ValueError("Unknown command or queue")
    ack(b"\0")
    seen = set()
    data_path = None
    try:
        for _ in range(2):
            command = line(stream)
            kind = command[:1]
            if kind not in (b"\x02", b"\x03") or kind in seen:
                raise ValueError("Expected one control file and one data file")
            size_text, name = command[1:].split(b" ", 1)
            if not size_text.isdigit() or not name:
                raise ValueError("Invalid file header")
            size = int(size_text)
            if not 0 < size <= (65536 if kind == b"\x02" else MAX_JOB):
                raise ValueError("Print job is too large or empty")
            ack(b"\0")
            if kind == b"\x03":
                fd, temp = tempfile.mkstemp(prefix="receiving-", suffix=".ps", dir=spool)
                data_path = Path(temp)
                output = os.fdopen(fd, "wb")
            else:
                output = None
            try:
                remaining = size
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError("Truncated print job")
                    if output:
                        output.write(chunk)
                    remaining -= len(chunk)
                if output:
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                if output:
                    output.close()
            if stream.read(1) != b"\0":
                raise ValueError("Invalid file terminator")
            seen.add(kind)
            if len(seen) == 2:
                accept(data_path)  # durable commit BEFORE final ACK
            ack(b"\0")
    finally:
        if data_path:
            data_path.unlink(missing_ok=True)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(60)
        try:
            receive(self.rfile, self.request.sendall, self.server.spool, self.server.accept_job)
        except (OSError, ValueError):
            try:
                self.request.sendall(b"\x01")
            except OSError:
                pass


class Server(socketserver.TCPServer):
    # Serial receipt is intentional: bounded resource usage and ordered jobs.
    allow_reuse_address = False

    def __init__(self, address, spool, accept):
        if address[0] != "127.0.0.1":
            raise ValueError("Only loopback binding is permitted")
        self.spool, self.accept_job = spool, accept
        super().__init__(address, Handler)
