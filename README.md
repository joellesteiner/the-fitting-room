# The Fitting Room

An AI size recommender for jeans that uses a pair you already own as the size guide, instead of body measurements.

Built as the proof of concept for QMUL IOT6000U Digital Innovation and Product Development.

## How it works

The recommender has three layers, kept separate on purpose:

1. **Product matching.** TF IDF retrieval matches the shopper's description to a catalogue product.
2. **Starting size.** A transparent chart rule turns the owned size and how it fits into a starting size.
3. **Confidence.** A Bayesian belief over sizes gives a confidence level. The app abstains when the top size holds less than 50% of the belief, and updates the belief from fit reports after delivery.

No height, weight or body measurements are collected.

## What is stored

Saved pairs and fit reports are kept in a local SQLite file, `app/data/fitting_room.db`, which is never committed. Each shopper is a random ID kept in their browser; there are no names, emails or body data. Every query is parameterised. See [ADR 0002](docs/adr/0002-store-data-in-sqlite.md).

The belief behind each recommendation stays on the server. The browser gets a random recommendation ID and sends back only that ID, the size worn and how it fitted, so it cannot choose the probabilities the update starts from, and each recommendation counts as one fit report at most. See [ADR 0003](docs/adr/0003-keep-the-belief-on-the-server.md).

## Results

Backtested on 2,213 ModCloth shoppers the model never saw (five fold cross validation by shopper):

* Stated confidence is on average within 3 points of the real hit rate, down from 13 points with the 001 hand set model.
* Abstaining below 50% confidence still serves 78% of shoppers and lifts exact size accuracy from 51% to 54%.
* Learning showed that a fit report on another brand's garment is weak evidence, which shapes what the pilot must collect.

Full analysis: [research/backtest/backtest.ipynb](research/backtest/backtest.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/joellesteiner/the-fitting-room/blob/main/research/backtest/backtest.ipynb)

## Repository layout

| Path | Contents |
| --- | --- |
| `app/` | Web prototype: Python server, recommendation engine, SQLite storage, learned model file, front end and tests |
| `research/backtest/` | Learned model and backtest: code, tests, notebook, results and charts |
| `research/modcloth/` | 001 fit classifier experiment on the ModCloth dataset |
| `docs/adr/` | Architecture decision records |
| `evidence/` | Screenshots and records supporting the report |

## Running the prototype

Requires Python 3.10 or later.

```
cd app
pip install -r requirements.txt
python -m unittest discover -s tests
python server.py
```

Then open http://127.0.0.1:8799. On Windows you can double click `app/START_WINDOWS.bat` instead.

To use a different database file, set `FITTING_ROOM_DB` before starting the server. To start afresh, delete `app/data/fitting_room.db`.

## Your data

The prototype never asks for a name, email, height, weight or any other body measurement, and the server refuses any request that tries to send one (400, `Unexpected field`). What it does keep is listed at the top of `app/storage.py`.

* **Delete my data:** the button on the first step, or `DELETE /api/shopper` with the `X-Shopper-Id` header, removes the shopper and every saved pair, fit report and recommendation linked to them. SQLite `secure_delete` overwrites the deleted rows in the file.
* **Retention:** recommendations are deleted after 30 days. A fit report outlives its recommendation and keeps only product, size worn and fit.

See [ADR 0004](docs/adr/0004-delete-my-data-and-retention.md).

## Research data

The ModCloth dataset (Misra, Wan and McAuley, 2018) is not stored in this repository. Download `modcloth_final_data.json` from the authors' release and pass its path to the script:

```
python research/modcloth/experiment.py path/to/modcloth_final_data.json
python research/backtest/backtest.py path/to/modcloth_final_data.json --write-app-model
python research/backtest/charts.py
```

The notebook downloads the data itself.

## Status

Proof of concept. The sensor model is learned from ModCloth; the belief width and the 50% abstain bar are design choices that a pilot will tune.
