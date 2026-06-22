# Flight Data Analyzer

A Python portfolio project that turns Mission Planner and ArduPilot flight logs
into a self-contained, readable HTML report. It demonstrates telemetry parsing,
time-series analysis, event detection, engineering heuristics, and a small
privacy-conscious upload service without a web framework.

## What works now

- Generates a realistic synthetic flight (no hardware required)
- Imports a normalized CSV file
- Analyzes takeoff, landing, mode changes, low battery, and key maxima
- Produces a self-contained HTML report with plots
- Includes a `.tlog` adapter for Mission Planner telemetry logs

## Data flow

```text
Mission Planner .tlog -> MAVLink adapter -> normalized samples -> analyzer -> HTML report
Synthetic flight  ----^                         |
CSV file -----------^                           +-> events and summary
```

The normalized CSV columns are documented in `flightrecorder/model.py`. Keeping
one internal format means future `.BIN`, live MAVLink, ESC, and fuel-flow inputs
can reuse the same analyzer.

## Run the first exercise

The commands below use the Python executable available on your machine. In the
Codex desktop workspace, the bundled Python runtime can also be used.

```powershell
python -m flightrecorder simulate work/sample_flight.csv
python -m flightrecorder analyze work/sample_flight.csv outputs/sample_report.html
```

Open `outputs/sample_report.html` in a browser.

## Upload dashboard

On Windows, start the local dashboard with:

```powershell
.\start_dashboard.ps1
```

Then upload a Mission Planner `.tlog` or an ArduPilot DataFlash `.BIN`. The file
is processed locally and the generated report is displayed in the browser.

To install the parser dependency in a fresh environment first:

```powershell
python -m pip install -r requirements.txt
```

The local dashboard remains available at `http://127.0.0.1:8765`. Command-line
flags can override the address, and the server also honors the `HOST`, `PORT`,
and `MAX_UPLOAD_MB` environment variables.

## Deploy on Render

1. Push this repository to a public GitHub repository. Review the commit before
   publishing; flight logs and generated outputs may contain sensitive routes.
2. In Render, choose **New > Blueprint** and connect the repository.
3. Apply the detected `render.yaml` service and wait for the first build.

The blueprint installs `requirements.txt`, uses the Python version pinned in
`.python-version`, binds to Render's public interface, and reads Render's `PORT`
automatically. The free service can sleep when idle, so its first request may
take longer.

Public uploads are capped at 25 MB by default. Each raw log and generated report
is held in an isolated temporary directory, returned directly to the requester,
and deleted at the end of that request. No database or persistent disk is used.
Operators should still treat the service as an engineering demonstration: do
not upload logs containing sensitive location data unless you trust the host.

## Public-repository checklist

- Confirm `git status` does not include `work/`, `outputs/`, logs, credentials,
  virtual environments, or editor settings.
- Add a repository description and a screenshot that uses synthetic data.
- Link the deployed Render URL in the GitHub repository's **About** section.
- Run the test command below before publishing.

## Import a Mission Planner `.tlog`

Install the MAVLink parser:

```powershell
python -m pip install pymavlink
```

Then run:

```powershell
python -m flightrecorder import-tlog path\to\flight.tlog work\flight.csv
python -m flightrecorder analyze work\flight.csv outputs\flight_report.html
```

`.tlog` contains only telemetry that reached Mission Planner. It is not as
complete as the flight controller's onboard `.BIN` log.

To generate a repeatable test log:

```powershell
python -m flightrecorder generate-tlog outputs\pseudo_mission_planner.tlog
```

## Run tests

```powershell
python -m unittest discover -s tests -v
```

## Suggested learning order

1. Read `model.py` to understand the common data model.
2. Read `simulator.py` to see how a flight is represented mathematically.
3. Read `analysis.py` and change an event threshold.
4. Read `report.py` to see how raw values become a visual report.
5. Read `tlog.py` to see how MAVLink messages are merged into samples.
