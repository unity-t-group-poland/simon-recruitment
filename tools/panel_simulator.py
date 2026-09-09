"""Fictional SP/1 panel and TCP scenario checks. Python 3.9+, standard library only."""
import argparse
from collections import Counter
import math
import socket
import socketserver
import threading
import time


SCENARIOS = (
    "normal", "fragmented", "coalesced", "duplicate", "conflict",
    "bad-checksum", "bad-length", "truncated", "frame-timeout",
    "disconnect", "ack-loss",
)
EVENT = "E|1|device-17|ALARM|1789380900"
SECOND_EVENT = "E|2|device-17|RESTORE|1789380901"
CONFLICT_EVENT = "E|1|device-17|TEST|1789380900"
FRAME_TIMEOUT = 3.0
CLOSE_GRACE = 1.0


def frame(body):
    data = body.encode("ascii")
    if not 1 <= len(data) <= 256:
        raise ValueError("Invalid body length")
    return b"SP" + len(data).to_bytes(2, "big") + data + bytes([sum(data) % 256])


def receive_exact(sock, length, deadline=None, stop_event=None):
    result = bytearray()
    while len(result) < length:
        if stop_event is not None and stop_event.is_set():
            raise ConnectionAbortedError("Simulator stopped")
        remaining = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("Response deadline exceeded")
        if stop_event is not None:
            # Bounded waits let Ctrl+C stop active sessions on Windows as well as Linux.
            sock.settimeout(0.2 if remaining is None else min(0.2, remaining))
        elif remaining is not None:
            sock.settimeout(remaining)
        try:
            chunk = sock.recv(length - len(result))
        except socket.timeout:
            if stop_event is None:
                raise
            continue
        if not chunk:
            raise EOFError("Connection closed before the complete response")
        result.extend(chunk)
    return bytes(result)


def receive(sock, timeout=None, stop_event=None):
    previous_timeout = sock.gettimeout()
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        header = receive_exact(sock, 4, deadline, stop_event)
        length = int.from_bytes(header[2:], "big")
        if header[:2] != b"SP" or not 1 <= length <= 256:
            raise ValueError("Invalid frame header")
        body = receive_exact(sock, length, deadline, stop_event)
        if receive_exact(sock, 1, deadline, stop_event)[0] != sum(body) % 256:
            raise ValueError("Invalid checksum")
        return body.decode("ascii")
    finally:
        sock.settimeout(previous_timeout)


class Panel(socketserver.BaseRequestHandler):
    def report(self, status, message):
        self.server.report(self.client_address, status, message)

    def send_event(self, body):
        self.report("TX", body)
        self.request.sendall(frame(body))

    def expect_acks(self, *expected):
        pending = Counter(expected)
        for _ in expected:
            body = receive(self.request, self.server.response_timeout, self.server.stopping)
            self.report("RX", body)
            if pending[body] == 0:
                raise ValueError("Unexpected ACK %r; expected %r" % (body, list(pending.elements())))
            pending[body] -= 1

    def expect_close(self, timeout, started=None, earliest=0):
        try:
            data = receive_exact(self.request, 1, time.monotonic() + timeout, self.server.stopping)
        except (EOFError, ConnectionResetError):
            data = b""
        if data:
            raise ValueError("Expected connection close without an ACK, received data")
        if started is not None and time.monotonic() - started < earliest:
            raise ValueError("Client closed an incomplete frame before its 3-second deadline")
        self.report("PASS", "Client closed without an ACK; verify unchanged database separately")

    def wait_for_disconnect(self):
        self.request.settimeout(None)
        self.report("PASS", "Expected ACKs received; connection stays open; verify database and API separately")
        try:
            extra = receive_exact(self.request, 1, stop_event=self.server.stopping)
        except (EOFError, ConnectionResetError):
            extra = b""
        if extra:
            raise ValueError("Unexpected data after all expected ACKs")
        self.report("INFO", "Client disconnected")

    def handle(self):
        scenario = self.server.scenario
        event = frame(EVENT)
        self.report("INFO", "Connected; scenario=" + scenario)
        try:
            if scenario in ("bad-checksum", "bad-length", "truncated", "frame-timeout"):
                self.report("TX", "Invalid or incomplete frame: " + scenario)
                if scenario == "bad-checksum":
                    self.request.sendall(event[:-1] + bytes([event[-1] ^ 1]))
                elif scenario == "bad-length":
                    self.request.sendall(b"SP\x01\x01")
                elif scenario == "truncated":
                    self.request.sendall(event[:-2])
                    self.request.shutdown(socket.SHUT_WR)
                else:
                    started = time.monotonic()
                    self.request.sendall(event[:-1])
                    self.expect_close(FRAME_TIMEOUT + CLOSE_GRACE, started, FRAME_TIMEOUT - 0.1)
                    return
                self.expect_close(self.server.response_timeout)
                return

            if scenario == "fragmented":
                self.report("TX", EVENT + " (one byte per write)")
                for byte in event:
                    self.request.sendall(bytes([byte]))
                    time.sleep(0.01)
                self.expect_acks("A|1|OK")
            elif scenario == "coalesced":
                self.report("TX", EVENT + " + " + SECOND_EVENT + " (one write)")
                self.request.sendall(event + frame(SECOND_EVENT))
                self.expect_acks("A|1|OK", "A|2|OK")
            elif scenario == "duplicate":
                self.report("TX", EVENT + " (twice in one write)")
                self.request.sendall(event + event)
                self.expect_acks("A|1|OK", "A|1|OK")
            elif scenario == "conflict":
                # Confirm the original before sending a conflicting version of the same event.
                self.send_event(EVENT)
                self.expect_acks("A|1|OK")
                self.send_event(CONFLICT_EVENT)
                self.expect_acks("A|1|CONFLICT")
                self.send_event(EVENT)
                self.expect_acks("A|1|OK")
            else:
                self.send_event(EVENT)
                self.expect_acks("A|1|OK")
                if scenario == "disconnect":
                    self.report("PASS", "OK received; panel closes the connection now")
                    return
                if scenario == "ack-loss" and self.server.discard_ack_once():
                    self.report("INFO", "First ACK deliberately ignored; closing. Restart/reconnect the client with the same sourceId and database; keep this simulator running")
                    return

            self.wait_for_disconnect()
        except (EOFError, OSError, ValueError) as error:
            if not self.server.stopping.is_set():
                self.report("FAIL", str(error))


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = False

    def __init__(self, address, handler=Panel, *, scenario="normal", response_timeout=10.0):
        self.scenario = scenario
        self.response_timeout = response_timeout
        self.stopping = threading.Event()
        self._lock = threading.Lock()
        self._connections = set()
        self._ack_discarded = False
        super().__init__(address, handler)

    def report(self, peer, status, message):
        print("[%s] %s:%s %s" % (status, peer[0], peer[1], message), flush=True)

    def discard_ack_once(self):
        with self._lock:
            if self._ack_discarded:
                return False
            self._ack_discarded = True
            return True

    def process_request(self, request, client_address):
        with self._lock:
            self._connections.add(request)
        super().process_request(request, client_address)

    def shutdown_request(self, request):
        super().shutdown_request(request)
        with self._lock:
            self._connections.discard(request)

    def server_close(self):
        self.stopping.set()
        with self._lock:
            connections = tuple(self._connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        super().server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19090)
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--response-timeout", type=float, default=10.0,
                        help="Tool wait limit for an ACK or error disconnect, in seconds (default: 10); not an idle timeout")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not math.isfinite(args.response_timeout) or args.response_timeout <= 0:
        parser.error("--response-timeout must be a positive finite number")
    with Server((args.host, args.port), scenario=args.scenario,
                response_timeout=args.response_timeout) as server:
        print("SP/1 listening on", server.server_address, args.scenario, flush=True)
        print("PASS/FAIL checks TCP only, not database persistence or REST. Stop with Ctrl+C.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
