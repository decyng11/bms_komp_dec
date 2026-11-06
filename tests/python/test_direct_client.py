REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Prawdziwy klient Solarman V5 / Modbus TCP (przeniesiony z ha-solarman) kontra symulator loggera."""
import asyncio, sys
sys.path.insert(0, ".")
import direct_env; direct_env.install()
sys.path.insert(0, REPO + "")
from logger_sim import LoggerSim
from custom_components.bms_komp_dec.direct.pysolarman import Solarman
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)

async def main():
    # --- V5, numer seryjny nieznany: klient uczy się go z pierwszej odpowiedzi
    sim = await LoggerSim().start()
    sim.regs.update({0x0010: 1234, 0x0011: 5678, 0x0100: 65535})
    c = Solarman("127.0.0.1", sim.port, "tcp", 0, 1, 2)
    try:
        r = await c.execute(3, 0x0010, count=2)
        check("V5: odczyt 2 rejestrów (funkcja 3)", list(r) == [1234, 5678], r)
        check("V5: numer seryjny odczytany z odpowiedzi loggera", c.serial == 2712345678, c.serial)
        r = await c.execute(4, 0x0100, count=1)
        check("V5: odczyt rejestru wejściowego (funkcja 4)", list(r) == [65535], r)
        r = await c.execute(6, 0x0020, data=777)
        check("V5: zapis pojedynczego rejestru (funkcja 6)", sim.regs.get(0x0020) == 777, (r, sim.regs.get(0x0020)))
        r = await c.execute(16, 0x0030, data=[1, 2, 3])
        check("V5: zapis wielu rejestrów (funkcja 16)", [sim.regs.get(0x30), sim.regs.get(0x31), sim.regs.get(0x32)] == [1, 2, 3], sim.regs)
        sim.illegal.add(0x0500)
        try:
            await c.execute(3, 0x0500, count=1); raised = None
        except Exception as e:
            raised = type(e).__name__
        check("V5: wyjątek Modbus (zły adres) → błąd, nie śmieciowe dane", raised is not None, raised)
        r = await c.execute(3, 0x0010, count=1)
        check("V5: po wyjątku połączenie nadal działa", list(r) == [1234], r)
        check("V5: jedno połączenie TCP przez cały czas", sim.connections == 1, sim.connections)
        check("V5: zapytania wysłane z poprawnym adresem i liczbą", (3, 0x0010, 2) in sim.log and (16, 0x30, [1, 2, 3]) in sim.log, sim.log)
    finally:
        await c.close(); await sim.stop()

    # --- V5 z podanym numerem seryjnym
    sim = await LoggerSim(serial=2700000001).start(); sim.regs[1] = 42
    c = Solarman("127.0.0.1", sim.port, "tcp", 2700000001, 1, 2)
    try:
        r = await c.execute(3, 1, count=1)
        check("V5: znany numer seryjny → odczyt", list(r) == [42], r)
    finally:
        await c.close(); await sim.stop()

    # --- Modbus TCP
    sim = await LoggerSim(mode="tcp").start(); sim.regs.update({5: 11, 6: 22})
    c = Solarman("127.0.0.1", sim.port, "modbus_tcp", 0, 1, 2)
    try:
        r = await c.execute(3, 5, count=2)
        check("Modbus TCP: odczyt", list(r) == [11, 22], r)
        await c.execute(6, 7, data=99)
        check("Modbus TCP: zapis", sim.regs.get(7) == 99, sim.regs)
    finally:
        await c.close(); await sim.stop()
    print(f"DIRECT-CLIENT PASS={PASS} FAIL={FAIL}")
asyncio.run(main())
