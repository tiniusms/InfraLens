# POST-HOC EXTERNAL EVIDENCE — NOT USED FOR MODEL SELECTION

This note asks what public events line up with the closed EIA commercial-price holdout. It is post-hoc interpretation only. It is prohibited from informing the closed model, the feature set, the penalty, the baseline, the interval rule, or the final-holdout evaluation. It does not rescore that holdout, change Ridge, change the seasonal-naive baseline, or add a feature.

The scored result remains the one recorded on 2026-10-04 from runner commit `ee5bcf6d541a1b15822f705e4099320f6f05dc32`. Summary: `docs/final_eia_holdout_oneshot.json`. Error description this note relies on: `docs/final_eia_holdout_posthoc_analysis.md`. Protocol: `EVALUATION.md`. PJM geography and vintage rules: `docs/pjm_ltlf_inventory.md` and `docs/pjm_screening_schema.md`.

Pages below were read on 2026-10-14. Quotations and figures are from those pages. A figure computed in this note is labeled as arithmetic on published numbers.

Two separations run through every section.

An **observed event** is a date, price, or institutional action the cited page states. An **interpretation** is a proposed link from that event to the 60 holdout errors. The link is not an event.

A **wholesale** price here is a PJM capacity price in dollars per MW-day, a wholesale energy or uplift cost, or a Henry Hub natural-gas spot price. The holdout target is a **state-level monthly commercial retail** price in cents per kWh from EIA retail sales, sector COM, for MD, NJ, OH, PA, and VA. Those are different objects. A utility default-service rate for one customer class is a third object. It is not the statewide commercial series. A zonal wholesale clearing price is also not the net charge to load in a constrained area: the 2025/2026 auction report allocates Capacity Transfer Rights as a credit to load-serving entities there.

Three labels are kept apart. A **documented event** is what a source states. A **plausible retail mechanism** is a path by which that event could reach a bill. An **unmeasured causal contribution** is the absence of any measurement of that path in the 60 holdout errors.

## Research question

After the holdout had already failed, which external events are aligned in time and geography with the underprediction, which of those events were public at the forecast origin, and which proposed explanations of the errors survive contact with the sources?

The question is interpretive. It is not a confirmatory test and it is not a search for a new model.

## Holdout facts

These facts are copied from the tracked summary and the post-hoc error note. This memo did not reopen `data/processed/final_holdout/final_holdout_cases.parquet` and did not refit anything.

- Primary criterion: **FAIL**. Ridge MAE 2.638473 ¢/kWh. Paired availability-adjusted seasonal-naive MAE 2.613667 ¢/kWh. Improvement −0.9491% against a threshold of at least +10%. Attempted 60, scored 60, every skip count 0.
- State paired improvement, descriptive only, 12 cases each: MD +6.18%, NJ +14.23%, OH −10.59%, PA −0.10%, VA −31.90%.
- Ridge underpredicted all 60 cases. The seasonal naive did too. There is no overprediction.
- State Ridge mean signed errors (¢/kWh): MD 3.3855, NJ 2.7261, OH 2.3859, PA 2.3448, VA 2.3500.
- Five-state mean actuals stay near 13.4–13.6 ¢/kWh from 2025-07 through 2025-12, then 14.87 in 2026-01 and 15.51 in 2026-02, and remain above the autumn level through 2026-06.
- Over those same months the five-state mean Ridge forecast stays near 11.2–12.0 and the seasonal-naive mean stays near 11.3–11.7. The largest Ridge misses cluster in January and February 2026, especially Maryland (5.27 and 5.32) and Virginia in February (5.14). Ohio’s errors grow from 0.70 in 2025-07 to 3.70 in 2026-02. New Jersey’s high actual is 2025-08, not early 2026.
- Interval coverage is 0%. All 60 actuals are above the upper bound.
- Origins are month-ends from 2024-07-31 through 2025-06-30. The target is the commercial price 12 months later, 2025-07 through 2026-06.
- Features are only `eia_commercial_price_v1`. PJM, weather, fuel, tariffs, and data-center load are not in the model.
- Extract: `eia_retail_sales_monthly_com_20260911T190524Z.parquet`, retrieved 2026-09-11. The evaluation is a publication-lag-constrained current-vintage backtest. Later revisions can already be inside that extract.

## Temporal alignment

The locked rule sets `assumed_available_at` for EIA month *m* to the first day of month *m+3*. An origin may use an EIA row only when that date is on or before the origin. Applying that rule to the locked origin list, without rescoring:

| Origin | Target | Latest EIA month the rule can show this origin |
| --- | --- | --- |
| 2024-07-31 | 2025-07 | 2024-04 |
| 2024-08-31 | 2025-08 | 2024-05 |
| 2024-09-30 | 2025-09 | 2024-06 |
| 2024-10-31 | 2025-10 | 2024-07 |
| 2024-11-30 | 2025-11 | 2024-08 |
| 2024-12-31 | 2025-12 | 2024-09 |
| 2025-01-31 | 2026-01 | 2024-10 |
| 2025-02-28 | 2026-02 | 2024-11 |
| 2025-03-31 | 2026-03 | 2024-12 |
| 2025-04-30 | 2026-04 | 2025-01 |
| 2025-05-31 | 2026-05 | 2025-02 |
| 2025-06-30 | 2026-06 | 2025-03 |

No holdout origin can see an EIA month from 2025-04 onward. The June 2025 retail month, which is the first month that could contain a rate effective 2025-06-01, becomes available on 2025-09-01. That is after the last origin. The entire target window is unpublished at every origin. That is the training guard already in `EVALUATION.md`.

For a January 2026 target at the 2025-01-31 origin, the same-calendar-month analog has to be a January whose availability date is on or before 2025-01-31. January 2025 is available on 2025-04-01, so it is not eligible. January 2024 is available on 2024-04-01, so it is eligible. This memo did not re-read the stored analog from the case file. The sentence above is the rule, not a new lookup.

External dates fall into two groups.

**Public at every holdout origin.** The PJM 2025/2026 capacity-auction article is dated July 30, 2024, the day before the first origin. The revised 2024 Long-Term Load Forecast file, if stored as the revised artifact, has `vintage_available_at` 2024-02-01 under the screening schema.

**Public only after some or all origins.** The 2025 LTLF listing is 2025-01-24, so it is available from the 2025-01-31 origin onward. The New Jersey BGS release is 2025-02-12, so it is after the origin for target 2026-01 and on or before the origins for targets 2026-02 through 2026-06. The Ohio SSO notice is 2025-04-30. The Dominion fuel-factor hearing notice is 2025-05-12. The 2026/2027 capacity-auction release is July 22, 2025, after the last origin of 2025-06-30, including the origin for target 2026-06. The Maryland bulletin is 2025-09-08. The Dominion biennial order is 2025-11-25. The 2026 LTLF PDF posting is 2026-01-14. The EIA gas note is 2026-01-23. The PJM cold-weather review is 2026-02-06. None of those post-June 2025 documents existed at any forecast origin.

A post-origin event can still be a candidate explanation of why the realized retail series moved. It cannot be described as information the forecast failed to use. An event that was public at the origin was still not an EIA feature. This note does not turn either kind of event into a feature.

## Regional PJM capacity evidence

Observed, from PJM Inside Lines, July 30, 2024:

- The Base Residual Auction procured capacity for the delivery year June 1, 2025 through May 31, 2026.
- The RTO price is $269.92/MW-day. The 2024/2025 auction price stated in the same article is $28.92/MW-day.
- BGE cleared at $466.35/MW-day and Dominion at $444.26/MW-day. PJM says those two zones cleared at the zonal cap because of insufficient resources inside the regions and transmission limits on imports. The article names Baltimore Gas and Electric, and Dominion in Virginia and North Carolina.
- PJM’s stated drivers are fewer supply offers, mainly generator retirements (about 6,600 MW retired or with must-offer exceptions relative to the prior auction), a higher peak-load forecast (150,640 MW to 153,883 MW), and FERC-approved market reforms. The fetched article does not use the words “data center.”
- PJM says the capacity market is one of several wholesale markets and that the day-ahead and real-time energy markets account for the majority of total costs.
- The cleared auction quantity is 135,684 MW, plus 10,886 MW of Fixed Resource Requirement, 146,570 MW in total. The reserve margin is 18.5%, compared with 20.4% for the prior delivery year.
- The next auction, for 2026/2027, is described as scheduled for December 2024. This July 30, 2024 article does not report that later price.

The 2025/2026 delivery year in that article is June 1, 2025 through May 31, 2026. It covers holdout targets 2025-07 through 2026-05. It does not cover target 2026-06.

The 2025/2026 Base Residual Auction Report, dated July 30, 2024, prints the same resource clearing prices in its price table: RTO $269.92/MW-day, BGE $466.35/MW-day, DOM $444.26/MW-day. The locational price adders in that table are $196.43/MW-day for BGE and $174.34/MW-day for DOM, each added to a system marginal price of $269.92/MW-day. One sentence in the report says RTO, EMAAC, SWMAAC, and MAAC cleared at $269.97/MW-day. The price table, the July 30, 2024 news release, and the July 22, 2025 release all state $269.92/MW-day. This memo uses $269.92.

That report also documents Capacity Transfer Rights for the constrained areas:

> Since BGE and DOM were constrained LDAs, Capacity Transfer Rights (CTRs) will be allocated to loads in these constrained LDAs for the 2025/2026 Delivery Year. CTRs are allocated by load ratio share to all Load Serving Entities (LSEs) in a constrained LDA that has a higher clearing price than the unconstrained region. CTRs serve as a credit back to the LSEs in the constrained LDA for use of the transmission system to import less expensive capacity into that constrained LDA and are valued at the difference in the clearing prices of the constrained and unconstrained regions.

The gross zonal clearing price is the auction result. The CTR is a wholesale credit to LSEs in BGE and DOM, valued at that locational difference, for delivery year 2025/2026. It is not a net end-customer retail charge. The report does not say how much of the credit, if any, an LSE passed through to a commercial customer, or in which billing month.

Observed, from PJM’s July 22, 2025 news release:

- The announcement date on the release is July 22, 2025.
- The 2026/2027 Base Residual Auction price “came in at the FERC-approved cap, $329.17/MW-day (UCAP), for the entire PJM footprint.”
- The same release compares that price with $269.92/MW-day for the 2025/2026 RTO result, and with $466.35/MW-day in BGE and $444.26/MW-day in Dominion.
- The release says wholesale capacity is a relatively small portion of retail bills. It says PJM would expect the cap price to translate to a year-over-year increase of 1.5–5% in some customers’ bills, depending on how load-serving entities and states pass wholesale costs through. It also says prices decreased in two zones and that consumers in some areas could see a drop in retail rates. Those sentences are PJM’s expectation. They are not a measurement of the EIA commercial series.
- The cleared quantity in this release is 134,311 MW UCAP, plus 11,933 MW UCAP under the Fixed Resource Requirement.
- Forecasted peak load for the 2026/2027 Delivery Year “increased year to year by more than 5,400 MW, driven largely by data center expansion, electrification and economic growth.”

The July 22, 2025 PDF labels the price as the 2026/2027 Delivery Year. It does not print the calendar endpoints “June 1, 2026” or “May 31, 2027.” The July 30, 2024 release defined the prior delivery year as June 1, 2025 through May 31, 2026. Under that June-through-May convention, the 2026/2027 delivery year is June 1, 2026 through May 31, 2027. June 2026 is then the first month of the new delivery year. May 2027 is outside the holdout.

Three dates therefore stay separate. The **announcement date** is July 22, 2025. The **delivery window**, by the convention above, is June 2026–May 2027. The **holdout relevance** is the five state cells for target 2026-06 only. The other 55 cells sit in the 2025/2026 delivery year. The forecast origin for 2026-06 is 2025-06-30, twenty-two days before the announcement, so $329.17/MW-day was not public when that forecast was made. For BGE and Dominion, $329.17 is below the 2025/2026 zonal prices printed in the same release.

Maryland’s Office of People’s Counsel, on September 8, 2025, describes the same auction as an “800 percent” price spike and says those costs hit retail supply charges on utility-specific schedules during the 2025–26 delivery year. That percentage is OPC’s characterization. The prices to cite are PJM’s two figures above. OPC also says a pending federal complaint could produce refunds. No refund outcome is in the bulletin.

Interpretation, kept separate from the observation: the 2025/2026 wholesale capacity price is a documented event, public before every origin, overlapping eleven target months. A retail pass-through is a plausible mechanism and an unmeasured contribution to the commercial series. The gross BGE and Dominion clearing prices are the wrong object for that mechanism, because CTRs credit LSEs for the locational gap. The 2026/2027 price is a second documented event. It can be relevant only to the June 2026 target, it was announced after that target’s origin, and its contribution to the June 2026 commercial prices is unmeasured.

## January–February 2026 weather and fuel evidence

Observed, from PJM Inside Lines, February 6, 2026:

- PJM describes the strongest sustained cold on its system since the 1990s.
- Temperatures across the footprint stayed below freezing from January 16–21, 2026. Winter Storm Fern followed. A more severe arctic period ran January 23 through February 2.
- From January 26–30, temperatures were warmer than widely accepted forecasts, and closures reduced demand. PJM did not set a record peak. Hourly winter peak load was 130 GW or higher for eight consecutive days, January 26 through February 2, including two of the ten highest winter peaks in preliminary figures.
- Gas and electric scheduling were misaligned. PJM reports about $798 million in preliminary out-of-market uplift from January 24 through February 1.
- Generation outages averaged 18–19 GW during Fern and its aftermath, against a seasonal winter projection of 15.9 GW and against about 12–13 GW in the January 2025 cold spell. PJM’s January 2025 hourly peak, stated in this article, was 143.9 GW.
- A Department of Energy order allowed 15 generators to run beyond environmental permits, for 1,035 run hours and 5.2 GW. A second DOE order would have allowed PJM to direct data centers and other large loads onto backup generation. PJM says it did not implement that order. The order expired February 2.
- Several of these operating figures are labeled preliminary.

Observed, from EIA Today in Energy, January 23, 2026:

- Henry Hub daily spot natural gas reached nearly $8.15 per million Btu on January 22.
- EIA’s sentence is: “Higher wholesale natural gas prices generally contribute to higher wholesale electricity prices.”
- Mid-January storage was about 6% above the previous five-year average. The article says the early-February storage report would show withdrawals ahead of the cold snap, so that withdrawal was not yet in this article.
- The piece points to NOAA messages dated January 22 and to EIA dashboards. It does not report a PJM power price, a state retail price, or a February price.

The holdout’s five-state mean actual moves from 13.52 in December 2025 to 14.87 in January 2026 and 15.51 in February 2026, then remains elevated. That calendar overlap is real. The gas article is dated January 23, inside the storm window and before February’s retail month has closed. The PJM review is dated February 6, after January’s retail month and during February.

Interpretation: these sources document a wholesale and operational stress episode in late January and early February 2026. They do not measure how much of any state’s monthly commercial retail price moved because of it. EIA’s general sentence is about wholesale electricity, not about the COM series. Retail fuel and purchased-power factors often settle on a later cycle. The July–December 2025 underprediction is already present before this weather. In the post-hoc table the five-state Ridge MAE in those months runs from 2.042 to 2.335 ¢/kWh.

None of this was knowable at a forecast origin. The last origin is 2025-06-30.

## State-specific retail mechanisms

### Maryland

Observed, from the Office of People’s Counsel bulletin sent September 8, 2025:

- OPC says most Maryland customers can expect higher electric bills in fall 2025 than in fall 2024, and attributes the increase to the 2024 PJM capacity auction for the delivery year June 1, 2025 through May 31, 2026.
- The costs are in the supply portion of utility bills, on different schedules. SMECO beginning June. Pepco and Delmarva Power beginning August. Potomac Edison beginning October.
- For BGE, a Public Service Commission order sought to keep the higher costs out of summer and winter. OPC says BGE customers see them in September–November 2025 and March–May 2026. OPC’s estimate for a typical BGE customer is about $30 on monthly bills in those six months, versus about $16 if the same delivery-year cost were spread over twelve months. Other monthly estimates, if spread over twelve months, are about $18 for Potomac Edison, $16 for BGE, $14 for Pepco and SMECO, and $4 for Delmarva.
- OPC says the exclusion of the Brandon Shores and Wagner reliability-must-run plants increased auction results by as much as $5 billion, “as documented in OPC’s report.” This memo did not retrieve that report.
- OPC says one Independent Market Monitor scenario attributed $9.3 billion of an approximate $12.5 billion auction-cost increase to data centers. This memo did not retrieve the Monitor’s scenario.
- OPC represents residential consumers. The dollar figures are described as monthly bill effects. They are not commercial cents per kWh.

Maryland’s scored commercial series peaks in January 2026 at 18.19 ¢/kWh. Ridge’s largest misses are January and February 2026 (5.27 and 5.32). OPC’s BGE schedule puts the extra residential capacity cost outside the winter. A BGE residential winter capacity adder therefore does not line up with Maryland’s largest commercial misses. July 2025 is already a 2.73 ¢/kWh Ridge underprediction, before Pepco, Delmarva, Potomac Edison, and BGE’s fall windows as OPC dates them. SMECO’s June start could overlap July. That is one utility’s residential timing, not a statewide commercial measurement.

### New Jersey

Observed, from the Board of Public Utilities release dated February 12, 2025:

- The 24th Basic Generation Service auction ran February 7–10, 2025. The Board says the results mean higher supply costs for most residents and many small and medium-sized businesses served by the four regulated distribution companies, effective for a 12-month period starting June 1, 2025.
- The residential bill table, at 650 kWh, shows estimated increases of 17.23% (ACE), 20.20% (JCP&L), 17.24% (PSE&G), and 18.18% (RECO). That table is residential.
- The RSCP auction, for residential and small- to medium-sized commercial customers, covers one-third of that load for three energy years starting June 1, 2025. The other two-thirds of the year starting June 1, 2025 come from the 2023 and 2024 auctions. Closing prices for the new tranche are 11.050 (ACE), 11.096 (JCP&L), 10.736 (PSE&G), and 11.615 (RECO) cents/kWh.
- The CIEP auction, for large commercial and industrial customers, is a one-year product. Its auction price covers capacity and the renewable standard. Energy is priced at the spot price. CIEP closing prices are 605.22 (ACE), 625.21 (JCP&L), 696.05 (PSE&G), and 566.54 (RECO) dollars per MW-day. The Board says that as of June 2024, about 82.53% of CIEP load was on third-party contracts not affected by this auction, and that the CIEP auction price is a small portion of those customers’ bills.
- The Board names PJM’s capacity auction, demand growth including data centers, interconnection delays, and market rules as context. Those sentences are the Board’s attribution.

New Jersey’s EIA commercial price is 18.36 in July 2025 and 18.47 in June 2026, with the maximum in August 2025 (18.68) and the minimum in November 2025 (15.91). The winter peak seen in the other four states is not New Jersey’s peak. The RSCP tranche prices are not all-in retail rates, and they are not the statewide commercial average. The residential percentage increases are not commercial cents per kWh.

The February 12 release is after the 2025-01-31 origin (target 2026-01) and before the origins for targets 2026-02 through 2026-06. No origin sees the June 2025 EIA month.

### Ohio

Observed, from the PUCO page published April 30, 2025. A non-browser fetch of the URL returned 404, and a plain HTTP request returned 403. The text below was read in a browser from the same URL on 2026-10-14. The page’s own “Published” field is April 30, 2025.

- A new AEP Ohio standard-service-offer rate takes effect June 1, 2025 for customers who are not in a government aggregation and not enrolled with a competitive supplier.
- “Rates for residential customers will rise by nearly 2 cents per kilowatt hour (kWh) to $0.0997 per kWh.”
- PUCO describes the standard-service offer as the default price of energy, from wholesale auctions, passed through with no utility profit.
- The price-to-compare instructions in the release are addressed to residential customers.
- The release states no commercial cents-per-kWh figure.

Ohio’s smallest Ridge miss is July 2025 (0.70 ¢/kWh), the first holdout month after June 1. The misses then rise through February 2026 (3.70). The July EIA commercial price is 11.50 ¢/kWh. The published $0.0997/kWh figure is a residential generation default rate. It is not the statewide commercial all-in price, and the release does not give the commercial counterpart. Ohio commercial prices continue up after July, to 14.30 in February 2026.

### Pennsylvania

Observed, from PPL Electric Utilities’ June 2025 Business Connect page:

- The business default Price to Compare is 12.114¢/kWh, up from 10.446¢/kWh, effective June 1, 2025. PPL calls this the main driver of a nearly 16% increase in the Price to Compare.
- PPL attributes the generation-supply increase to retirements and limited new generation in Pennsylvania and the broader region, and to expected demand growth over the next decade. The page does not use the words “data center.”
- PPL says it does not generate electricity, earns no profit on this supply charge, and controls about half of a bill. The other half includes generation supply, mandates, and taxes.
- The page tells business customers they can shop. It does not say what share of Pennsylvania commercial load is on this Price to Compare.

The page is the June 2025 issue. It does not print a day. Whether that page existed before the 2025-06-30 origin is unresolved. The effective date it states is June 1, 2025.

Pennsylvania’s EIA commercial price is 12.63 in July 2025 and peaks at 14.86 in February 2026. Ridge’s February miss is 4.04 ¢/kWh. July’s miss is 1.47. A single June 1 default Price to Compare for PPL business customers on default service can be one input to PPL bills. It is not the statewide commercial series, and a rate that steps once on June 1 does not, by itself, account for a further February peak in that statewide series. This memo does not have the later monthly Price to Compare path.

### Virginia

Two SCC releases, and they say different things.

Fuel-factor hearing notice, May 12, 2025, case PUR-2025-00059:

- The SCC set a hearing on Dominion Energy Virginia’s application to increase its fuel factor for usage on and after July 1, 2025.
- Dominion requests recovery of about $1.958 billion of estimated Virginia jurisdictional fuel, energy-related, and purchased-power capacity-related expenses for the fuel year July 1, 2025 through June 30, 2026, plus a projected June 30, 2025 unrecovered balance of $204.5 million.
- The application proposes to shift purchased capacity expense from base rates to the fuel factor beginning January 2026.
- The public witness hearing is September 2, 2025, together with biennial-review case PUR-2025-00058.

This page is a hearing notice. It does not state an approved cents-per-kWh factor. The outcome of PUR-2025-00059 was not in this source and was not retrieved elsewhere for this memo.

Biennial-review order, November 25, 2025, case PUR-2025-00058:

- The SCC approved a new GS-5 rate class for customers demanding 25 MW or more, including data centers. GS-5 is effective January 1, 2027.
- Large-scale customers in that design pay at least 85% of contracted distribution and transmission demand and 60% of generation demand, among other requirements. The release’s purpose statement is to insulate other ratepayers from infrastructure built for these users.
- The SCC rejected Dominion’s requested base-rate increases of $822 million in 2026 and $345 million in 2027. It approved $565.7 million in 2026 and $209.9 million in 2027.
- The residential illustration is $11.24 per month in 2026 and $2.36 per month in 2027. The release does not state a commercial cents-per-kWh effect or the month in 2026 when the base-rate change takes effect.
- Authorized return on equity moves from 9.7% to 9.8%.

GS-5 begins January 1, 2027. The holdout window ends June 2026. The class cannot be a price in the scored months. Virginia’s largest Ridge miss is February 2026 (5.14 ¢/kWh), before both the GS-5 effective date and, relative to the forecast, after every origin. The November 25 order itself is after every origin.

The proposed January 2026 capacity shift inside the fuel-factor application coincides on the calendar with Virginia’s large winter misses. Coincidence is not approval, and approval is not in the May 12 source.

## Large-load and data-center context

Observed statements, each tied to the page that makes them:

- PJM’s July 30, 2024 auction article states higher peak load and tighter supply. It does not say data centers.
- PJM’s July 22, 2025 release says the 2026/2027 peak-load forecast rose by more than 5,400 MW, “driven largely by data center expansion, electrification and economic growth.” That sentence is about the later delivery year’s forecast. It was published after every holdout origin.
- The New Jersey Board, on February 12, 2025, says demand growth driven by data centers and other factors contributed to the capacity-cost increase that fed the BGS result. That is the Board’s attribution, not a table of statewide commercial prices.
- Maryland OPC, on September 8, 2025, reports one Market Monitor scenario in which data centers account for $9.3 billion of an approximate $12.5 billion increase in auction cost. The scenario document was not retrieved. OPC also says data centers can be built faster than generation.
- PJM’s February 6, 2026 review says the DOE backup-generation order for data centers and other large loads was not used.
- The Virginia GS-5 class for demand of at least 25 MW is effective January 1, 2027.
- The screening inventory already dates the 2026 load-forecast PDF to January 14, 2026, the 2025 vintage to January 24, 2025, and the revised 2024 file to February 1, 2024. Those files are zonal and RTO peaks, not state retail prices. The schema forbids joining them to `state_id`.

A data-center load adjustment in a zonal forecast is evidence about where PJM is embedding peak risk. It is not evidence that the adjustment changed the EIA commercial price in a state that overlaps the zone. Dominion is not Virginia-only. BGE is the Maryland-aligned zone that also cleared at the capacity cap. AEP, APS, DPL, and others cross state lines. That many-to-many overlap is already in the screening schema.

## Competing explanations

Each row is a proposed explanation of the holdout errors. The event and the contribution are classified separately in the next section. The labels mean:

- **Supported.** The cited source states it, and the statement does not require an extra inferential step. For a contribution to the errors, supported would require a measurement of that contribution in the statewide commercial series. None of these sources contain that measurement.
- **Plausible but unproven.** Timing or institutional design makes a connection possible, and the sources do not measure it.
- **Unsupported.** The connection conflicts with the source’s dates, customer class, or geography, or the source is a request rather than an effect.

In those labels, **supported** on the event side is a documented event. **Plausible but unproven** is a plausible retail mechanism whose effect on the 60 errors is unmeasured. **Unsupported** means the proposed contribution conflicts with the source. No external event has a measured causal contribution to the errors.

| ID | Proposed explanation of the errors |
| --- | --- |
| E1 | Both forecasts are low because the protocol predicts a retail level 12 months ahead from EIA months that stop well before the target, so any later level shift shows up as underprediction for Ridge and for the seasonal naive. |
| E2 | The 2025/2026 wholesale capacity price was passed through into the five statewide commercial series and produced the underprediction. |
| E2b | The July 22, 2025 price of $329.17/MW-day produced the June 2026 commercial prices. |
| E3 | The January–February 2026 cold spell and the Henry Hub spike produced the January–February retail jump. |
| E4 | New Jersey’s BGS results explain the New Jersey EIA commercial path. |
| E5 | PPL’s business Price to Compare explains the Pennsylvania EIA commercial path. |
| E6 | AEP Ohio’s residential standard-service offer explains the Ohio EIA commercial path. |
| E7 | BGE’s capacity-cost recovery explains Maryland’s January–February commercial spike. |
| E8 | Dominion’s fuel-factor application, including the proposed January 2026 capacity shift, explains Virginia’s February miss. |
| E9 | The new GS-5 large-user class explains Virginia’s holdout misses. |
| E10 | Data-center demand explains the 60 commercial-price errors. |

E1 is a description of the scored path plus the locked rule. It does not name the external cause of the higher retail level. It does account for the fact that Ridge and the seasonal naive fail together, in every state, in every month.

E2 accounts for a wholesale price that was public early and that covers eleven target months. It does not account for Ohio, Pennsylvania, and New Jersey moving with Maryland and Virginia even though only BGE and Dominion cleared at the zonal cap. It does not account for Capacity Transfer Rights, which credit LSEs in those two zones for the locational gap, so the gross zonal price is not a net charge to load. It does not account for Maryland’s largest misses falling in the winter months OPC says were excluded for BGE residential capacity recovery. It does not cover June 2026.

E2b uses the price that does cover June 2026. The announcement is July 22, 2025. The delivery window, under the June-through-May convention of the prior release, is June 2026–May 2027. Only the five June 2026 cells are inside both that window and the holdout. The origin for those cells is June 30, 2025. In BGE and Dominion the new price is below the prior zonal price. PJM’s 1.5–5% bill remark is an expectation about some customers, not a result for the EIA series.

E3 accounts for the months when the five-state mean is highest. It does not account for the July–December 2025 underprediction, whose five-state Ridge MAE runs from 2.042 to 2.335 ¢/kWh in the post-hoc table. It was unknowable at the origins.

E4–E6 are real default-service changes for named classes and, in Pennsylvania and Ohio, named utilities. Each forbids the inference that the named tariff is the statewide commercial series. New Jersey’s own path does not peak in the winter. Ohio’s smallest miss is the first month after the June 1 residential change. Pennsylvania’s February peak is a second movement after a June 1 step.

E7 conflicts with the BGE winter exclusion in the same bulletin that documents the capacity cost.

E8 is an application and a hearing date. The approved factor is not in the source.

E9 is an order whose effective date is after the holdout window, for customers at or above 25 MW.

E10 mixes a documented demand narrative with an unmeasured retail effect. The July 30, 2024 article’s demand evidence is a peak-load forecast increase, and that article does not say data centers. The July 22, 2025 release does say data center expansion, for the 2026/2027 peak-load increase, after every origin. The New Jersey release and OPC’s report of a scenario also discuss data centers. The January 2026 backup-generation order was not used. GS-5 is not yet in effect.

## Evidence classification

| ID | Underlying event or mechanism | Contribution to the 60 statewide commercial errors |
| --- | --- | --- |
| E1 | Supported, as a description of the locked origin rule and the already scored path | Supported as a mechanical description of why both forecasts can miss a later level. It does not identify which external event set that level. |
| E2 | Documented event: the 2025/2026 prices, the June 1, 2025–May 31, 2026 delivery year, the BGE and Dominion caps, and the CTR credit to LSEs | Plausible retail mechanism, unmeasured contribution. The gross zonal price is not the net wholesale charge to load, and neither figure is the commercial retail series. The caps are narrower than the misses. |
| E2b | Documented event: $329.17/MW-day UCAP for the entire footprint, announced July 22, 2025, for the 2026/2027 Delivery Year | Plausible retail mechanism only for the five June 2026 cells, and unmeasured there. Unsupported for the other 55 cells. The price was not public at the June 30, 2025 origin. |
| E3 | Supported for the operational cold period, the preliminary uplift, and the January 22 Henry Hub print | Plausible but unproven for the January–February retail months. Unsupported as an explanation of the July–December misses. |
| E4 | Supported for the BGS auction, the June 1, 2025 effective date, and the residential and RSCP/CIEP figures the Board published | Unsupported as an explanation of the statewide commercial series. Plausible but unproven as a partial input to the subset of New Jersey load that is actually on BGS-RSCP. |
| E5 | Supported for PPL’s business default Price to Compare on June 1, 2025 | Unsupported as an explanation of the statewide commercial series. Plausible but unproven for PPL default-service business customers. |
| E6 | Supported for the AEP Ohio residential standard-service offer of $0.0997/kWh on June 1, 2025 | Unsupported as an explanation of the statewide commercial series. The release states no commercial rate. The error path grows after July rather than stepping there. |
| E7 | Supported for OPC’s description of residential bill timing, including the BGE winter exclusion | Unsupported for the January–February Maryland commercial spike. Other utilities’ earlier start dates are plausible but unproven, and they are still residential dollar estimates. |
| E8 | Supported as the contents of an application and a hearing notice | Unsupported. The cited page does not approve a factor or a January 2026 shift. |
| E9 | Supported for the November 25, 2025 order and the January 1, 2027 effective date | Unsupported. The class is outside the holdout window and outside the statewide commercial average. |
| E10 | Documented that the July 30, 2024 article raised the peak-load forecast without saying data centers; that the July 22, 2025 release attributes the later peak-load increase largely to data center expansion, electrification, and economic growth; and that New Jersey and OPC discuss data centers. The $9.3 billion scenario was not independently retrieved | Plausible mechanism for wholesale capacity cost. Unmeasured as a cause of these commercial retail errors. |

“Supported” in the event column means the source says the thing happened or says the number. “Supported” in the contribution column is used only for E1, and only for the mechanical lag. No external event has a supported causal contribution to the errors.

## Limitations

- The case file was not reopened. Analog months implied by the availability rule were not confirmed against stored columns.
- The EIA extract is current-vintage as of 2026-09-11. How much of each holdout actual is a later revision is unknown.
- No source here decomposes the EIA commercial price into energy, capacity, transmission, distribution, fuel riders, and shopping versus default service.
- Dominion fuel-factor case PUR-2025-00059 has no final order in the sources read. The month when the approved 2026 Dominion base-rate change takes effect is not stated.
- The Market Monitor scenario cited by OPC was not retrieved. OPC’s own underlying bill-impact report was not retrieved.
- The July 22, 2025 release does not print “June 1, 2026” or “May 31, 2027.” Those endpoints are the June-through-May convention from the July 30, 2024 delivery-year sentence, applied to the 2026/2027 label.
- How LSEs applied Capacity Transfer Rights on retail bills, and whether the $329.17/MW-day cap reached commercial customers in June 2026, is not in either PJM document.
- One sentence in the 2025/2026 auction report says $269.97/MW-day where the price table says $269.92/MW-day. This memo follows the table.
- PPL’s newsletter has no day-level publication date. Commercial standard-service prices for AEP Ohio, BGE, Pepco, Delmarva, Potomac Edison, and Dominion are not in these releases.
- PJM’s February 6 figures that the article marks preliminary are preliminary here too.
- Inside Lines and agency pages can be edited in place. This note records the text retrieved on 2026-10-14.
- Month-to-month correlations were already declined in the error note. They are not added here.
- Nothing in this note is a historical feature, a license to rerun `python -m infralens.evaluation.final_holdout`, or a reason to retune.

## Implications for the separate PJM screening layer

The screening layer remains a zonal display. It does not join to the EIA model, does not allocate MW or capacity prices onto `state_id`, and does not reopen the holdout.

What this evidence changes about that layer is the vintage test, not the model:

- The July 30, 2024 capacity result, including the BGE and Dominion separation from the RTO price, was public at every holdout origin. A screening card may show it beside a state page as a wholesale reliability-price fact, with the delivery year and the zone names, and with the CTR credit stated beside the gross zonal price. It may not be labeled as the state’s commercial retail price, as a net charge to end customers, or as the cause of the holdout miss.
- The July 22, 2025 announcement of $329.17/MW-day is after every holdout origin. A view as of 2025-06-30 must not show it. A later view may show it as the wholesale price for the 2026/2027 Delivery Year, including the June 2026 target month under the June-through-May convention, and must not present it as the June 2026 commercial retail price. In BGE and Dominion that price is below the prior zonal clearing price.
- The 2024 revised load forecast is usable, under the existing `vintage_available_at` of 2024-02-01, at every holdout origin. The 2025 vintage is usable from 2025-01-24. The 2026 vintage, posted 2026-01-14, is not usable at any holdout origin. The July 22, 2025 capacity release, the September 8, 2025 Maryland bulletin, the November 25, 2025 Virginia order, the January 23, 2026 gas note, and the February 6, 2026 operations review are likewise after every origin.
- Large-load and data-center fields already specified in the screening schema stay zonal. The unused DOE backup-generation order and the 2027 GS-5 class are context that the large-load issue was live. They are not 2025–26 retail prices.
- Utility default-service rates belong in a tariff source register if they are collected later. They stay out of both the EIA feature matrix and the zonal screening table. One utility’s residential or business default rate is not a state commercial series.
- A screening view that shows only information with `vintage_available_at` or publication date on or before the selected origin will not “explain” the January–February 2026 retail jump with documents that did not yet exist. That is the correct behavior.

## Source register

Retrieved 2026-10-14. Each row separates the evidence publication date from the delivery or effective date. Customer class is “not an end-use class” when the source is wholesale.

| Evidence publication date | Organization | URL | Applicable delivery or effective date | Geographic coverage | Customer class | Exact claim supported |
| --- | --- | --- | --- | --- | --- | --- |
| July 30, 2024 | PJM Interconnection, Inside Lines | https://insidelines.pjm.com/pjm-capacity-auction-procures-sufficient-resources-to-meet-rto-reliability-requirement/ | Delivery year June 1, 2025–May 31, 2026. June 2026 is outside this delivery year | RTO price, plus zonal caps for BGE (Maryland) and Dominion (Virginia and North Carolina) | Not an end-use class. Wholesale capacity | RTO $269.92/MW-day versus $28.92/MW-day in the prior auction; BGE $466.35/MW-day; Dominion $444.26/MW-day; peak-load forecast 150,640 MW to 153,883 MW; about 6,600 MW retired or with must-offer exceptions; energy markets are most of total cost. Does not report the 2026/2027 price and does not say “data center.” |
| July 30, 2024 | PJM Interconnection, 2025/2026 Base Residual Auction Report | https://www.pjm.com/-/media/DotCom/markets-ops/rpm/rpm-auction-info/2025-2026/2025-2026-base-residual-auction-report.ashx | 2025/2026 Delivery Year | BGE and DOM locational deliverability areas for the CTR credit; the price table also restates the RTO, BGE, and DOM resource clearing prices | Load-serving entities in the constrained LDAs, allocated by load ratio share. Not an end-use commercial class | Price table: system marginal price $269.92/MW-day; BGE adder $196.43/MW-day and resource clearing price $466.35/MW-day; DOM adder $174.34/MW-day and resource clearing price $444.26/MW-day. CTRs are a credit to those LSEs valued at the difference between the constrained and unconstrained clearing prices. One other sentence in the report says $269.97/MW-day; this memo uses the table. The gross zonal price is not a net end-customer retail charge. |
| July 22, 2025 | PJM Interconnection, news release | https://www.pjm.com/-/media/DotCom/about-pjm/newsroom/2025-releases/20250722-pjm-auction-procures-134311-mw-of-generation-resources-supply-responds-to-price-signal.pdf | 2026/2027 Delivery Year. The PDF does not print June 1, 2026 or May 31, 2027. Under the prior release’s June 1–May 31 convention, that year is June 1, 2026–May 31, 2027, so the only holdout month inside it is 2026-06 | Entire PJM footprint, stated as one price. The release also restates the prior BGE and Dominion prices | Not an end-use class. PJM’s bill sentence is an expectation for “some customers,” depending on LSE and state pass-through | $329.17/MW-day (UCAP) at the FERC-approved cap for the entire footprint. Compared with $269.92/MW-day for the 2025/2026 RTO and with $466.35 and $444.26 in BGE and Dominion. Cleared 134,311 MW UCAP plus 11,933 MW UCAP of Fixed Resource Requirement. Peak load up more than 5,400 MW, driven largely by data center expansion, electrification, and economic growth. Expected retail translation 1.5–5% year over year for some bills; prices decreased in two zones. Announced after the 2025-06-30 origin. |
| February 6, 2026 | PJM Interconnection, Inside Lines | https://insidelines.pjm.com/pjm-reviews-january-cold-weather-operations/ | Operating window January 16–February 2, 2026. Uplift window stated as January 24–February 1 | PJM footprint. Not a state retail series | Not an end-use class | Below-freezing January 16–21; Winter Storm Fern; arctic weather January 23–February 2; preliminary uplift about $798 million; hourly winter peak load 130 GW or higher for eight days; average outages 18–19 GW; DOE large-load backup order not implemented. Preliminary figures. After every forecast origin. |
| January 23, 2026 | U.S. Energy Information Administration | https://www.eia.gov/todayinenergy/detail.php?id=67046 | Henry Hub spot print January 22, 2026. No retail effective date | National Henry Hub benchmark | Not an end-use class | Henry Hub daily spot nearly $8.15/MMBtu on January 22. Higher wholesale gas prices generally contribute to higher wholesale electricity prices. Mid-January storage about 6% above the five-year average. No PJM power price, no February price, and no state retail price. |
| February 12, 2025 | New Jersey Board of Public Utilities | https://www.nj.gov/bpu/newsroom/2025/approved/20250212.html | Supply period starting June 1, 2025. RSCP tranche covers one-third of the relevant load for three energy years and is blended with the 2023 and 2024 auctions. CIEP is one year | New Jersey regulated territories ACE, JCP&L, PSE&G, and RECO | Residential bill table at 650 kWh. RSCP: residential and small- to medium-sized commercial. CIEP: large commercial and industrial, with about 82.53% of that load on third-party contracts as of June 2024 | Residential estimated bill increases 17.23% (ACE), 20.20% (JCP&L), 17.24% (PSE&G), 18.18% (RECO). RSCP closing prices 11.050, 11.096, 10.736, and 11.615 cents/kWh. CIEP closing prices 605.22, 625.21, 696.05, and 566.54 $/MW-day. Not the EIA statewide commercial average. |
| June 2025; day not stated on the page | PPL Electric Utilities | https://www.pplelectric.com/site/More/About-Us/Our-Company/ConnectNewsletter/business/2025/June-2025-Business-Connect | June 1, 2025 | PPL Electric Utilities territory in Pennsylvania | Business customers on the default Price to Compare. Not shoppers | Business default Price to Compare 12.114¢/kWh, up from 10.446¢/kWh. PPL does not profit on generation supply. Not the statewide commercial series. |
| April 30, 2025 | Public Utilities Commission of Ohio | https://puco.ohio.gov/news/puco-alerts-aep-ohio-customers-to-upcoming-price-changes | June 1, 2025 | AEP Ohio | The $0.0997/kWh figure is residential standard-service offer, for customers not on aggregation or a competitive supplier. No commercial rate is stated | Residential rate rises by nearly 2¢/kWh to $0.0997/kWh. Generation default rate, not the all-in retail bill. Text confirmed in a browser on 2026-10-14 after a direct fetch was blocked. |
| September 8, 2025 | Maryland Office of People’s Counsel | https://content.govdelivery.com/accounts/MDOPC/bulletins/3f1b028 | Delivery year June 1, 2025–May 31, 2026. Billing start differs: SMECO June, Pepco and Delmarva August, Potomac Edison October, BGE September–November 2025 and March–May 2026 | Named Maryland utilities: SMECO, Pepco, Delmarva, Potomac Edison, BGE | Residential. OPC represents residential consumers | Monthly residential bill estimates of about $18, $16, $14, and $4 if spread over twelve months, and about $30 for typical BGE customers in the six bridge months. BGE winter is excluded. “800 percent” is OPC’s phrase. The $5 billion and $9.3 billion figures cite documents this memo did not retrieve. |
| May 12, 2025 | Virginia State Corporation Commission | https://www.scc.virginia.gov/about-the-scc/newsreleases/release/scc-to-consider-dominion-fuel-factor-request/scc-sets-hearing-on-dev-fuel-factor-request.html | Requested fuel year July 1, 2025–June 30, 2026. Hearing September 2, 2025. Proposed capacity shift beginning January 2026 | Dominion Energy Virginia jurisdictional customers. Not the rest of Virginia, and not North Carolina load inside the PJM Dominion zone | Class not split in the hearing notice | Application in PUR-2025-00059, not an order. Requested recovery about $1.958 billion plus a $204.5 million deferral. No approved cents-per-kWh factor. |
| November 25, 2025 | Virginia State Corporation Commission | https://www.scc.virginia.gov/about-the-scc/newsreleases/release/scc-issues-order-on-dev-biennial-review-2025/scc-rules-in-dev-biennial-review-case.html | GS-5 effective January 1, 2027. Base-rate dollars labeled 2026 and 2027 without a month | Dominion Energy Virginia | GS-5: customers demanding 25 MW or more, including data centers. The dollar illustration is residential | Order in PUR-2025-00058. Approved base-rate increases $565.7 million in 2026 and $209.9 million in 2027, against requests of $822 million and $345 million. Residential illustration $11.24 per month in 2026 and $2.36 in 2027. Return on equity from 9.7% to 9.8%. GS-5 is after the holdout window. Commercial cents per kWh are not stated. |

## Unresolved questions

- What share of each state’s EIA commercial kWh is default service versus a competitive contract, and for which utility?
- What commercial, as distinct from residential, cents-per-kWh change did AEP Ohio, PPL, the New Jersey EDCs, BGE, Pepco, Delmarva, Potomac Edison, and Dominion actually post, and in which billing month?
- Did the SCC approve PUR-2025-00059, at what factor, and did purchased capacity move into the fuel factor in January 2026?
- In which month of 2026 do Dominion’s approved base rates take effect, and what is the commercial cents-per-kWh effect?
- What does the Market Monitor scenario actually say, and what does OPC’s own bill-impact report assume about consumption and customer class?
- Did load-serving entities pass Capacity Transfer Rights through to commercial end users in 2025–26, and did the $329.17/MW-day price appear in June 2026 commercial retail bills? The wholesale prices are documented. The retail appearance is not.
- How much of the September 11, 2026 EIA extract revises the first publication of each holdout month?
- Which same-calendar-month row is stored on each seasonal-naive holdout case? The rule implies the answer. The case file was not re-read.
