# FIRMS Hotspot Watch

Serverseitige GitHub-Actions-Überwachung für satellitengestützte FIRMS-Hotspots innerhalb eines festen Polygons.

## Überwachtes Polygon

- 44.83812, 21.30252
- 44.79014, 21.21291
- 44.89789, 20.99648
- 44.96886, 21.10188

Das Skript fragt die FIRMS Area API für die Bounding Box ab und filtert anschließend **geometrisch exakt** auf das Polygon.

## Datenquellen

Standardmäßig werden folgende FIRMS-NRT-Quellen versucht:

- `VIIRS_NOAA21_NRT`
- `VIIRS_NOAA20_NRT`
- `VIIRS_SNPP_NRT`
- `MODIS_NRT`
- `LANDSAT_NRT`

Falls eine Quelle bei FIRMS für die Area API nicht verfügbar ist, wird der Fehler isoliert in `data/status.json` protokolliert; die anderen Quellen laufen weiter.

## Einrichtung

1. Neues GitHub-Repository erstellen.
2. Inhalt dieses ZIPs in das Repository hochladen.
3. In GitHub öffnen:
   **Settings → Secrets and variables → Actions → New repository secret**
4. Secret anlegen:
   - Name: `FIRMS_MAP_KEY`
   - Value: dein aktueller FIRMS MAP_KEY
5. Unter **Actions** den Workflow `FIRMS Hotspot Watch` einmal über **Run workflow** manuell starten.

## Intervall

Der Workflow ist auf

```yaml
cron: "*/10 * * * *"
```

gesetzt, also nominell alle 10 Minuten.

Hinweis: GitHub Actions garantiert bei `schedule` keine sekundengenaue Ausführung; bei hoher Plattformlast können geplante Runs verspätet starten.

## Ausgaben

- `data/status.json`  
  Letzter Lauf, Quellenstatus und neue Hotspots.
- `data/events.jsonl`  
  Append-only Historie neu erkannter Hotspots.
- `data/seen.json`  
  Deduplizierungszustand.
- `data/summary.md`  
  Menschlich lesbare Kurzfassung des letzten Laufs.

## Hotspot-Daten

Soweit von FIRMS geliefert, bleiben u. a. erhalten:

- latitude / longitude
- acquisition date / time
- FRP
- confidence
- day/night
- brightness / scan / track, abhängig vom Produkt

## Bewertung

Das Skript berechnet zusätzlich eine einfache `severity`:

- `low`
- `medium`
- `high`

Sie basiert nur auf tatsächlich gelieferten FIRMS-Werten für FRP und Confidence. Sie ist **keine amtliche Brandklassifikation**.

## Sicherheit

Der FIRMS-Key gehört ausschließlich in das GitHub-Secret `FIRMS_MAP_KEY`.

**Nie den Key in `watch.py`, Workflow-Dateien, Issues oder Commits eintragen.**

Falls ein Key bereits öffentlich oder in einem Chat geteilt wurde, sollte er ersetzt werden, bevor dieses Repository produktiv genutzt wird.

## Manuell testen

Der Workflow unterstützt `workflow_dispatch`, daher kann er jederzeit unter:

**Actions → FIRMS Hotspot Watch → Run workflow**

gestartet werden.

## Lokaler Test (optional)

```bash
pip install -r requirements.txt
export FIRMS_MAP_KEY="..."
python watch.py
```
