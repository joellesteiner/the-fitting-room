# ADR 0001: Learn the sensor model from data instead of setting it by hand

**Status:** Accepted, 18 November 2026

## Context

The 001 prototype updated its size belief using a sensor model, P(fit report | true size minus worn size), whose values were set by hand. For example, it assumed a shopper wearing one size too small reports "too tight" 80% of the time. These values decide how far a post delivery fit report moves the recommendation, but nothing tested them.

## Decision

Estimate the sensor model from ModCloth repeat buyers (8,774 owned and next pair examples from 2,213 shoppers), with Laplace smoothing, and load it in the app from `app/model/sensor_learned.json`. Judge it with five fold cross validation split by shopper (`research/backtest`).

## Evidence

| Measure | 001 assumed | Learned |
| --- | --- | --- |
| P("too tight" given one size too small) | 80% | 17% |
| Size calibration error | 13% | 3% |
| Exact size accuracy | 45% | 51% |
| Fit report log loss (lower is better) | 1.39 | 0.77 |

## Consequences

* Stated confidence now tracks real accuracy, which is what the abstain rule depends on.
* A single fit report moves the belief far less, so the app abstains more often after a report. This is the correct response to weak evidence, but it makes the demo less dramatic.
* The weak signal is probably caused by cross brand sizing on ModCloth. The pilot must collect garment linked fit reports within one brand, and the sensor should be relearned on that data.

## Alternatives considered

* **Keep the hand set values.** Rejected: overconfident by 13 points on unseen shoppers.
* **Train a classifier on body measurements** (001 experiment). Rejected: 41% macro recall, and it needs body data the product promises not to collect.
