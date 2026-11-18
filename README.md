# The Fitting Room

An AI size recommender for jeans that uses a pair you already own as the size guide, instead of body measurements.

Built as the proof of concept for QMUL IOT6000U Digital Innovation and Product Development.

## How it works

The recommender has three layers, kept separate on purpose:

1. **Product matching.** TF IDF retrieval matches the shopper's description to a catalogue product.
2. **Starting size.** A transparent chart rule turns the owned size and how it fits into a starting size.
3. **Confidence.** A Bayesian belief over sizes gives a confidence level. The app abstains when the top size holds less than 50% of the belief, and updates the belief from fit reports after delivery.

No height, weight or body measurements are collected.

## Repository layout

| Path | Contents |
| --- | --- |
| `app/` | Web prototype: Python server, recommendation engine, front end and unit tests |
| `research/modcloth/` | Fit classifier experiment on the ModCloth dataset |

## Running the prototype

Requires Python 3.10 or later.

```
cd app
pip install -r requirements.txt
python -m unittest discover -s tests
python server.py
```

Then open http://127.0.0.1:8799. On Windows you can double click `app/START_WINDOWS.bat` instead.

## Research data

The ModCloth dataset (Misra, Wan and McAuley, 2018) is not stored in this repository. Download `modcloth_final_data.json` from the authors' release and pass its path to the script:

```
python research/modcloth/experiment.py path/to/modcloth_final_data.json
```

## Status

Proof of concept. Probabilities in the current engine are stated modelling assumptions, not validated fit predictions.
