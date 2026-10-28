# dbs_pdf2csv

Estrae dai report PDF di Vercise Neural Navigator (DBS Boston Scientific) le tabelle
delle impedenze, l'emisfero, la Visit Date e i dati IPG, e li salva in CSV in formato
tidy (una riga per ogni impedenza misurata).

## Requisiti

- Python 3.12 o superiore

## Installazione

Linux / macOS:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Windows:

```bat
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

## Uso

Su Windows sostituire `venv/bin/python` con `venv\Scripts\python`.

```bash
# Help
venv/bin/python dbs_pdf2csv.py -h

# Singolo PDF: scrive report.csv accanto al PDF
venv/bin/python dbs_pdf2csv.py report.pdf

# Cartella: elabora tutti i PDF, anche nelle sottocartelle
venv/bin/python dbs_pdf2csv.py cartella/

# Forzare la pagina con le tabelle (di solito non serve)
venv/bin/python dbs_pdf2csv.py report.pdf --page 3
```

La pagina con le tabelle viene cercata in automatico: è l'unica che contiene tutte le
parole Configuration, IPG, Model, Serial, Firmware, Port e Hemisphere.

Con una cartella lo script scrive:

- un CSV accanto a ogni PDF, con lo stesso nome;
- `dbs_merged.csv` nella cartella indicata, con i dati di tutti i PDF e una colonna
  `File` con il percorso del PDF di origine.

Se un PDF non può essere elaborato, viene segnalato e lo script passa al successivo;
alla fine elenca i file non elaborati ed esce con codice 1.

## Output

| Colonna | Esempio |
|---|---|
| File (solo in `dbs_merged.csv`) | `paziente1/report.pdf` |
| Visit Date | `09/04/2021` |
| Device Type | `Vercise Gevia™` |
| Model | `DB1200` |
| Serial | `744927` |
| Implant Date | `22/03/2021` |
| Firmware | `9028451-101-00` |
| Battery Type | `Rechargeable` |
| Battery Voltage | `3.73 V` |
| Patient Amplitude | `OFF` |
| Port | `C` |
| Hemisphere | `Left` |
| Row | `E7` |
| Column | `E8` |
| Impedance | `4031` (Ω) |

`Row` e `Column` sono le etichette della tabella triangolare nel PDF.

Nel PDF le impedenze fuori scala compaiono come `+9999`: nel CSV vengono scritte come
`9999`. Un valore `9999` va quindi letto come "9999 Ω o più" e non si distingue da una
misura reale di esattamente 9999 Ω.

## Controlli

Le tabelle vengono estratte in due modi (griglia ricavata dalle etichette e ordine del testo nel PDF) e i risultati
devono coincidere; vengono inoltre verificate intestazioni, etichette di riga e
struttura triangolare. Se qualcosa non torna, il PDF viene scartato con un errore
invece di produrre dati sbagliati.
