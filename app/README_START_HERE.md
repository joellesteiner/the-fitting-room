# The Fitting Room, Bayesian version

## Run it
1. Unzip into a normal folder.
2. Double click START_WINDOWS.bat and keep the black window open.
3. Wait for "Ran 21 tests ... OK". Chrome opens http://127.0.0.1:8799.

## What changed
- Fixed a sizing bug: "a little tight" used to move the size DOWN. It now moves up, and a test guarantees it never sizes down.
- Added a Bayesian belief over sizes: confidence %, belief bars, abstain below 50%.
- Added step 4: report fit after delivery, which updates the belief with Bayes' rule and shows the working.
- Low quality product matches now abstain instead of erroring.
- No height, weight or body data anywhere. ModCloth research panel removed from the shopper app.
- 21 unit tests (was 12).

## Assumptions (all illustrative)
- Prior: discretised Gaussian over chart sizes, centred on the chart rule size. Width 0.70 size steps for the same style, 0.75 for the 501 family, 1.20 for a different cut, plus 0.40 for oversized. A tight or loose report leans it 0.15 steps further that way.
- Sensor model, P(report | true size minus worn size): 0 gives tight 0.15, right 0.70, loose 0.15; +1 gives tight 0.80; minus 1 gives tight 0.05.
- Recommend only if the top size holds at least 50% of the belief.
