"""Dokleja do instrukcji PDF dodatek „Zmiany od wersji 0.9.4” (strony od 15).

Użycie:  python3 docs/build_dodatek.py
Skrypt bierze pierwsze BASE_PAGES stron istniejącej instrukcji i dopisuje dodatek — można go uruchamiać wielokrotnie.
Wymaga: reportlab, pypdf, czcionki DejaVu Sans.
"""
from __future__ import annotations

import io
import os

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, "Instrukcja_EMS_komp-dec.pdf")
BASE_PAGES = 14
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
GREEN = colors.HexColor("#0b6e4f")
HEAD_BG = colors.HexColor("#e3f3ec")
LINE = colors.HexColor("#cfd8d4")
TEXT = colors.HexColor("#1c2422")
MUTED = colors.HexColor("#5b6763")

pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))

H1 = ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=17, leading=22, textColor=GREEN, spaceAfter=8)
H2 = ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=11.5, leading=15, textColor=GREEN, spaceBefore=10, spaceAfter=4)
P = ParagraphStyle("p", fontName="DejaVu", fontSize=9.5, leading=14, textColor=TEXT, spaceAfter=5)
CELL = ParagraphStyle("cell", fontName="DejaVu", fontSize=8.8, leading=12.5, textColor=TEXT)
CELL_B = ParagraphStyle("cellb", parent=CELL, fontName="DejaVu-Bold")
NOTE = ParagraphStyle("note", parent=P, fontSize=8.8, leading=12.5, textColor=MUTED)


def table(head, rows, widths):
    data = [[Paragraph(h, CELL_B) for h in head]] + [[Paragraph(r[0], CELL_B)] + [Paragraph(c, CELL) for c in r[1:]] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
    canvas.setFont("DejaVu", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 10.5 * mm, "EMS komp-dec · instrukcja użytkownika")
    canvas.drawRightString(A4[0] - 20 * mm, 10.5 * mm, f"strona {BASE_PAGES + doc.page}")
    canvas.restoreState()


def story():
    s = []
    s.append(Paragraph("15. Dodatek: zmiany od wersji 0.9.4", H1))
    s.append(Paragraph("Ten dodatek opisuje funkcje dodane po przygotowaniu instrukcji. Tam, gdzie zmienia wcześniejszy rozdział, "
                       "jest to zaznaczone.", P))

    s.append(Paragraph("15.1. Zakaz „ładuj z sieci → sprzedaj” (uzupełnia rozdział 8)", H2))
    s.append(Paragraph("EMS prowadzi licznik energii naładowanej z sieci, która nadal jest w baterii. Licznik rośnie, gdy bateria "
                       "ładuje się przy poborze z sieci, i maleje, gdy bateria zasila dom. Rozładowanie do sieci go nie zmniejsza. "
                       "Dopóki licznik jest powyżej tolerancji, sprzedaż z baterii jest zablokowana: z harmonogramu, ręcznie i w trakcie.", P))
    s.append(table(["Blokada", "Działanie", "Gdzie"], [
        ["Energia z sieci w baterii", "Wstrzymuje sprzedaż, dopóki dom nie zużyje energii naładowanej z sieci. Tolerancja jest wspólna "
                                      "z bilansem dwudniowym (domyślnie 0,5 kWh). 0 wyłącza obie blokady.", "Ustawienia EMS: „Blokada arbitrażu — tolerancja”"],
        ["Plan", "Plan nie proponuje sprzedaży na godzinę, o której w baterii byłaby jeszcze energia z planowanego ładowania z sieci.", "Zakładka EMS, powód przy propozycji"],
    ], [38, 92, 40]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Na ekranie głównym pojawia się znacznik „W baterii ~X kWh energii z sieci”. Czerwony oznacza, że sprzedaż jest "
                       "zablokowana. Powiadomienie „Okno arbitrażu jutro” z rozdziału 10 zostało usunięte.", P))

    s.append(Paragraph("15.2. Zestawy: włączanie, wyłączanie, zerowanie", H2))
    s.append(table(["Sytuacja", "Co robi EMS"], [
        ["Plan przewiduje okno, zestaw jest wyłączony", "Przy włączonym auto-stosowaniu EMS sam włącza przełącznik zestawu — także wtedy, gdy godzin "
                                                        "nie trzeba zmieniać. Zestawu sprzedaży nie włącza, gdy obowiązuje zakaz sprzedaży."],
        ["Plan nie przewiduje sprzedaży", "Wyłącza zestaw sprzedaży i ustawia Stop = Start (puste okno). Gdy plan znów zaproponuje sprzedaż, "
                                          "godziny i zestaw wracają. „Cofnij” przywraca poprzednie godziny."],
        ["Zestaw wyłączony albo okno puste", "Godziny w zakładce EMS są przygaszone z dopiskiem „nieaktywne”."],
        ["Chcesz włączać zestawy ręcznie", "Wyłącz przełącznik „Auto-włączanie zestawów” (Diagnostyka → Tryby). Wtedy 90 minut przed oknem "
                                           "z planu przyjdzie powiadomienie „Zestaw potrzebny w planie jest wyłączony”."],
    ], [55, 115]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Godzina 00:00 oznacza „nie ustawiono” — okno z taką godziną nie zadziała. Dla północy wpisz 23:59 (koniec) "
                       "albo 00:01 (start). Karta ostrzega o tym przy zapisie.", P))

    s.append(Paragraph("15.3. Auto-stosowanie w ciągu doby (uzupełnia rozdział 5)", H2))
    s.append(Paragraph("Auto-stosowanie działa codziennie o 16:00 dla wszystkich propozycji. Dodatkowo zmiany okien ładowania z sieci "
                       "(noc i zestaw 2) są stosowane w ciągu doby z planu liczonego na bieżąco, pod warunkami:", P))
    s.append(table(["Warunek", "Wartość"], [
        ["Propozycja bez zmian", "co najmniej 30 minut (plan potrafi zmieniać zdanie, np. 11:00 ↔ 12:00)"],
        ["Odstęp między zmianami", "co najmniej 1 godzina"],
        ["Okno startuje za chwilę", "mniej niż 10 minut do startu — bez zmian"],
        ["Pozostałe zabezpieczenia", "trwa ładowanie lub sprzedaż, limit przesunięcia, odrzucone propozycje, niska pewność, tryb „tylko podgląd”"],
    ], [55, 115]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Sprzedaż z baterii zmienia się tylko w propozycji dziennej. Przy każdej propozycji karta pokazuje szacowany "
                       "zysk w złotych, a propozycje bez realnej wartości są ukrywane.", P))

    s.append(Paragraph("15.4. Awaryjny STOP", H2))
    s.append(Paragraph("Reguły harmonogramu działają w dokładnej minucie. Jeżeli okno wystartowało z harmonogramu, a jego STOP nie "
                       "zadziałał (restart Home Assistanta, przeładowanie integracji), EMS kończy ładowanie z sieci albo sprzedaż "
                       "po czasie i wysyła powiadomienie. Nie dotyczy to startów ręcznych ani przełącznika „Wymuś ładowanie”.", P))

    s.append(Paragraph("15.5. Prognoza PV", H2))
    s.append(table(["Element", "Opis"], [
        ["Suma dnia", "Liczona z prognozy godzinowej Solcast w wariancie środkowym (estimate), niezależnie od ustawień encji. "
                      "Zakres pod wartością to warianty pesymistyczny i optymistyczny."],
        ["Ostrzeżenie o wariancie", "Diagnostyka → Zaawansowane → „Prognoza PV” ostrzega, gdy encja Solcast pokazuje wariant "
                                    "pesymistyczny (estimate10) albo optymistyczny (estimate90)."],
        ["Porównanie źródeł", "Ta sama karta pokazuje prognozę Solcast i Forecast.Solar na dziś i jutro, jeśli obie integracje są zainstalowane."],
        ["Wyzeruj naukę korekty PV", "Kasuje zapamiętane prognozy, z których liczona jest korekta. Użyj po zmianie ustawień źródła prognozy — "
                                     "inaczej stara korekta zniekształca nową prognozę. Korekta uczy się od nowa około 5 dni."],
    ], [45, 125]))

    s.append(Paragraph("15.6. Podsumowania i dziennik", H2))
    s.append(Paragraph("Podsumowanie dnia zawiera dodatkowo plan kontra wykonanie: prognozę PV i produkcję, plan i wykonanie sprzedaży "
                       "z baterii oraz liczbę zadziałań zabezpieczeń i automatu. Zakładka „Zysk” ma sekcję „Co EMS zrobił dziś” "
                       "z najważniejszymi zdarzeniami dnia. Po północy dziennik dostaje wpis: plan sprzedaży a faktyczny eksport.", P))

    s.append(Paragraph("15.7. Pasek zakładek", H2))
    s.append(Paragraph("Pasek zakładek jest przyklejony do dołu ekranu. Przełącznik „Pasek zakładek na górze” (Diagnostyka → Tryby) "
                       "przywraca poprzedni układ u wszystkich użytkowników.", P))
    s.append(Spacer(1, 6))
    s.append(Paragraph("Wszystkie opisane funkcje były sprawdzane w środowisku testowym. Po aktualizacji obserwuj dziennik decyzji "
                       "przez pierwsze dni.", NOTE))
    return s


def main() -> None:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=22 * mm,
                            title="EMS komp-dec — instrukcja użytkownika", author="Komp-Dec")
    doc.build(story(), onFirstPage=footer, onLaterPages=footer)
    base = PdfReader(PDF)
    out = PdfWriter()
    for page in base.pages[:BASE_PAGES]:
        out.add_page(page)
    extra = PdfReader(io.BytesIO(buf.getvalue()))
    for page in extra.pages:
        out.add_page(page)
    out.add_metadata({"/Title": "EMS komp-dec — instrukcja użytkownika", "/Author": "Komp-Dec"})
    tmp = PDF + ".tmp"
    with open(tmp, "wb") as fh:
        out.write(fh)
    os.replace(tmp, PDF)
    print(f"OK: {BASE_PAGES} stron instrukcji + {len(extra.pages)} stron dodatku")


if __name__ == "__main__":
    main()
