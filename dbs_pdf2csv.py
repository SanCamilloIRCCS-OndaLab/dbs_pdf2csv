"""Estrae le tabelle triangolari delle impedenze (pagina 2) da un report DBS
Vercise Neural Navigator, insieme all'emisfero di ciascuna tabella."""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

# Etichette fisse delle tabelle triangolari delle impedenze
COLUMNS = ["case", "E8", "E7", "E6", "E5", "E4", "E3", "E2"]
ROWS = ["E8", "E7", "E6", "E5", "E4", "E3", "E2", "E1"]

ROW_TOL = 3  # tolleranza (pt) per considerare due parole sulla stessa riga
COL_TOL = 5  # tolleranza (pt) per allineare un valore alla colonna dell'header

MERGED_NAME = "dbs_merged.csv"  # CSV complessivo scritto nella cartella indicata


def group_rows(words):
    """Raggruppa le parole per riga in base alla coordinata 'top'."""
    rows = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= ROW_TOL:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def extract_visit_date(page):
    """Testo a destra di "Visit Date" sulla stessa riga."""
    words = page.extract_words(keep_blank_chars=True)
    label = next(w for w in words if w["text"].strip() == "Visit Date")
    return " ".join(w["text"].strip() for w in sorted(words, key=lambda w: w["x0"])
                    if abs(w["top"] - label["top"]) <= ROW_TOL and w["x0"] > label["x1"])


IPG_LABELS = ["Device Type", "Model", "Serial", "Implant Date", "Firmware",
              "Battery Type", "Battery Voltage", "Patient Amplitude"]


def extract_ipg(page):
    """Valori della colonna IPG: per ogni etichetta, le righe tra essa e l'etichetta
    successiva (per l'ultima, solo la riga subito sotto)."""
    words = page.extract_words(keep_blank_chars=True)
    port_x = min(w["x0"] for w in words if w["text"].startswith("Port:"))
    column = group_rows([w for w in words if w["x1"] < port_x])
    texts = [" ".join(w["text"].strip() for w in r) for r in column]

    pos = {lab: next(i for i, t in enumerate(texts) if t.rstrip(":") == lab)
           for lab in IPG_LABELS}
    info = {}
    for lab, nxt in zip(IPG_LABELS, IPG_LABELS[1:] + [None]):
        end = pos[nxt] if nxt else pos[lab] + 2
        info[lab] = " ".join(texts[pos[lab] + 1:end])
    return info


def extract_tables(page):
    words = page.extract_words()
    ports = sorted((w for w in words if w["text"] == "Port:"), key=lambda w: w["top"])
    tables = []

    for i, port in enumerate(ports):
        top = port["top"]
        bottom = ports[i + 1]["top"] if i + 1 < len(ports) else page.height
        section = [w for w in words if top <= w["top"] < bottom and w["x0"] >= port["x0"] - 2]

        # Nome della porta: tutto il testo dopo "Port:" sulla stessa riga (es. "C", "D", "Left Lead")
        port_name = " ".join(w["text"] for w in sorted(section, key=lambda w: w["x0"])
                             if abs(w["top"] - top) <= ROW_TOL and w["x0"] > port["x1"])

        # Emisfero: la parola subito sotto "Hemisphere", nella stessa colonna
        hemi = next(w for w in section if w["text"] == "Hemisphere")
        hemisphere = min(
            (w for w in section if w["top"] > hemi["top"] and abs(w["x0"] - hemi["x0"]) <= COL_TOL),
            key=lambda w: w["top"],
        )["text"]

        tables.append({"port": port_name, "hemisphere": hemisphere,
                       "columns": COLUMNS, "rows": read_table(page, section, port_name)})
    return tables


def read_table(page, section, port_name):
    """Tabella triangolare con extract_table: righe e colonne sono ricavate dalla
    posizione delle etichette fisse (COLUMNS in intestazione, ROWS a sinistra)."""
    case = next(w for w in section if w["text"] == "case")
    header = sorted((w for w in section if abs(w["top"] - case["top"]) <= ROW_TOL
                     and w["x0"] >= case["x0"] - COL_TOL and w["text"] in COLUMNS),
                    key=lambda w: w["x0"])
    labels = sorted((w for w in section if w["top"] > case["top"] + ROW_TOL
                     and w["x1"] < case["x0"] and w["text"] in ROWS),
                    key=lambda w: w["top"])
    check([w["text"] for w in header] == COLUMNS, port_name, "intestazione inattesa")
    check([w["text"] for w in labels] == ROWS, port_name, "etichette di riga inattese")

    step = header[-1]["x0"] - header[-2]["x0"]
    xs = [labels[0]["x0"] - 2] + [w["x0"] - 2 for w in header] + [header[-1]["x0"] + step - 2]
    ys = [case["top"] - 2] + [w["top"] - 2 for w in labels] + [labels[-1]["bottom"] + 2]
    table = page.crop((xs[0], ys[0], xs[-1], ys[-1])).extract_table({
        "vertical_strategy": "explicit", "explicit_vertical_lines": xs,
        "horizontal_strategy": "explicit", "explicit_horizontal_lines": ys,
    })

    check(table[0][1:] == COLUMNS, port_name, f"intestazione estratta {table[0]}")
    rows = []
    for k, (label, row) in enumerate(zip(ROWS, table[1:]), start=1):
        # Triangolo: la riga k-esima ha esattamente k valori numerici, poi celle vuote.
        # "+9999" = fuori scala: int() lo converte in 9999
        values, empty = row[1:k + 1], row[k + 1:]
        check(row[0] == label and all(v and v.removeprefix("+").isdigit() for v in values)
              and not any(empty),
              port_name, f"riga {label} non valida: {row}")
        rows.append((label, [int(v) for v in values] + [None] * len(empty)))
    return rows


def read_tables_stream(pdf_path, page_no):
    """Stesse tabelle lette nell'ordine del testo nel PDF (pypdf), per verifica incrociata:
    dopo "Port: X" seguono l'intestazione e, per ogni riga Eₖ, l'etichetta e k valori."""
    lines = [l.strip() for l in PdfReader(pdf_path).pages[page_no - 1].extract_text().splitlines()]
    tables = {}
    for i, line in enumerate(lines):
        if not line.startswith("Port:"):
            continue
        port_name = line.removeprefix("Port:").strip()
        tokens = " ".join(lines[i + 1:]).split()
        pos = tokens.index("case")
        check(tokens[pos:pos + len(COLUMNS)] == COLUMNS, port_name, "intestazione inattesa (stream)")
        pos += len(COLUMNS)
        rows = []
        for k, label in enumerate(ROWS, start=1):
            check(tokens[pos] == label, port_name, f"attesa riga {label} (stream), trovato {tokens[pos]!r}")
            values = [int(v) for v in tokens[pos + 1:pos + 1 + k]]
            rows.append((label, values + [None] * (len(COLUMNS) - k)))
            pos += 1 + k
        tables[port_name] = rows
    return tables


def check(condition, port_name, message):
    if not condition:
        raise ValueError(f"Port {port_name}: {message}")


PAGE_KEYWORDS = {"Configuration", "IPG", "Model", "Serial", "Firmware", "Port", "Hemisphere"}


def find_page(pdf):
    """Numero (da 1) dell'unica pagina che contiene tutte le PAGE_KEYWORDS."""
    found = [i for i, p in enumerate(pdf.pages, start=1)
             if PAGE_KEYWORDS <= {w.rstrip(":") for w in (p.extract_text() or "").split()}]
    if len(found) != 1:
        raise ValueError(f"attesa una sola pagina con {sorted(PAGE_KEYWORDS)}, trovate: {found}")
    return found[0]


def process_pdf(pdf_path, page_no=None):
    """Estrae i dati da un PDF, scrive il CSV accanto al PDF e restituisce i record.
    Senza page_no la pagina viene cercata con find_page."""
    with pdfplumber.open(pdf_path) as pdf:
        page_no = page_no or find_page(pdf)
        page = pdf.pages[page_no - 1]
        info = {"Visit Date": extract_visit_date(page), **extract_ipg(page)}
        tables = extract_tables(page)
    for key in ("Visit Date", "Implant Date"):
        info[key] = datetime.strptime(info[key], "%d %b %Y").strftime("%d/%m/%Y")

    # Verifica incrociata: le due estrazioni indipendenti devono coincidere
    stream = read_tables_stream(pdf_path, page_no)
    check([t["port"] for t in tables] == list(stream), "-", f"porte diverse: {list(stream)}")
    for t in tables:
        check(t["rows"] == stream[t["port"]], t["port"], "extract_table e ordine del testo non coincidono")

    # Formato tidy: una riga per ogni impedenza misurata, con i dati anagrafici ripetuti
    records = [
        {**info, "Port": t["port"], "Hemisphere": t["hemisphere"],
         "Row": label, "Column": col, "Impedance": v}
        for t in tables
        for label, vals in t["rows"]
        for col, v in zip(t["columns"], vals)
        if v is not None
    ]
    write_csv(pdf_path.with_suffix(".csv"), records)
    return records


def write_csv(out, records):
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"{len(records)} righe  ->  {out}")


def main():
    parser = argparse.ArgumentParser(
        description="Estrae da report DBS Vercise Neural Navigator (PDF) le tabelle delle "
                    "impedenze, l'emisfero, la Visit Date e i dati IPG, in formato CSV tidy "
                    "(una riga per impedenza).",
        epilog="Con un file: scrive <nome>.csv accanto al PDF. "
               "Con una cartella: cerca i PDF anche nelle sottocartelle, scrive il CSV di "
               "ciascuno accanto al relativo PDF e, nella cartella indicata, un CSV "
               f"complessivo ({MERGED_NAME}) con una colonna File in più.",
    )
    parser.add_argument("path", type=Path, help="file PDF o cartella da elaborare")
    parser.add_argument("--page", type=int,
                        help="pagina del PDF con le tabelle (default: cercata in automatico)")
    args = parser.parse_args()

    if args.path.is_file():
        process_pdf(args.path, args.page)
        return
    if not args.path.is_dir():
        parser.error(f"percorso non trovato: {args.path}")

    merged, failed = [], []
    for pdf_path in sorted(args.path.rglob("*.pdf", case_sensitive=False)):
        try:
            records = process_pdf(pdf_path, args.page)
        except Exception as e:
            # Un PDF non valido non blocca gli altri: viene segnalato alla fine
            print(f"ERRORE {pdf_path}: {e!r}", file=sys.stderr)
            failed.append(pdf_path)
            continue
        rel = pdf_path.relative_to(args.path).as_posix()
        merged += [{"File": rel, **r} for r in records]

    if merged:
        write_csv(args.path / MERGED_NAME, merged)
    else:
        print("Nessun PDF elaborato.")
    if failed:
        print(f"{len(failed)} PDF non elaborati:", *failed, sep="\n  ", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
