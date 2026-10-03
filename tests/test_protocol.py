"""Framing tests — no Discord required."""

from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.core.errors import ProtocolError
from worthlesstask.rpc.protocol import (
    MAX_FRAME_BYTES,
    OP_FRAME,
    OP_HANDSHAKE,
    OP_PING,
    FrameDecoder,
    encode_frame,
    handshake_payload,
    op_name,
    set_activity_payload,
)


class TestEncoding(unittest.TestCase):
    def test_header_is_two_little_endian_int32(self):
        frame = encode_frame(OP_HANDSHAKE, {"v": 1, "client_id": "1"})
        op, length = struct.unpack("<II", frame[:8])
        self.assertEqual(op, OP_HANDSHAKE)
        self.assertEqual(length, len(frame) - 8)
        self.assertEqual(json.loads(frame[8:].decode()), {"v": 1, "client_id": "1"})

    def test_none_payload_becomes_empty_object(self):
        frame = encode_frame(OP_PING, None)
        self.assertEqual(frame[8:], b"{}")

    def test_oversized_payload_is_refused(self):
        with self.assertRaises(ProtocolError):
            encode_frame(OP_FRAME, {"x": "a" * (MAX_FRAME_BYTES + 1)})

    def test_op_name(self):
        self.assertEqual(op_name(OP_FRAME), "FRAME")
        self.assertEqual(op_name(99), "OP_99")


class TestDecoder(unittest.TestCase):
    def test_single_frame(self):
        decoder = FrameDecoder()
        frames = list(decoder.feed(encode_frame(OP_FRAME, {"cmd": "SET_ACTIVITY"})))
        self.assertEqual(frames, [(OP_FRAME, {"cmd": "SET_ACTIVITY"})])
        self.assertEqual(decoder.pending_bytes, 0)

    def test_split_across_chunks(self):
        """A pipe read can split anywhere — including inside the header."""
        blob = encode_frame(OP_FRAME, {"cmd": "SET_ACTIVITY", "nonce": "abc"})
        decoder = FrameDecoder()
        collected = []
        for index in range(len(blob)):
            collected.extend(decoder.feed(blob[index : index + 1]))
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0][1]["nonce"], "abc")

    def test_two_frames_in_one_chunk(self):
        decoder = FrameDecoder()
        blob = encode_frame(OP_PING, {"a": 1}) + encode_frame(OP_FRAME, {"b": 2})
        frames = list(decoder.feed(blob))
        self.assertEqual([op for op, _ in frames], [OP_PING, OP_FRAME])
        self.assertEqual(frames[1][1], {"b": 2})

    def test_empty_body_yields_none(self):
        decoder = FrameDecoder()
        frames = list(decoder.feed(struct.pack("<II", OP_PING, 0)))
        self.assertEqual(frames, [(OP_PING, None)])

    def test_oversized_length_is_rejected(self):
        decoder = FrameDecoder()
        with self.assertRaises(ProtocolError):
            list(decoder.feed(struct.pack("<II", OP_FRAME, MAX_FRAME_BYTES + 1)))

    def test_malformed_json_is_rejected(self):
        decoder = FrameDecoder()
        body = b"{not json"
        with self.assertRaises(ProtocolError):
            list(decoder.feed(struct.pack("<II", OP_FRAME, len(body)) + body))

    def test_partial_header_is_buffered(self):
        decoder = FrameDecoder()
        self.assertEqual(list(decoder.feed(b"\x01\x00\x00")), [])
        self.assertEqual(decoder.pending_bytes, 3)


class TestPayloads(unittest.TestCase):
    def test_handshake_payload_shape(self):
        self.assertEqual(handshake_payload("123"), {"v": 1, "client_id": "123"})

    def test_set_activity_payload_shape(self):
        payload = set_activity_payload(4321, {"details": "hi"}, "nonce-1")
        self.assertEqual(payload["cmd"], "SET_ACTIVITY")
        self.assertEqual(payload["args"]["pid"], 4321)
        self.assertEqual(payload["args"]["activity"], {"details": "hi"})
        self.assertEqual(payload["nonce"], "nonce-1")

    def test_set_activity_none_clears(self):
        self.assertIsNone(set_activity_payload(1, None, "n")["args"]["activity"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
