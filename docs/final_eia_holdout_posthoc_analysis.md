# POST-HOC ANALYSIS — NOT USED FOR MODEL SELECTION

This note describes the one-shot final EIA holdout after it was scored. It does not change that score.

The preregistered result remains **FAIL**: Ridge MAE 2.638473 ¢/kWh versus paired availability-adjusted seasonal-naive MAE 2.613667 ¢/kWh, an improvement of −0.9491% against a threshold of at least +10%. Sixty cells were attempted and sixty were scored. Runner commit `ee5bcf6d541a1b15822f705e4099320f6f05dc32`, executed once on 2026-10-04. Recorded summary: `docs/final_eia_holdout_oneshot.json`. Case rows: `data/processed/final_holdout/final_holdout_cases.parquet`.

## Analysis boundary

Numbers below are read from that case file. Development case-level residuals were not saved, so they were not recomputed. No model was fit. No penalty was selected. Features, the seasonal-naive rule, and the interval rule are unchanged. Nothing here is a cause. In particular, this note does not use PJM, fuel prices, weather, regulation, tariffs, or data-center load to explain the errors. Those would be a separate investigation.

Signed error is `actual − prediction`. A positive value means the forecast was below the actual price.

`scripts/describe_final_holdout_errors.py` reprints the summary counts from the same case file. It does not call the holdout runner.

## Error direction

Ridge underpredicted every holdout case. So did the seasonal naive. There are no overpredictions and no exact ties.

| | Mean signed error | Median signed error | Underpredictions | Overpredictions | Exact |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ridge | 2.638473 | 2.5794 | 60 | 0 | 0 |
| Seasonal naive | 2.613667 | 2.6400 | 60 | 0 | 0 |

Because every Ridge signed error is positive, the Ridge mean signed error equals the Ridge MAE. The same is true for the seasonal naive. The holdout failure is predominantly underprediction. It is underprediction in all 60 cases, not a mixture that happens to average out.

The same one-sided pattern holds in each state (12 cases each):

| State | Ridge mean | Ridge median | Ridge under / over | Seasonal mean | Seasonal median | Seasonal under / over |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MD | 3.3855 | 3.1260 | 12 / 0 | 3.6083 | 3.4250 | 12 / 0 |
| NJ | 2.7261 | 2.6873 | 12 / 0 | 3.1783 | 3.1100 | 12 / 0 |
| OH | 2.3859 | 2.5877 | 12 / 0 | 2.1575 | 2.2050 | 12 / 0 |
| PA | 2.3448 | 2.0692 | 12 / 0 | 2.3425 | 2.2400 | 12 / 0 |
| VA | 2.3500 | 2.0764 | 12 / 0 | 1.7817 | 1.5350 | 12 / 0 |

The smallest Ridge signed error is still +0.697 ¢/kWh (Ohio, target 2025-07). The largest is +5.318 ¢/kWh (Maryland, target 2026-02).

## Month-by-month break

Each row is the five-state mean for that target month. Improvement is `(seasonal MAE − Ridge MAE) / seasonal MAE`. Positive would mean Ridge is closer.

| Target | Mean actual | Ridge MAE | Seasonal MAE | Ridge signed | Seasonal signed | Ridge vs seasonal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-07 | 13.568 | 2.070 | 2.050 | 2.070 | 2.050 | −0.98% |
| 2025-08 | 13.478 | 2.079 | 1.996 | 2.079 | 1.996 | −4.14% |
| 2025-09 | 13.432 | 2.042 | 2.006 | 2.042 | 2.006 | −1.79% |
| 2025-10 | 13.426 | 2.150 | 1.984 | 2.150 | 1.984 | −8.36% |
| 2025-11 | 13.514 | 2.328 | 2.066 | 2.328 | 2.066 | −12.66% |
| 2025-12 | 13.522 | 2.335 | 2.178 | 2.335 | 2.178 | −7.21% |
| 2026-01 | 14.872 | 3.667 | 3.524 | 3.667 | 3.524 | −4.04% |
| 2026-02 | 15.514 | 4.256 | 4.116 | 4.256 | 4.116 | −3.40% |
| 2026-03 | 14.426 | 2.913 | 2.872 | 2.913 | 2.872 | −1.41% |
| 2026-04 | 14.168 | 2.493 | 2.652 | 2.493 | 2.652 | +5.99% |
| 2026-05 | 14.510 | 2.635 | 2.932 | 2.635 | 2.932 | +10.15% |
| 2026-06 | 14.680 | 2.696 | 2.988 | 2.696 | 2.988 | +9.78% |

From 2025-07 through 2025-09, Ridge MAE stays near 2.04–2.08 ¢/kWh. October through December drift up toward about 2.3. January is the first month that sits well above that earlier band (3.67), and February is the worst Ridge month (4.26). March through June come back toward about 2.5–2.9, which is still above the July–September level. The path is a step up into January–February, not a smooth climb from July, and not a single stray cell.

The seasonal naive moves at the same time: about 2.0 through the autumn, then 3.52 in January and 4.12 in February, then back toward 2.9–3.0. Both forecasts are already low in the first holdout months. The larger errors later are a further drop in accuracy for both, not a Ridge-only break.

## State by month

Ridge signed errors, in ¢/kWh. Every entry is positive, so every entry is an underprediction.

| State | 2025-07 | 2025-08 | 2025-09 | 2025-10 | 2025-11 | 2025-12 | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MD | 2.730 | 2.601 | 2.522 | 2.682 | 2.971 | 3.184 | 5.267 | 5.318 | 3.616 | 3.386 | 3.068 | 3.280 |
| NJ | 3.876 | 4.055 | 2.709 | 2.082 | 1.582 | 1.938 | 3.601 | 3.077 | 2.666 | 1.669 | 2.557 | 2.902 |
| OH | 0.697 | 0.813 | 1.460 | 1.959 | 2.323 | 2.049 | 2.853 | 3.703 | 3.234 | 3.138 | 3.379 | 3.023 |
| PA | 1.470 | 1.603 | 2.005 | 1.946 | 2.134 | 2.432 | 3.491 | 4.041 | 3.166 | 2.285 | 1.817 | 1.749 |
| VA | 1.577 | 1.320 | 1.514 | 2.081 | 2.628 | 2.071 | 3.120 | 5.142 | 1.880 | 1.989 | 2.351 | 2.525 |

Seasonal-naive signed errors:

| State | 2025-07 | 2025-08 | 2025-09 | 2025-10 | 2025-11 | 2025-12 | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MD | 2.94 | 2.64 | 2.72 | 2.89 | 3.03 | 3.02 | 5.14 | 5.35 | 3.86 | 3.82 | 3.92 | 3.97 |
| NJ | 3.47 | 4.10 | 2.91 | 2.64 | 2.27 | 2.56 | 4.31 | 3.70 | 3.31 | 2.65 | 3.12 | 3.10 |
| OH | 0.93 | 0.64 | 1.10 | 1.41 | 1.79 | 1.69 | 2.62 | 3.16 | 2.83 | 2.96 | 3.45 | 3.31 |
| PA | 1.54 | 1.79 | 1.63 | 1.66 | 1.73 | 2.06 | 3.31 | 4.04 | 2.92 | 2.43 | 2.42 | 2.58 |
| VA | 1.37 | 0.81 | 1.67 | 1.32 | 1.51 | 1.56 | 2.24 | 4.33 | 1.44 | 1.40 | 1.75 | 1.98 |

All twelve target months have the same error direction in all five states, for both Ridge and the seasonal naive. The “at least four of five” count is therefore also all twelve months. There is no month in which the states disagree about the sign.

The largest Ridge misses sit together in January and February 2026: Maryland 5.27 and 5.32, Virginia 5.14 in February, Pennsylvania 4.04 in February, New Jersey 3.60 in January. Ohio’s largest miss is also February (3.70), though Ohio’s errors grow more steadily from July. The sign is common to the whole window. The unusually large magnitudes cluster in those two months and across several states at once.

## Actual prices in the holdout window

These are the scored commercial prices already stored on the holdout cases.

| State | 2025-07 | 2026-06 | Change | Percent | Minimum (month) | Maximum (month) |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| MD | 15.14 | 16.84 | +1.70 | +11.2% | 15.09 (2025-08) | 18.19 (2026-01) |
| NJ | 18.36 | 18.47 | +0.11 | +0.6% | 15.91 (2025-11) | 18.68 (2025-08) |
| OH | 11.50 | 13.77 | +2.27 | +19.7% | 11.45 (2025-08) | 14.30 (2026-02) |
| PA | 12.63 | 13.33 | +0.70 | +5.5% | 12.63 (2025-07) | 14.86 (2026-02) |
| VA | 10.21 | 10.99 | +0.78 | +7.6% | 9.46 (2025-08) | 13.01 (2026-02) |

Five-state mean actual by target month: 13.57, 13.48, 13.43, 13.43, 13.51, 13.52, then 14.87, 15.51, 14.43, 14.17, 14.51, 14.68. The average is nearly flat from July through December 2025, then higher from January 2026 through June, with the peak in February. That is a broad upward move in the five-state average during the second half of the window. It is not uniform: New Jersey’s June price is almost its July price, and New Jersey’s high is August 2025 rather than early 2026. This description does not assign a cause.

## Forecast responsiveness

Five-state mean level:

| Target | Actual | Ridge | Seasonal naive |
| --- | ---: | ---: | ---: |
| 2025-07 | 13.57 | 11.50 | 11.52 |
| 2025-08 | 13.48 | 11.40 | 11.48 |
| 2025-09 | 13.43 | 11.39 | 11.43 |
| 2025-10 | 13.43 | 11.28 | 11.44 |
| 2025-11 | 13.51 | 11.19 | 11.45 |
| 2025-12 | 13.52 | 11.19 | 11.34 |
| 2026-01 | 14.87 | 11.21 | 11.35 |
| 2026-02 | 15.51 | 11.26 | 11.40 |
| 2026-03 | 14.43 | 11.51 | 11.55 |
| 2026-04 | 14.17 | 11.67 | 11.52 |
| 2026-05 | 14.51 | 11.88 | 11.58 |
| 2026-06 | 14.68 | 11.98 | 11.69 |

The actual average rises by about 2 ¢/kWh from December to February. Over those same months the Ridge average stays near 11.2 and the seasonal-naive average stays near 11.4. Across the whole window the Ridge average only moves from about 11.2 to 12.0, and the seasonal average from about 11.3 to 11.7.

Within each state, the range of actual prices is wider than the range of either forecast:

| State | Actual range | Ridge range | Seasonal range |
| --- | ---: | ---: | ---: |
| MD | 3.10 | 1.15 | 0.85 |
| NJ | 2.77 | 1.76 | 2.27 |
| OH | 2.85 | 0.60 | 0.76 |
| PA | 2.23 | 1.02 | 0.54 |
| VA | 3.55 | 0.98 | 0.90 |

Ridge is not flat in every state, but its month-to-month movement is smaller than the actual’s in Maryland, Ohio, and Virginia, and it does not follow the January–February rise in the five-state average. The seasonal naive is similar: a little wider than Ridge in New Jersey and Ohio, a little narrower in Maryland and Pennsylvania, and likewise low through the months when the actual average is highest. This is a description of the scored series. It is not a proposed correction.

## Development versus holdout residuals

The 1,145 development out-of-sample Ridge rows were not written to disk. They were not refit for this note, so this section does not report a development 80th or 90th percentile of those rows, and it does not report a percentage of holdout errors above a percentile that was never stored.

What is already published, and what the holdout file itself shows:

- Development Ridge MAE on 1,145 paired cases: 0.7075 ¢/kWh. Holdout Ridge MAE: 2.638473. Holdout median absolute error: 2.579. Holdout 80th percentile of absolute error: 3.300. Holdout 90th percentile: 3.720. Holdout maximum: 5.318.
- The smallest holdout absolute error, 0.697, is about the size of the development MAE. The center of the holdout distribution, not only its tail, sits above that development MAE.
- Development state MAEs on the same 1,145 cases were MD 1.088, NJ 0.894, OH 0.386, PA 0.532, VA 0.637. Holdout state MAEs are 3.385, 2.726, 2.386, 2.345, and 2.350. Every state is higher. Ohio’s holdout MAE is several times its development MAE; Maryland’s is also much higher, from an already higher base.
- Each holdout interval half-width is the frozen development absolute-residual order statistic for that state and origin (`k = ceil((n + 1) * 0.8)`). All 60 holdout absolute errors exceed that case’s half-width. Relative to the development calibration quantile actually used for these forecasts, the holdout errors are not a pair of outliers on an otherwise familiar distribution. The whole set sits outside that quantile. Median absolute error is 2.58 ¢/kWh against a median half-width of 0.87 ¢/kWh.

## Why coverage is 0%

An actual is outside the interval by `distance_outside_interval`: 0 when it lies between the bounds, otherwise the distance to the nearest bound.

All 60 actuals are above the upper bound. None are inside. None are below the lower bound.

| Distance outside (¢/kWh) | Value |
| --- | ---: |
| Minimum | 0.044 |
| Median | 1.368 |
| Mean | 1.556 |
| Maximum | 4.269 |

The closest miss is Ohio, target 2025-07: actual 11.50, upper bound 11.46, distance 0.044. That single case is a narrow miss. It is not the typical case. The median actual is 1.37 ¢/kWh above the upper bound, and the farthest (Maryland, 2026-02) is 4.27 above it.

Mean and median distance outside by state:

| State | Mean | Median | Above upper | Below lower |
| --- | ---: | ---: | ---: | ---: |
| MD | 1.651 | 1.417 | 12 | 0 |
| NJ | 1.359 | 1.340 | 12 | 0 |
| OH | 1.733 | 1.935 | 12 | 0 |
| PA | 1.565 | 1.286 | 12 | 0 |
| VA | 1.472 | 1.203 | 12 | 0 |

Coverage is 0% because every actual landed above the upper bound, usually by more than a cent per kWh, not because the intervals were slightly wide of a two-sided scatter. The interval rule is unchanged.

## Ridge versus seasonal naive, case by case

Overall MAEs differ by only 0.0248 ¢/kWh. At the case level the comparison is split:

| | Count |
| --- | ---: |
| Ridge absolute error lower | 30 |
| Seasonal absolute error lower | 30 |
| Tie | 0 |

Mean case-level advantage (seasonal absolute error minus Ridge absolute error) is −0.0248 ¢/kWh, the same gap as the MAE difference. The median case-level advantage is +0.016 ¢/kWh, so the typical case is a very small Ridge win. The mean is negative because the seasonal wins add up to slightly more: the positive advantages sum to +11.38 ¢/kWh and the negative advantages sum to −12.87 ¢/kWh.

Twelve cases favor Ridge by more than 0.5 ¢/kWh, and twelve favor the seasonal naive by more than 0.5. The largest Ridge win is New Jersey, target 2026-04: Ridge absolute error 1.669 versus seasonal 2.650 (advantage +0.981). The largest Ridge loss is Virginia, target 2025-11: Ridge 2.628 versus seasonal 1.510 (advantage −1.118).

The FAIL is not a few large Ridge losses alone, and it is not a uniform small loss on every case. Wins and losses are equal in count and similar in total size, and the losses are slightly larger. That small net gap is the entire difference between 2.638473 and 2.613667. It is far from the +10% threshold.

## Alpha, descriptive only

Alpha 100 was selected at two origins (2024-07-31 and 2025-06-30), ten cases. Alpha 10 was selected at the other ten origins, fifty cases.

| Selected alpha | Cases | Ridge MAE | Seasonal MAE | Mean signed error | Underpredictions |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10 | 50 | 2.690 | 2.633 | 2.690 | 50 |
| 100 | 10 | 2.383 | 2.519 | 2.383 | 10 |

Both groups are entirely underpredictions. The alpha-100 slice has a lower Ridge MAE here. That slice is two specific origins, the first and the last, not a sample of penalty quality. This comparison is not a reason to prefer either penalty. The penalty procedure stays frozen.

## Limitations

The case file is the scored 60-cell grid only. Development residual percentiles are absent because those rows were never stored. Month-to-month correlations of changes are not reported as findings; with eleven changes per state they are too thin to carry the description above. No external series was joined. No chart is attached.

## Closed experiment

None of these findings may be used to revise the closed primary experiment. They do not authorize another holdout run, a new feature, a new penalty, a new model, a changed baseline, a changed 10% threshold, or a changed interval rule. A later confirmatory forecast would need a new evaluation design and new untouched data.
