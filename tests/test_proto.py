import unittest

from scanner_service.proto import bytes_field, double, double_field, fields, int_field, one, packed_ints, text, varint


class ProtoTests(unittest.TestCase):
    def test_scalar_and_bytes_roundtrip(self):
        message = int_field(1, 300) + bytes_field(2, "hello") + double_field(3, 12.5)
        decoded = fields(message)
        self.assertEqual(one(decoded, 1), 300)
        self.assertEqual(text(decoded, 2), "hello")
        self.assertEqual(double(decoded, 3), 12.5)

    def test_packed_ints(self):
        packed = bytes_field(1, varint(4) + varint(900))
        self.assertEqual(packed_ints(fields(packed), 1), [4, 900])

    def test_rejects_truncated_message(self):
        with self.assertRaises(ValueError):
            fields(b"\x0a\x04x")

    def test_rejects_zero_field(self):
        with self.assertRaises(ValueError):
            fields(b"\x00")


if __name__ == "__main__":
    unittest.main()
