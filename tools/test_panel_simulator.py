"""Tests for the supplied simulator, not for the candidate's application."""
import contextlib
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

from panel_simulator import (
    CONFLICT_EVENT, EVENT, FRAME_TIMEOUT, SCENARIOS, SECOND_EVENT,
    Server, frame, receive, receive_exact,
)


@contextlib.contextmanager
def running(scenario, response_timeout=1.0):
    server = Server(("127.0.0.1", 0), scenario=scenario, response_timeout=response_timeout)
    reports = queue.Queue()
    server.report = lambda peer, status, message: reports.put((status, message))
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield server, reports
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if thread.is_alive():
            raise AssertionError("Simulator listener did not stop")


@contextlib.contextmanager
def connection(scenario, response_timeout=1.0):
    with running(scenario, response_timeout) as (server, reports):
        with socket.create_connection(server.server_address, timeout=5) as client:
            yield client, reports


def result(reports, expected, timeout=5):
    deadline = time.monotonic() + timeout
    while True:
        status, message = reports.get(timeout=max(0.001, deadline - time.monotonic()))
        if status == expected:
            return message
        if status == "FAIL":
            raise AssertionError("Unexpected simulator failure: " + message)


class SimulatorTest(unittest.TestCase):
    def test_reference_frame(self):
        self.assertEqual(frame("A|1|OK").hex(), "53500006417c317c4f4b04")

    def test_frame_length_limits(self):
        for length in (1, 256):
            self.assertEqual(len(frame("X" * length)), length + 5)
        for length in (0, 257):
            with self.assertRaises(ValueError):
                frame("X" * length)
        with self.assertRaises(UnicodeEncodeError):
            frame("\u0105")

    def test_events_and_acknowledgements(self):
        second = {"coalesced": SECOND_EVENT, "duplicate": EVENT}
        for scenario in ("normal", "fragmented", "coalesced", "duplicate"):
            with self.subTest(scenario=scenario), connection(scenario) as (client, reports):
                self.assertEqual(receive(client), EVENT)
                if scenario in second:
                    self.assertEqual(receive(client), second[scenario])
                replies = ["A|1|OK"]
                if scenario in second:
                    replies.append("A|2|OK" if scenario == "coalesced" else "A|1|OK")
                client.sendall(b"".join(frame(body) for body in replies))
                result(reports, "PASS")

    def test_coalesced_acknowledgements_may_arrive_in_reverse_order(self):
        with connection("coalesced") as (client, reports):
            receive(client)
            receive(client)
            client.sendall(frame("A|2|OK") + frame("A|1|OK"))
            result(reports, "PASS")

    def test_conflict_then_original_event(self):
        with connection("conflict") as (client, reports):
            for event, ack in ((EVENT, "A|1|OK"), (CONFLICT_EVENT, "A|1|CONFLICT"),
                               (EVENT, "A|1|OK")):
                self.assertEqual(receive(client), event)
                client.sendall(frame(ack))
            result(reports, "PASS")

    def test_wrong_ok_for_conflict_fails(self):
        with connection("conflict") as (client, reports):
            receive(client)
            client.sendall(frame("A|1|OK"))
            self.assertEqual(receive(client), CONFLICT_EVENT)
            client.sendall(frame("A|1|OK"))
            self.assertIn("CONFLICT", result(reports, "FAIL"))
            self.assertEqual(client.recv(1), b"")

    def test_unexpected_ack_contents_fail(self):
        for body in ("A|999|OK", "A|1|CONFLICT", "A|01|OK", "A|1|OK|extra",
                     "C|request|device-17|STATUS"):
            with self.subTest(body=body), connection("normal") as (client, reports):
                receive(client)
                client.sendall(frame(body))
                self.assertIn("Unexpected ACK", result(reports, "FAIL"))

    def test_malformed_ack_frames_fail(self):
        good = frame("A|1|OK")
        non_ascii = b"A|1|\x80"
        cases = (
            good[:-1] + bytes([good[-1] ^ 1]),
            b"XX" + good[2:],
            b"SP\x00\x00",
            b"SP\x01\x01",
            b"SP" + len(non_ascii).to_bytes(2, "big") + non_ascii + bytes([sum(non_ascii) % 256]),
        )
        for data in cases:
            with self.subTest(data=data), connection("normal") as (client, reports):
                receive(client)
                client.sendall(data)
                result(reports, "FAIL")

    def test_missing_ack_fails(self):
        with connection("normal", response_timeout=0.1) as (client, reports):
            receive(client)
            self.assertIn("deadline exceeded", result(reports, "FAIL"))
            self.assertEqual(client.recv(1), b"")

    def test_missing_second_duplicate_ack_fails(self):
        with connection("duplicate", response_timeout=0.1) as (client, reports):
            receive(client)
            receive(client)
            client.sendall(frame("A|1|OK"))
            result(reports, "FAIL")

    def test_incomplete_ack_followed_by_eof_fails(self):
        with connection("normal") as (client, reports):
            receive(client)
            client.sendall(frame("A|1|OK")[:-1])
            client.shutdown(socket.SHUT_WR)
            self.assertIn("complete response", result(reports, "FAIL"))

    def test_extra_ack_fails(self):
        with connection("normal") as (client, reports):
            receive(client)
            client.sendall(frame("A|1|OK") * 2)
            result(reports, "PASS")
            self.assertIn("Unexpected data", result(reports, "FAIL"))

    def test_receive_uses_one_deadline_for_the_whole_ack(self):
        sock = Mock()
        sock.gettimeout.return_value = 5.0
        sock.recv.side_effect = [b"S", b"P", b"\x00\x06", b"A|1|OK", b"\x04"]
        with patch("panel_simulator.time.monotonic", side_effect=[10, 10, 10.05, 10.1, 10.15, 10.2]):
            self.assertEqual(receive(sock, timeout=0.3), "A|1|OK")
        timeouts = [call.args[0] for call in sock.settimeout.call_args_list]
        for actual, expected in zip(timeouts, (0.3, 0.25, 0.2, 0.15, 0.1, 5.0)):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(len(timeouts), 6)

    def test_receive_deadline_expiry_restores_socket_timeout(self):
        sock = Mock()
        sock.gettimeout.return_value = None
        sock.recv.return_value = b"S"
        with patch("panel_simulator.time.monotonic", side_effect=[10, 10.1, 10.31]):
            with self.assertRaises(socket.timeout):
                receive(sock, timeout=0.3)
        sock.settimeout.assert_called_with(None)

    def test_invalid_events_require_close_without_ack(self):
        for scenario in ("bad-checksum", "bad-length", "truncated"):
            with self.subTest(scenario=scenario), connection(scenario) as (client, reports):
                with self.assertRaises((ValueError, EOFError)):
                    receive(client)
                client.close()
                result(reports, "PASS")

    def test_ack_for_invalid_event_fails(self):
        for scenario in ("bad-checksum", "bad-length", "truncated"):
            with self.subTest(scenario=scenario), connection(scenario) as (client, reports):
                with self.assertRaises((ValueError, EOFError)):
                    receive(client)
                client.sendall(frame("A|1|OK"))
                self.assertIn("without an ACK", result(reports, "FAIL"))

    def test_invalid_event_without_disconnect_fails(self):
        with connection("bad-length", response_timeout=0.1) as (client, reports):
            with self.assertRaises(ValueError):
                receive(client)
            result(reports, "FAIL")

    def test_frame_timeout_accepts_close_after_three_seconds(self):
        with connection("frame-timeout") as (client, reports):
            self.assertEqual(receive_exact(client, len(frame(EVENT)) - 1), frame(EVENT)[:-1])
            time.sleep(FRAME_TIMEOUT)
            client.close()
            result(reports, "PASS")

    def test_frame_timeout_rejects_early_close(self):
        with connection("frame-timeout") as (client, reports):
            receive_exact(client, len(frame(EVENT)) - 1)
            client.close()
            self.assertIn("before its 3-second deadline", result(reports, "FAIL"))

    def test_frame_timeout_rejects_client_that_keeps_waiting(self):
        with connection("frame-timeout") as (client, reports):
            receive_exact(client, len(frame(EVENT)) - 1)
            result(reports, "FAIL", timeout=5)

    def test_disconnect_happens_only_after_ack(self):
        with connection("disconnect") as (client, reports):
            self.assertEqual(receive(client), EVENT)
            client.settimeout(0.1)
            with self.assertRaises(socket.timeout):
                client.recv(1)
            client.settimeout(5)
            client.sendall(frame("A|1|OK"))
            self.assertEqual(client.recv(1), b"")
            result(reports, "PASS")

    def test_ack_loss_repeats_event_on_next_connection(self):
        with running("ack-loss") as (server, reports):
            with socket.create_connection(server.server_address, timeout=5) as client:
                self.assertEqual(receive(client), EVENT)
                client.sendall(frame("A|1|OK"))
                self.assertEqual(client.recv(1), b"")
                self.assertTrue(server._ack_discarded)
            with socket.create_connection(server.server_address, timeout=5) as client:
                self.assertEqual(receive(client), EVENT)
                client.sendall(frame("A|1|OK"))
                result(reports, "PASS")

    def test_invalid_ack_does_not_consume_ack_loss_step(self):
        with running("ack-loss") as (server, reports):
            with socket.create_connection(server.server_address, timeout=5) as client:
                receive(client)
                client.sendall(frame("A|2|OK"))
                result(reports, "FAIL")
            self.assertFalse(server._ack_discarded)
            with socket.create_connection(server.server_address, timeout=5) as client:
                receive(client)
                client.sendall(frame("A|1|OK"))
                self.assertEqual(client.recv(1), b"")
                self.assertTrue(server._ack_discarded)

    def test_normal_has_no_idle_disconnect_after_ack(self):
        with connection("normal", response_timeout=0.1) as (client, reports):
            receive(client)
            client.sendall(frame("A|1|OK"))
            result(reports, "PASS")
            client.settimeout(0.3)
            with self.assertRaises(socket.timeout):
                client.recv(1)

    def test_server_stop_closes_waiting_and_idle_connections(self):
        for acknowledge in (False, True):
            with self.subTest(acknowledge=acknowledge):
                client = None
                try:
                    with running("normal") as (server, reports):
                        client = socket.create_connection(server.server_address, timeout=5)
                        receive(client)
                        if acknowledge:
                            client.sendall(frame("A|1|OK"))
                            result(reports, "PASS")
                    self.assertEqual(client.recv(1), b"")
                    self.assertFalse(server._connections)
                finally:
                    if client is not None:
                        client.close()

    def test_cli_help_lists_only_assignment_scenarios(self):
        process = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("panel_simulator.py")), "--help"],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(process.returncode, 0)
        for scenario in SCENARIOS:
            self.assertIn(scenario, process.stdout)
        self.assertNotIn("late-response", process.stdout)

    def test_cli_rejects_invalid_limits(self):
        for option, value in (("--response-timeout", "0"), ("--response-timeout", "-1"),
                              ("--response-timeout", "nan"), ("--response-timeout", "inf"),
                              ("--port", "0"), ("--port", "65536")):
            with self.subTest(option=option, value=value):
                process = subprocess.run(
                    [sys.executable, str(Path(__file__).with_name("panel_simulator.py")), option, value],
                    capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(process.returncode, 2)


if __name__ == "__main__":
    unittest.main()
