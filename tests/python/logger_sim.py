REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Symulator loggera Solarman: serwer TCP z protokołem V5 (transport „tcp”) albo Modbus TCP, z pamięcią rejestrów.

Służy tylko do testów: sprawdza, że prawdziwy kod klienta (ha-solarman / pysolarman) i nasza warstwa nad nim
dobrze kodują zapytania, czytają odpowiedzi i zapisują rejestry. Nie dowodzi zgodności z prawdziwym sprzętem.
"""
import asyncio, struct, sys
sys.path.insert(0, REPO + "")
from custom_components.bms_komp_dec.direct.pysolarman.umodbus.client.serial.redundancy_check import get_crc


class LoggerSim:
    def __init__(self, serial=2712345678, slave=1, mode="v5"):
        self.serial, self.slave, self.mode = serial, slave, mode
        self.regs = {}                 # adres -> wartość 16-bit (te same dla funkcji 3 i 4)
        self.rejected = set()          # rejestry, których zapis falownik „ignoruje” (nie zmienia wartości)
        self.illegal = set()           # adresy zwracające wyjątek 2 (illegal data address)
        self.log = []                  # (fc, addr, qty/values)
        self.mangle = None             # funkcja(odpowiedź) -> bajty do wysłania zamiast niej (testy odporności)
        self.connections = 0
        self.server = None
        self.port = None
        self.drop_next = 0             # tyle najbliższych zapytań zostanie zignorowanych (brak odpowiedzi)

    async def start(self):
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    # ---- Modbus (PDU: fc + dane) ----
    def _pdu(self, fc, body):
        if fc in (3, 4):
            addr, qty = struct.unpack(">HH", body[:4])
            self.log.append((fc, addr, qty))
            if any(a in self.illegal for a in range(addr, addr + qty)):
                return bytes([fc | 0x80, 2])
            vals = [self.regs.get(a, 0) for a in range(addr, addr + qty)]
            return bytes([fc, qty * 2]) + b"".join(struct.pack(">H", v) for v in vals)
        if fc == 6:
            addr, val = struct.unpack(">HH", body[:4])
            self.log.append((fc, addr, [val]))
            if addr not in self.rejected:
                self.regs[addr] = val
            return bytes([fc]) + body[:4]
        if fc == 16:
            addr, qty, bc = struct.unpack(">HHB", body[:5])
            vals = list(struct.unpack(">" + "H" * qty, body[5:5 + bc]))
            self.log.append((fc, addr, vals))
            for i, v in enumerate(vals):
                if addr + i not in self.rejected:
                    self.regs[addr + i] = v
            return bytes([fc]) + body[:4]
        return bytes([fc | 0x80, 1])

    async def _client(self, reader, writer):
        self.connections += 1
        try:
            while True:
                data = await reader.read(2048)
                if not data:
                    break
                if self.drop_next > 0:
                    self.drop_next -= 1
                    continue
                resp = self._v5(data) if self.mode == "v5" else self._tcp(data)
                if self.mangle is not None:            # złośliwy / uszkodzony logger: podmiana odpowiedzi
                    resp = self.mangle(resp)
                if resp:
                    writer.write(resp); await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    def _v5(self, data):
        assert data[0] == 0xA5 and data[-1] == 0x15, data.hex(" ")
        length = struct.unpack("<H", data[1:3])[0]
        assert length == len(data) - 13, (length, len(data))
        assert data[4] == 0x45, data.hex(" ")            # control code REQUEST
        seq = data[5:7]
        assert (sum(data[1:-2]) & 0xFF) == data[-2], "checksum zapytania"
        rtu = data[26:-2]                               # 11 nagłówek + 1 typ ramki + 2 typ czujnika + 12 czasów
        slave, fc, body, crc = rtu[0], rtu[1], rtu[2:-2], rtu[-2:]
        assert get_crc(rtu[:-2]) == crc, "crc modbus zapytania"
        pdu = self._pdu(fc, body)
        radu = bytes([slave]) + pdu
        radu += get_crc(radu)
        hdr = bytes([0xA5]) + struct.pack("<H", 14 + len(radu)) + b"\x10\x15" + seq[:1] + b"\x01" + struct.pack("<I", self.serial)
        payload = b"\x02\x01" + struct.pack("<III", 1, 2, 3) + radu
        frame = hdr + payload
        return frame + bytes([sum(frame[1:]) & 0xFF, 0x15])

    def _tcp(self, data):
        tid, pid, ln, unit = struct.unpack(">HHHB", data[:7])
        pdu = self._pdu(data[7], data[8:])
        return struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit) + pdu
