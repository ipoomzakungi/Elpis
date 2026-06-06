
# OI + Options Trading Signal Source Pack V2
## Deep distilled knowledge from option.pdf for future signal automation

Purpose: this document is written as a copy-ready knowledge source for a future session. It does not decide whether the strategy is good or bad yet. It only distills what the source is teaching and converts it into structured knowledge that can later be tested, judged, and automated.

Important note: this is educational research material, not financial advice and not a live trading recommendation. Any automated trading system must be backtested, forward-tested, paper-traded, and protected with risk limits before real money execution.

---

## 0. Is V1 all the data? No.

V1 is not "all data." V1 is a first framework. It captures the main idea that OI/heat-map zones matter and that OI should become part of a signal engine. But V1 is not detailed enough to use as a complete replacement for the source.

What V1 did cover reasonably:

- OI as a zone map, not a simple buy/sell signal.
- The source phrase "big, long, many" (ใหญ่ ยาว เยอะ) as the central OI heuristic.
- The idea that 1 SD / inner zone is the main intraday focus.
- OI Change as fresh positioning that must be compared with current price.
- Block logic such as gold 25/50 behavior and oil 1.0/0.5 zones.
- A first data dictionary for later automation.
- A first automation roadmap.

What V1 missed or treated too lightly:

- The full explanation of what options are, how option boards work, and why options reveal levels that futures alone do not show.
- The difference between OI, volume, OI Change, bid/ask liquidity, and option premium.
- The limitations of OI: it does not reveal who owns the order, whether the big position is buyer-driven or seller-driven, or whether the level will break or reverse.
- The detailed block research process: use future data, not broker CFD alone; adjust block size as price and volatility change; do not hard-code 25 forever.
- The standard-deviation / mean-deviation / TPO / volume profile logic used when OI is missing or as a third confirmation after block and OI.
- The source's discussion that sideway/fight zones often happen around the block levels and that these can cause many consecutive losses if the system trades both sides without a bias.
- The source's warning that the 2 SD and 3 SD zones usually matter less for day play unless the market has already expanded strongly.
- Premium valuation in detail: ATR ratio thresholds, Black-Scholes fair value, IV, time value, moneyness, and liquidity.
- The option strategy library: Wheel, Cash-Secured Put, Synthetic Long Stock, Protective Put, Deep Protective Put, Covered Call, Far OTM Covered Call, Collar, Covered Ratio Spread, Stock/Future + Long Strangle, Vertical Spreads, Calendar/Diagonal Spreads, Straddle/Strangle/Butterfly.
- Margin and cash-flow discipline: sellers receive premium but must reserve capital for drag, assignment, and exercise risk.
- The difference between trading for cash flow and trading for big directional wins.
- The signal-design rule that OI should be a map layer, premium should be a valuation layer, and price behavior should be the trigger layer.

So the correct answer is: V1 is useful, but it is not enough. Use V2 as the deeper source pack.

---

## 1. Master concept from the source

The source is not only about OI. The larger system has four layers:

1. Positioning layer: OI / option heat map / OI Change.
2. Price-structure layer: block levels, SD zones, sideway zones, tails, breakout points.
3. Valuation layer: premium cheap/expensive, ATR, IV, Black-Scholes, liquidity.
4. Risk/cash-flow layer: margin, cash reserve, max consecutive loss, wheel/cash-flow strategy, hedge strategy.

The source repeatedly pushes a survival-first mindset. The goal is not only to be correct. The goal is to not die, keep cash flow, preserve capital, and use options to control risk where direct cut loss or direct futures trading becomes inefficient.

This matters for automation because an automated signal should not output only BUY or SELL. It should output:

- Market state.
- OI zone state.
- Premium state.
- Suggested strategy family.
- Risk condition.
- Whether the trade is fresh or late.
- Whether execution is allowed or vetoed.

A proper signal should be more like:

"Price is near a high-OI 1 SD zone. OI Change increased on the downside. Price has not yet moved fully to that zone. Premium is expensive versus ATR, so buying options is not preferred. If the account has enough margin and the strategy allows short premium, consider a short-premium / covered / cash-secured structure; otherwise wait for price confirmation at the block edge."

Not like:

"Put OI high, sell now."

---

## 2. Options basics needed before OI

### 2.1 Option = right, not obligation

An option gives the holder a right, not an obligation, to transact the underlying at a set strike price before or at expiration, depending on contract style.

Core fields:

- Underlying: the asset, such as gold futures, oil futures, stock, index, ETF, Bitcoin futures, etc.
- Call option: benefits when the underlying is above the strike, all else equal.
- Put option: benefits when the underlying is below the strike, all else equal.
- Strike price: the price level where the option becomes meaningful for exercise/payoff.
- Expiration date: the last date/time the option contract is valid.
- Premium: the price paid by the buyer and received by the seller.
- Contract size: multiplier that turns point movement into monetary value.
- Moneyness: ATM, ITM, OTM.
- Intrinsic value: value if exercised now.
- Time value: extra value from time and uncertainty before expiration.
- IV: implied volatility, the volatility expectation embedded in option price.
- Greeks: Delta, Gamma, Vega, Theta; they describe sensitivity to price, acceleration, volatility, and time decay.

### 2.2 Buyer vs seller

Buyer of option:

- Pays premium upfront.
- Maximum loss is usually the premium paid.
- Needs price movement and/or premium expansion before time decay destroys value.
- Benefits from cheap premium and strong movement.
- Can profit before expiration if premium increases.

Seller of option:

- Receives premium upfront.
- Wants the option to decay or expire worthless.
- Has margin obligation and potentially large loss if price moves hard against the sold option.
- Needs capital reserve, not only initial margin.
- Benefits from expensive premium and stable/range-bound price.

Automation implication:

- Long-option signals need cheap premium, movement potential, and enough time.
- Short-option signals need expensive premium, stable/range expectation, liquidity, and strong margin control.

### 2.3 ATM, ITM, OTM

ATM = strike near current price. Premium is usually higher because the option is most sensitive to price movement.

ITM = option already has intrinsic value.

OTM = option has no intrinsic value yet but may become valuable if price reaches the strike. OTM options are cheaper but need a larger move. Deep OTM options can be disaster hedges; they are cheap but only pay when a large move happens or when volatility explodes.

Automation implication:

- ATM options are sensitive but expensive.
- OTM options are cheaper but need larger movement.
- Deep OTM options can be used for tail hedging or volatility expansion, not for routine small moves.

### 2.4 Options versus futures for signal use

Futures show current traded price. The futures order book shows current bid/ask depth, but it does not naturally show all future strike levels where market participants have placed option exposure.

Options show interest across many strikes and expiries. This is why the source uses option data: a strike with large OI marks a zone where many participants have exposure, incentive, risk, or settlement interest.

Automation implication:

- Futures price tells us where the market is now.
- Option OI tells us where important future fight zones may be.
- The signal engine needs both.

---

## 3. Open Interest (OI) distilled

### 3.1 Definition

Open Interest is the number of outstanding option contracts that remain open at a strike and expiration. It is not the same as volume.

- Volume = contracts traded during a period.
- OI = contracts still open after trades and closures.
- OI Change = change in open contracts from previous snapshot/report.

High OI means many contracts remain open at that strike/expiry. It does not mean price must go there. It means the level has interest and potential market impact.

### 3.2 The source's key phrase: "big, long, many"

The source compresses OI interpretation into:

ใหญ่ ยาว เยอะ = big, long, many.

Interpretation:

- Big: large OI size compared with nearby strikes.
- Long: longer or important expiry/series may carry more interest than a tiny short-dated zone.
- Many: many contracts or many repeated concentrations around a zone.

The bigger and more persistent the concentration, the more important the zone.

### 3.3 What OI can tell you

OI can help locate:

- Battle zones where call buyers/sellers or put buyers/sellers have opposing incentives.
- Magnet zones where price may travel toward because there is large interest.
- Pause zones where price may swing because participants fight.
- Potential support/resistance zones.
- Zones where market makers or large participants may hedge, defend, unwind, or rebalance.
- Settlement/expiry-sensitive areas.

### 3.4 What OI cannot tell you

OI cannot directly tell you:

- Who owns the contracts.
- Whether the big position is from a buyer, seller, market maker, hedge fund, retail, or hedge.
- Whether price will reverse, break through, or stall at the level.
- Whether a high call OI level is bullish or bearish by itself.
- Whether the position is speculative or protective.

The source explicitly warns that if we knew whose order it was, trading would be easy. But we do not know. Therefore we use OI as a map, not as a final trigger.

Automation implication:

OI = map layer.
Price behavior = trigger layer.
Premium/risk = strategy layer.

### 3.5 Call OI interpretation

High call OI at a strike means there is large call exposure around that level.

Possible incentives:

- Call buyers want price above the strike.
- Call sellers do not want price above the strike because they may lose/pay.
- Market makers may hedge dynamically around that level.

Practical reading:

- The level can become a fight zone.
- Price may move toward it, pause, swing, reject, or break through.
- Do not read it as automatically bullish.

### 3.6 Put OI interpretation

High put OI at a strike means there is large put exposure around that level.

Possible incentives:

- Put buyers want price below the strike.
- Put sellers do not want price below the strike because they may lose/pay.
- Hedgers may have bought protection, so the position may not be a directional bet.

Practical reading:

- The level can become a downside fight zone or support/defense zone.
- Price may move toward it, pause, swing, reject, or break through.
- Do not read it as automatically bearish.

---

## 4. OI Heat Map and OI Change

### 4.1 What a heat map is in this source

The heat map is a visual map of option interest by strike and expiry. It shows where option contracts are concentrated.

The source treats it as a way to see where large participants have positioned exposure, because option strikes reveal future price levels. This is different from a futures chart, which shows only current price movement.

### 4.2 OI Change

OI Change is the change in OI from one report/snapshot to the next. It tells whether new open interest has appeared or disappeared at a strike.

Important rule from the source:

Check OI Change against current futures price.

- If OI Change increases and price has not yet moved to that zone, the information may be fresh.
- If price has already moved far, the trade may be late.
- If OI Change appears but price does not respond, the market may be absorbing or waiting.
- If OI decreases at a zone, interest may be leaving and price may move to another zone.

Automation implication:

Each OI Change signal needs a freshness flag:

- fresh = OI changed but price is still near entry area.
- late = OI changed but price already traveled too far.
- stale = OI changed previously and no longer matters.
- invalidated = OI later disappears or opposite zone becomes dominant.

### 4.3 The 70% heuristic

The source suggests that if intraday OI/positioning is concentrated on one side, price often goes that side, roughly described as 70% in the discussion. This should be treated as a source heuristic, not a proven universal rule.

Automation implication:

Do not hard-code 70% as truth. Store it as a hypothesis to test:

- For each day, identify dominant side.
- Measure whether price traveled to that side.
- Measure whether it broke, reversed, or only touched.
- Track hit rate by asset, session, expiry, and volatility regime.

### 4.4 OI is a zone, not a candle signal

The source's view is that price goes to zones where interest exists, fights there, and then either continues or leaves. That means OI is not a candle entry by itself.

The robot should not trade immediately just because a strike has high OI. It should wait for confirmation such as:

- Price reaching a block level.
- Price rejecting at a tail.
- Price breaking sideway boundary.
- OI Change confirming same direction.
- Premium condition matching strategy.
- Liquidity and margin acceptable.

---

## 5. 1 SD, 2 SD, 3 SD logic

### 5.1 Main source rule

For day play / intraday trading, focus mainly on 1 SD, described in the source as the inner or dark-grey zone.

2 SD and 3 SD should usually be ignored for normal day play unless price expands strongly enough that the inner zone has already been exhausted.

Why:

- 1 SD is the normal zone where price spends most of its time.
- Intraday price often stays inside the inner band.
- 2 SD and 3 SD represent less common extremes or wider series-level interpretation.

### 5.2 How to treat 2 SD / 3 SD

Use 2 SD / 3 SD only when:

- Price already leaves 1 SD strongly.
- OI in the inner zone has been consumed or no longer matters.
- A strong event or high-volatility regime is present.
- Outer OI concentration is clearly larger and fresh.
- Price has enough ATR room to reach the outer zone.

### 5.3 Mean deviation / POC / TPO idea

The source discusses using TPO or volume profile style tools to find normal distribution zones:

- POC / mean area = the normal price area for the selected period.
- VAH/VAL or outer distribution levels can represent wider deviation areas.
- Price that moves too far from mean may revert if the market is not in a trend or event expansion.

The source warns not to use tiny minute periods for this because they are too noisy. It discusses using larger context, such as weekly period and H1 chart, to capture a meaningful block.

Automation implication:

The system should compute distribution zones using a stable context, not only M1/M5 noise.

### 5.4 Sharp curve rule

The source says SD logic should be used when the price behavior forms a full block / sharp curve. If the distribution is incomplete or messy, discard the SD signal.

Automation implication:

Add a distribution quality score:

- full sharp curve = valid.
- weak curve = lower score.
- no curve = no SD signal.

---

## 6. Block logic and price behavior

### 6.1 What block logic means

The source observes that some assets tend to react around repeated price blocks.

Examples discussed:

- Gold often shows behavior around 25 or 50 point zones in the source examples.
- Oil can be organized around 1.0 or 0.5 dollar zones.
- Bitcoin can show large block jumps such as 2,500 in the source discussion.

These are examples, not permanent constants.

### 6.2 Why blocks matter

The source says even people inside banks may not know the exact reason why certain blocks become routine. The important point is that the behavior appears repeatedly. The trader does not need to know the metaphysical reason; the trader needs to research whether the routine is currently active.

### 6.3 Do not hard-code old block sizes

Gold at 1,800 and gold at 3,000 should not automatically use the same block size. The source explains that as price rises, point movement can become wider even if percentage volatility is similar.

Automation implication:

Block size should be dynamic and estimated from:

- Current price level.
- Historical average daily range.
- ATR.
- Strike spacing in the options chain.
- Recent reaction points.
- OI concentration spacing.
- Contract tick size and instrument convention.

### 6.4 Block examples as formulas

For gold:

- If current behavior clusters every 25, use 25 as micro-block.
- If behavior has expanded, use 50 as main block.
- If price moves much higher, re-test whether 50 becomes the normal block and 25 becomes noise.

For oil:

- Use 1.0 dollar zones as primary blocks.
- Use 0.5 dollar zones as half-block or finer reaction zones.

For Bitcoin:

- Use larger block spacing and test behavior, especially if no daily OI heat map is available.

### 6.5 Tail / wick behavior

The source notes that tails often form at block levels. Traders can use block levels to find high-probability reaction points.

But tail trading has a problem:

- The level can become a sideway fight zone.
- It can swing many times before breaking.
- A two-sided system can suffer many consecutive losses.

Automation implication:

A tail reaction signal needs:

- Maximum consecutive loss assumption.
- Bias filter to avoid playing both directions blindly.
- Stop/hedge/recovery rule.
- Confirmation that the current block is still valid.

### 6.6 Sideway fight zone

The source explains that when price reaches a key block/OI zone, participants may fight. Price can oscillate around the level before choosing direction.

Example logic from the source:

- If block center is 50, sideway may swing roughly 47 to 53.
- A breakout might need price beyond 55 to confirm.
- A safer version may wait for 60 with larger stop but lower reward.

This is not a universal parameter. It is an example of converting observed micro-volatility into entry logic.

Automation implication:

Compute current sideway width using intraday ATR or historical swing around blocks.

---

## 7. Combining OI + block + SD

### 7.1 Priority order

The source implies a hierarchy:

1. Block behavior / price routine.
2. OI / heat map.
3. SD / mean deviation as confirmation when OI is missing or when distribution is clean.

In one discussion, SD is described as the third tool after block and OI.

### 7.2 Practical combined reading

A high-quality zone is stronger when:

- It sits on a known block level.
- It has high OI or fresh OI Change.
- It lies inside or near the 1 SD intraday zone.
- It is near POC/mean or a meaningful distribution boundary.
- Price has not already moved too far.
- Premium condition supports the intended strategy.

A weaker zone occurs when:

- OI is high but price block is not aligned.
- OI Change is old/stale.
- Price already reached the zone.
- Premium is too expensive for long-option strategy.
- Liquidity is poor.
- The block size is outdated.
- SD distribution is not clean.

### 7.3 OI zone behavior model

At a high OI zone, expect one of four behaviors:

1. Magnet: price travels toward the zone.
2. Fight: price swings around the zone.
3. Rejection: price touches or approaches and reverses.
4. Break: one side loses and price moves to the next zone.

Signal automation must classify which stage is happening.

### 7.4 Decision sequence

Step 1: Locate high OI zones.
Step 2: Rank them by size, expiry, and concentration.
Step 3: Mark whether each zone is inside 1 SD, 2 SD, or 3 SD.
Step 4: Map zones to block grid.
Step 5: Check OI Change freshness.
Step 6: Check price distance to zone.
Step 7: Check premium valuation.
Step 8: Choose strategy or no trade.
Step 9: Trigger only after price action confirms.
Step 10: Manage risk and log outcome.

---

## 8. Premium valuation: ATR method

### 8.1 Why premium matters

The source repeatedly warns that buying an option just because direction seems correct can still be bad if premium is too expensive.

If premium is too high, price must move a lot just to break even. Even if direction is right, the trade may not pay.

### 8.2 ATR comparison method

Use ATR over the same horizon as the option expiry.

Example from the source:

- Option expiry: 30 days.
- Premium: 85.
- Monthly ATR: 110.
- Premium / ATR = 85 / 110 = about 77%.

Interpretation:

- Price must move more than 85 just to cover premium.
- If typical monthly movement is 110, only about 25 points remain as potential edge after covering premium.
- This is expensive for an option buyer.

### 8.3 Premium / ATR thresholds

The source gives a practical threshold framework:

- Under 30% of ATR: cheap premium. Long options may be attractive if direction/volatility supports it.
- 30% to 60% of ATR: moderate/fair. There is still room for movement.
- 60% to 80% of ATR: expensive. Be cautious as buyer; may favor seller if risk allows.
- Over 80% of ATR: very expensive. Usually poor for buyers unless future volatility is expected to expand far beyond historical ATR.

### 8.4 Limitation of ATR

ATR is based on past movement. It does not guarantee future movement.

A premium that looks expensive versus historical ATR may still be justified if the market expects a major future event. Conversely, a premium that looks cheap can remain cheap and decay if nothing happens.

Automation implication:

Premium / ATR is a filter, not a final truth.

### 8.5 How to implement ATR premium filter

For each option:

premium_atr_ratio = option_mid_premium / ATR_matching_expiry

Then classify:

- cheap <= 0.30
- fair > 0.30 and <= 0.60
- expensive > 0.60 and <= 0.80
- very_expensive > 0.80

Use the classification in strategy selection:

- cheap/fair -> long options, protective puts, strangles, directional options are possible.
- expensive/very expensive -> avoid buying naked premium; consider covered call, cash-secured put, wheel, ratio spread, collar, or no trade depending on risk.

---

## 9. Premium valuation: Black-Scholes, IV, and time value

### 9.1 Black-Scholes purpose

The source discusses using Black-Scholes or a simplified calculator/AI tool to estimate theoretical option value.

Inputs usually include:

- Current underlying price.
- Strike price.
- Time to expiration.
- Risk-free interest rate.
- Volatility / IV.
- Option type: call or put.

### 9.2 Market premium versus theoretical premium

If market premium is much higher than theoretical value:

- The option may be expensive.
- Market may expect higher future volatility.
- Selling premium may be attractive if risk/margin and strategy fit.

If market premium is lower than theoretical value:

- The option may be cheap.
- Buying premium may have better RR if direction/volatility supports it.

### 9.3 IV as expectation

IV is the market's embedded volatility expectation. It is not the same as historical ATR.

- High IV -> premium expensive, good for sellers but dangerous if market moves more.
- Low IV -> premium cheap, good for buyers if a big move may come.

### 9.4 Premium can be traded before exercise

The source emphasizes that options are not only about final exercise payoff. Premium itself can expand or shrink.

Example logic:

- Buy cheap deep OTM put for 15.
- If price crashes quickly while much time remains, premium may rise to 30, 50, 80 before the option even becomes fully exercised/intrinsic.
- The trader can sell the premium expansion instead of waiting to expiry.

Automation implication:

Exit rules should include:

- premium expansion target.
- IV spike target.
- time remaining threshold.
- not only strike reached / expiry payoff.

### 9.5 Time decay

Theta hurts long option buyers as time passes. The closer to expiry, the faster OTM options can decay.

Automation implication:

- Avoid buying options with too little time unless the expected move is immediate.
- For sellers, time decay is income but gap risk remains.
- For calendar/diagonal spreads, short-dated time decay is a key feature.

---

## 10. Liquidity and execution

### 10.1 Why liquidity matters

The source warns that option strategy becomes difficult in illiquid markets because bid/ask spread can be wide and exits can be hard.

Liquid markets mentioned/implied:

- Major indices.
- Major commodities such as gold and oil.
- Large instruments with market makers.

Less liquid markets can be dangerous because:

- The premium looks good but cannot be entered/exited fairly.
- Bid/ask spread destroys expected edge.
- Assignment/exercise and rolling become harder.

### 10.2 Required liquidity data

Automation should track:

- bid.
- ask.
- mid.
- spread_points = ask - bid.
- spread_percent = spread / mid.
- option volume.
- OI.
- last trade time.
- quote age.
- slippage estimate.

Trade veto examples:

- No bid or no ask.
- Spread above allowed threshold.
- Option volume too low.
- OI too low.
- Quote stale.
- Broker price not aligned with source futures data.

---

## 11. Strategy library distilled from the source

This section is not for choosing the final strategy yet. It is for preserving the knowledge that the next session can use.

### 11.1 Long Call

Structure:

- Buy call option.

View:

- Bullish.
- Expect price to rise enough to cover premium.
- Prefer cheap premium or expected volatility expansion.

Risk:

- Maximum loss = premium paid.

Automation use:

- Use when OI/price/volatility suggests upside and premium is cheap/fair.
- Avoid if premium is expensive relative to ATR.

### 11.2 Long Put

Structure:

- Buy put option.

View:

- Bearish or protective.
- Expect price to fall enough to cover premium.

Risk:

- Maximum loss = premium paid.

Automation use:

- Use for downside signals or hedge.
- Good when premium is cheap, volatility is low, or crash risk is rising.

### 11.3 Short Call

Structure:

- Sell call option.

View:

- Price unlikely to rise beyond strike.
- Premium is worth collecting.

Risk:

- Potentially large loss if underlying rises strongly.
- Requires margin.

Automation use:

- Only with risk control or covered by underlying/long call.
- Avoid naked short call unless system explicitly allows and risk is capped.

### 11.4 Short Put

Structure:

- Sell put option.

View:

- Price unlikely to fall below strike, or trader is willing to acquire/hold underlying.

Risk:

- Loss if price falls below strike beyond collected premium.
- Requires cash/margin reserve.

Automation use:

- Basis of Cash-Secured Put and Wheel.
- Use when premium is high and underlying is acceptable to hold.

### 11.5 Protective Put / Buy and Hedge

Structure:

- Long underlying/future/stock.
- Long put.

View:

- Want upside while limiting downside.

Payoff:

- Downside locked after premium and strike protection.
- Upside remains open, minus premium cost.

Deeper source insight:

- When price falls, the put gains value.
- The trader may use put gains or premium value as cash to buy more underlying at lower price.
- If price later recovers, the trader can have more units than simple buy-and-hold.

Automation use:

- Hedge for long future/stock exposure.
- Portfolio survival tool.
- Better than stop-loss when you do not want to close the main position.

### 11.6 Deep Protective Put / Toric Hedging

Structure:

- Long underlying/future.
- Buy far OTM put.

View:

- Need disaster protection but ATM put is too expensive.
- Accept some downside before protection begins.

Key source insight:

- Deep OTM put is cheap.
- If market crashes quickly and time remains, premium can swell several times before full expiry payoff.
- This lets trader sell premium expansion or use it to offset long losses.

Automation use:

- Tail hedge.
- Budget-limited hedge.
- Crash-volatility signal.

Critical filters:

- Time remaining.
- Distance to strike.
- Premium cheapness.
- Expected event/crash probability.
- Liquidity.

### 11.7 Covered Call

Structure:

- Long underlying.
- Short call.

View:

- Own the asset but believe price will not rise much.

Benefit:

- Collect premium.
- Premium buffers downside.
- Turns passive holding into cash-flow asset.

Cost:

- Upside capped after strike.

Automation use:

- Sideways/slightly bearish/neutral market with expensive call premium.
- Useful when account already holds underlying.

### 11.8 Far OTM Covered Call

Structure:

- Long underlying.
- Short far OTM call.

View:

- Price may rise some, but unlikely to reach distant strike.

Benefit:

- Collect premium without capping near-term upside too close.

Cost:

- Premium is smaller.
- If price spikes above strike, upside is capped and short call loses.

Best context:

- Mean-reverting assets.
- Oil or dividend stocks in the source discussion.
- Researched distribution where far strike is unlikely.

Automation use:

- Use when high strike is statistically hard to reach and premium still compensates risk.

### 11.9 Collar

Structure:

- Long underlying.
- Short call.
- Long put.

View:

- Want defined outcome.
- Used for accounting certainty, structured notes, or fixed reward/loss boundaries.

Benefit:

- Downside limited by long put.
- Short call helps finance the put.
- P&L range becomes predictable.

Cost:

- Upside capped.
- Needs careful strike balance.

Deeper source insight:

- If market falls, put and premium can create cash/buffer for recovery or additional strategy.
- If market rises, profit is capped but known.

Automation use:

- Portfolio hedge.
- Defined-risk structure before events.
- Strategy when certainty is more important than unlimited upside.

### 11.10 Covered Ratio Spread

Structure from source example:

- Long underlying/future.
- Short 2 call options at one strike.
- Long 1 call option at higher strike.

View:

- Expect price to stay in a researched zone.
- Want extra profit if price remains around target range.

Benefit:

- Can improve return in range-bound commodity.
- Reduces downside versus naked long underlying due collected premium.
- Long call helps if price spikes.

Risk:

- Complex payoff.
- Needs accurate range research.
- Not ideal for strongly trending stocks.

Best context:

- Commodities like oil that often oscillate in a known range.

Automation use:

- Only when range probability is high, premium conditions are favorable, and risk engine can model payoff fully.

### 11.11 Long Stock/Future + Long Strangle

Structure:

- Long underlying/future.
- Long OTM call.
- Long OTM put.

View:

- Want downside protection and upside acceleration.
- Expect large movement or recovery.
- Premium should be cheap.

Benefit:

- Put protects downside.
- Call boosts upside if price breaks upward.

Cost:

- Pay two premiums.
- If market stagnates, time decay hurts.

Automation use:

- Low-volatility stagnation with possible breakout/recovery.
- Event setup with cheap premium.

### 11.12 Synthetic Long Stock

Structure:

- Long call.
- Short put.

View:

- Replicate long stock/future payoff using options.

Benefit:

- Margin/capital efficiency.
- Frees cash balance for other use.

Risk:

- Short put creates margin and downside risk.
- Premiums rarely perfectly balance; payoff can be skewed.

Automation use:

- Replace future/stock exposure when margin is expensive.
- Only if margin and downside risk are controlled.

### 11.13 Cash-Secured Put

Structure:

- Sell put while reserving cash/margin to buy or hold underlying if assigned/dragged.

View:

- Want cash flow and willing to buy lower.
- Similar to grid logic but through options.

Benefit:

- Premium received immediately.
- If price does not fall below strike, keep premium.
- If price falls, acquire/hold underlying at effective discount.

Risk:

- Price can fall far beyond premium.
- Requires cash reserve.

Automation use:

- Short-premium income strategy.
- Works when premium is high and asset is acceptable to own.

### 11.14 Wheel Strategy

Structure:

1. Sell put and collect premium.
2. If price falls and assignment/long position occurs, hold underlying.
3. Sell call against held underlying.
4. If price rises and called away, return to cash.
5. Repeat.

View:

- Cash-flow strategy.
- Good in sideways or slightly bullish markets with enough premium.
- Similar feeling to grid trading: collect rent/cash flow.

Benefit:

- Systematic premium collection.
- Can acquire asset at lower effective cost.
- Can generate monthly/periodic income.

Risk:

- Underlying can fall much more than premium collected.
- Upside is capped when covered call is sold.
- Requires margin/cash discipline.
- Not for chasing big wins.

Automation use:

- Only for instruments the account is willing and able to hold.
- Needs assignment/roll/covered-call logic.
- Needs premium valuation filter: avoid when premium is too low.

### 11.15 Vertical Spreads

Bull Call Spread:

- Buy lower strike call.
- Sell higher strike call.
- Bullish with defined risk and capped reward.
- Reduces premium cost versus naked long call.

Bear Put Spread:

- Buy higher strike put.
- Sell lower strike put.
- Bearish with defined risk and capped reward.
- Reduces premium cost versus naked long put.

Automation use:

- When direction exists but premium is not cheap enough for naked option.
- When risk must be defined.

### 11.16 Calendar Spread

Structure:

- Buy longer-dated option.
- Sell shorter-dated option at same strike.

View:

- Use time decay difference.
- Short option decays faster; long option protects longer-term exposure.

Automation use:

- When near-term range is expected but longer-term movement is possible.
- Needs expiry management.

### 11.17 Diagonal Spread

Structure:

- Buy longer-dated option at one strike.
- Sell shorter-dated option at different strike.

View:

- Hybrid of calendar and directional spread.
- Collect short-term premium while keeping longer-term directional exposure.

Automation use:

- More advanced strategy selector after basic OI/premium framework is tested.

### 11.18 Straddle, Strangle, Butterfly

Long Straddle:

- Buy call and put at same strike.
- Expect big move; direction unknown.
- Expensive because both legs near ATM.

Long Strangle:

- Buy OTM call and OTM put.
- Cheaper than straddle but needs bigger move.

Short Straddle/Strangle:

- Sell both sides.
- Want price stable and premium decay.
- High risk if price breaks hard.

Butterfly:

- Combination that profits around a middle zone with defined risk/reward.
- Useful for stable/range expectation when payoff is well understood.

Automation use:

- Long vol structures when premium cheap and move expected.
- Short vol structures only with strict risk, margin, and event filters.

---

## 12. Strategy selection logic

The strategy should be selected after OI, block, and premium are known.

### 12.1 If premium is cheap and movement is expected

Possible strategies:

- Long call.
- Long put.
- Long strangle/straddle.
- Protective put.
- Deep protective put.
- Vertical spread if cheaper defined risk is needed.

Avoid:

- Selling cheap premium unless there is another strong reason.

### 12.2 If premium is expensive and range is expected

Possible strategies:

- Covered call.
- Far OTM covered call.
- Cash-secured put.
- Wheel.
- Collar.
- Covered ratio spread.
- Short premium structures with protection.

Avoid:

- Buying naked expensive options unless expecting huge volatility expansion.

### 12.3 If OI zone is high but direction unclear

Possible strategies:

- Wait for breakout/rejection.
- Use defined-risk structures.
- Use collar/protective hedge if already holding underlying.
- Avoid entering naked direction purely from OI.

### 12.4 If OI Change is fresh and price has not moved

Possible strategies:

- Directional futures/CFD setup after block confirmation.
- Long option if premium cheap/fair.
- Vertical spread if premium moderate/expensive but direction strong.
- No trade if price is mid-zone and no trigger.

### 12.5 If OI Change is late

Possible strategies:

- Wait for pullback to block.
- Wait for next OI zone.
- Consider premium expansion exit if already in.
- Avoid chasing.

---

## 13. Trading signal framework

### 13.1 Signal is a score, not a single condition

A robust signal should combine several scores:

- OI zone score.
- OI Change freshness score.
- Block alignment score.
- SD/mean-deviation score.
- Price action trigger score.
- Premium valuation score.
- Liquidity score.
- Risk/margin score.
- Event/regime score.

Only when total score and risk filters pass should the system allow a trade.

### 13.2 OI zone score

Inputs:

- OI at strike.
- OI percentile among nearby strikes.
- OI rank within expiry.
- OI rank across expiries.
- OI concentration relative to neighboring strikes.
- Expiry importance.
- Call/put side.

Example scoring:

- +3 if OI is top 5% in expiry.
- +2 if OI is top 10%.
- +1 if OI is above median.
- +2 if OI also aligns with block.
- +1 if OI aligns with 1 SD.
- -2 if OI is far outside reachable ATR.

### 13.3 OI Change freshness score

Inputs:

- Current OI Change.
- Previous OI Change.
- Price movement since change.
- Distance from current price to changed strike.
- Time since report.

Freshness model:

- fresh: OI Change large and price has not yet moved much.
- active: price is moving toward changed zone.
- late: price already traveled most of the distance.
- invalid: OI Change disappeared or opposite side dominates.

### 13.4 Block alignment score

Inputs:

- Candidate zone level.
- Dynamic block grid.
- Distance to nearest block.
- Historical reaction frequency at block.
- Current sideway width around block.

Signal idea:

- A high OI strike exactly at or near a strong block is more meaningful than high OI in a random area.

### 13.5 SD/mean-deviation score

Inputs:

- POC/mean.
- 1 SD boundary.
- 2 SD boundary.
- 3 SD boundary.
- Distribution quality.

Signal idea:

- Intraday signals prefer 1 SD.
- Reversion signals use distance from mean if market is not trending.
- Outer SD only matters when expansion regime is active.

### 13.6 Premium valuation score

Inputs:

- Premium / ATR ratio.
- Market premium versus theoretical value.
- IV rank or IV percentile.
- Bid/ask spread.
- Time to expiration.

Signal idea:

- Cheap premium supports buying options.
- Expensive premium supports selling premium or structured strategies.
- Very wide spreads veto trades.

### 13.7 Price trigger score

OI is not enough. Trigger examples:

- Touch and reject at OI/block zone.
- Breakout beyond sideway boundary.
- Retest after breakout.
- Mean reversion from 2 SD/3 SD toward POC.
- Price has not moved yet after fresh OI Change.

### 13.8 Risk score

Inputs:

- Account equity.
- Free margin.
- Required margin.
- Max loss.
- Expected drawdown.
- Consecutive loss stress.
- Daily loss limit.
- Contract multiplier.
- Slippage/spread.

Risk veto examples:

- Free margin below required safety buffer.
- Expected worst-case exceeds allowed drawdown.
- Data feed delayed.
- Spread too wide.
- Event risk not allowed.
- Consecutive loss stress fails.

---

## 14. Signal templates

### 14.1 OI Magnet / Fight Zone Signal

Goal:

Detect where price may travel, pause, or fight.

Conditions:

- Strike has high OI.
- Zone aligns with current dynamic block.
- Zone is inside 1 SD or reachable by ATR.
- Price is not already far past the zone.

Output:

- Mark zone as magnet/fight zone.
- Do not auto-enter yet.
- Wait for reaction or breakout confirmation.

Trade trigger options:

- Rejection = counter-trend scalp/reversion.
- Break and hold = continuation to next zone.
- No confirmation = no trade.

### 14.2 Fresh OI Change Direction Signal

Goal:

Detect new positioning before price has fully moved.

Conditions:

- OI Change is large relative to baseline.
- OI Change is on one side/strike cluster.
- Current futures price has not yet moved too far toward the zone.
- Zone is inside 1 SD or reachable by daily ATR.

Output:

- Directional bias toward changed zone.
- Entry only after block breakout or pullback confirmation.

Veto:

- Price already moved to target.
- Premium too expensive for option buying.
- OI Change disappears.

### 14.3 1 SD Mean Reversion Signal

Goal:

Use normal distribution zone.

Conditions:

- Price moves away from mean/POC but remains within non-trending regime.
- Distribution quality is clean.
- Price reaches a 1 SD boundary or block edge.
- No strong event/trend expansion.

Output:

- Reversion bias toward POC/mean.

Veto:

- Strong trend.
- Outer OI pulling price farther.
- Event risk.
- Distribution not clean.

### 14.4 Block Breakout Signal

Goal:

Avoid being trapped in fight zone by waiting for escape.

Example logic:

- Block center = 50.
- Sideway width roughly 47 to 53.
- Buy trigger above 55 or 60 depending on stop choice.
- Sell trigger below 45 or 40 depending on stop choice.

Generalized formula:

upper_trigger = block_level + sideway_width_buffer
lower_trigger = block_level - sideway_width_buffer

Output:

- Enter in breakout direction only if OI/price/premium filters agree.

### 14.5 Premium Sell Signal

Goal:

Collect premium when premium is expensive and price expected stable.

Conditions:

- Premium / ATR > 0.60.
- IV high versus historical range.
- Price expected to remain within block/1 SD range.
- Liquidity good.
- Margin reserve adequate.

Possible strategies:

- Covered call.
- Cash-secured put.
- Wheel.
- Collar.
- Ratio spread.

Veto:

- Event risk.
- Strong breakout.
- Insufficient margin.
- Naked risk not allowed.

### 14.6 Premium Buy / Volatility Expansion Signal

Goal:

Buy option when premium is cheap and movement/volatility is expected.

Conditions:

- Premium / ATR < 0.30 or fair with strong catalyst.
- IV low relative to expected future volatility.
- OI Change or block breakout suggests movement.
- Time to expiry sufficient.

Possible strategies:

- Long call/put.
- Long strangle.
- Vertical spread.
- Protective put/deep put.

Veto:

- Premium expensive.
- Time too short.
- No movement catalyst.
- Spread too wide.

---

## 15. Data required for automation

### 15.1 Underlying/futures data

Required:

- Symbol.
- Exchange symbol, e.g. GC for gold futures if using CME data.
- Broker symbol, e.g. XAUUSD CFD if executing via broker.
- Current real-time futures price.
- Current broker executable price.
- Futures-to-broker price offset.
- OHLCV by timeframe.
- Tick size.
- Contract multiplier.
- Trading session.
- ATR by timeframe.
- Realized volatility.
- Trend state.
- POC/mean.
- VAH/VAL or SD boundaries.
- Dynamic block size.
- Sideway width estimate.

### 15.2 Option chain data

Required:

- Expiration date.
- Days to expiration.
- Strike.
- Option type: call/put.
- Bid.
- Ask.
- Mid.
- Last.
- Volume.
- Open Interest.
- OI Change.
- Implied volatility.
- Delta.
- Gamma.
- Vega.
- Theta.
- Intrinsic value.
- Time value.
- Moneyness.
- Settlement style.
- Exercise style.

### 15.3 Derived OI features

Derived fields:

- OI percentile by expiry.
- OI rank by expiry.
- OI rank across expiries.
- Max call OI strike.
- Max put OI strike.
- Call/put OI ratio.
- OI concentration score.
- OI cluster width.
- Distance from current price to OI zone.
- Distance in ATR units.
- Distance in block units.
- OI Change percentile.
- OI Change freshness.
- OI zone status: ahead, touched, broken, rejected, stale.

### 15.4 Derived premium features

Derived fields:

- mid premium = (bid + ask) / 2.
- spread = ask - bid.
- spread percent = spread / mid.
- premium / ATR ratio.
- theoretical value.
- market premium - theoretical value.
- IV rank.
- IV percentile.
- breakeven price.
- expected move.
- reward/risk after premium.
- time decay per day.

### 15.5 Risk/account data

Required:

- Account equity.
- Cash balance.
- Free margin.
- Used margin.
- Margin requirement per leg.
- Maximum allowed risk per trade.
- Maximum daily loss.
- Maximum weekly loss.
- Maximum open contracts.
- Maximum short option exposure.
- Maximum assignment exposure.
- Cash reserve for wheel/cash-secured strategy.
- Consecutive loss stress test.
- Slippage assumption.
- Commission.

### 15.6 Event data

Required:

- Expiration date/time.
- Roll date.
- Settlement date.
- Major macro events: CPI, FOMC, NFP, central bank decisions.
- Commodity-specific events: oil inventory, OPEC, geopolitical risk.
- Exchange holidays.
- Contract delivery risk.

---

## 16. Backtest requirements

### 16.1 Why backtest must be detailed

The source shows that a setup can look accurate on candle view but still suffer many swings inside the bar. A simple close-to-close backtest can lie.

Backtest should use intraday/tick data if possible.

### 16.2 Backtest questions for OI

Test:

- When a strike has top OI, does price travel toward it?
- How often does price touch, reject, break, or ignore it?
- Does 1 SD OI matter more than 2 SD/3 SD for intraday?
- Does OI Change predict price movement before the move?
- How late is too late after OI Change?
- Does call OI behave differently from put OI by regime?
- Does expiry distance change reliability?
- Does OI concentration matter more than raw size?

### 16.3 Backtest questions for block logic

Test:

- What is current valid block size?
- How often do blocks create tails?
- What sideway width appears around blocks?
- What breakout buffer reduces false signals?
- What is maximum consecutive loss when trading both sides?
- How much does a bias filter reduce losses?

### 16.4 Backtest questions for premium

Test:

- Does Premium / ATR threshold predict good/bad long-option trades?
- Are options with ratio under 30% profitable when paired with OI signal?
- Are options over 80% poor for buyers?
- Does selling premium work better when Premium / ATR is high?
- How does IV rank change performance?
- How much does bid/ask spread reduce edge?

### 16.5 Walk-forward and paper trading

Process:

1. Historical backtest.
2. Walk-forward by time period.
3. Out-of-sample testing.
4. Paper trading with live data.
5. Small live execution.
6. Scale only after stable results.

---

## 17. Risk controls for automation

### 17.1 Never automate OI alone

OI is not a trade by itself. Automation must require:

- OI zone.
- Price trigger.
- Premium filter.
- Liquidity filter.
- Risk filter.

### 17.2 Kill-switch rules

Stop trading when:

- Real-time data feed fails.
- OI data is stale.
- Broker price diverges from futures source beyond allowed offset.
- Spread widens beyond threshold.
- Daily loss limit hit.
- Weekly loss limit hit.
- Free margin below safety buffer.
- Event risk not allowed.
- Consecutive losses exceed stress limit.

### 17.3 Margin discipline

For short options:

- Premium received is not free profit until risk expires or is closed.
- Reserve cash for adverse moves.
- Stress test price beyond strike.
- Stress test gap moves.
- Stress test assignment/exercise.

For futures/CFD:

- Broker leverage can make position look cheap, but underlying exposure is still large.
- Small position can represent large notional exposure.
- Margin is not the same as maximum risk.

### 17.4 Cash-flow mindset

The source emphasizes cash flow. But cash flow can hide risk.

Good cash-flow system:

- Collects premium or grid profit.
- Keeps enough reserve.
- Survives bad regime.
- Avoids over-leverage.
- Knows when not to trade.

Bad cash-flow system:

- Collects small premium.
- Ignores tail risk.
- Multiplies too aggressively.
- Breaks during rare consecutive loss.

---

## 18. Automation architecture

### 18.1 Data ingestion

Modules:

- Futures price feed.
- Broker executable price feed.
- Option chain feed.
- OI/OI Change feed.
- Volatility/ATR calculator.
- Event calendar.
- Account/margin feed.

### 18.2 Feature engine

Computes:

- OI zones.
- OI Change freshness.
- Dynamic block grid.
- SD/POC/mean zones.
- Premium valuation.
- Liquidity metrics.
- Risk metrics.

### 18.3 Signal engine

Outputs:

- Bias: up/down/neutral.
- Zone type: magnet/fight/rejection/breakout/reversion.
- Strategy family: long premium/short premium/hedge/cash-flow/no trade.
- Confidence score.
- Invalidations.

### 18.4 Strategy selector

Maps signal to structure:

- Cheap premium + direction -> long call/put or vertical.
- Cheap premium + uncertain direction -> long strangle/straddle.
- Expensive premium + range -> covered call/cash-secured put/wheel/ratio.
- Existing long exposure + downside risk -> protective put/collar/deep put.
- Need margin efficiency -> synthetic long, only with strict risk.

### 18.5 Risk engine

Approves or vetoes:

- Position size.
- Max loss.
- Margin requirement.
- Cash reserve.
- Slippage/spread.
- Daily loss.
- Event conditions.

### 18.6 Execution engine

Rules:

- Use limit orders for options when spread exists.
- Do not chase stale OI moves.
- Log every rejected and accepted signal.
- Reconcile fills with broker.
- Monitor Greeks and margin after entry.

### 18.7 Monitoring

Track:

- Open positions.
- Greeks.
- OI changes after entry.
- Distance to strike/zone.
- Premium decay/expansion.
- Margin risk.
- Exit triggers.

---

## 19. Copy-ready pseudocode

### 19.1 OI zone extraction

For each expiry:

1. Load option chain.
2. For each strike, collect call_OI, put_OI, call_OI_change, put_OI_change.
3. Rank strikes by OI.
4. Identify top clusters.
5. Merge nearby strikes into zones if within block_size / 2.
6. Score each zone by OI size, OI Change, expiry, and concentration.

### 19.2 Block alignment

1. Estimate current block_size from historical reactions, ATR, and strike spacing.
2. Round candidate OI zone to nearest block.
3. Calculate distance_to_block.
4. If distance_to_block <= tolerance, add alignment score.

### 19.3 1 SD filter

1. Compute POC/mean and 1 SD boundaries from selected period.
2. If candidate zone inside 1 SD, mark intraday-relevant.
3. If candidate zone in 2 SD/3 SD, require expansion regime.
4. If no clean distribution, ignore SD confirmation.

### 19.4 Premium filter

1. Get option mid premium.
2. Get ATR matching option expiry.
3. ratio = premium / ATR.
4. Classify cheap/fair/expensive/very_expensive.
5. Compare to theoretical value if Black-Scholes data available.
6. Veto if spread too wide or liquidity poor.

### 19.5 Signal scoring

score = 0

score += OI_zone_score
score += OI_change_freshness_score
score += block_alignment_score
score += SD_score
score += price_trigger_score
score += premium_score
score += liquidity_score
score += risk_score

If any veto condition true: no trade.
Else if score above threshold: signal valid.
Else: watch only.

### 19.6 Trade output object

A proper signal should output:

- timestamp.
- symbol.
- current futures price.
- broker price.
- candidate zone.
- zone type.
- dominant OI side.
- OI size and rank.
- OI Change and freshness.
- block size.
- SD location.
- premium state.
- liquidity state.
- strategy family.
- entry trigger.
- invalidation.
- risk amount.
- margin required.
- exit plan.
- reason log.

---

## 20. What the next session should decide

The next session should not re-read the whole source. It should use this V2 source pack and decide:

1. Which asset to automate first: gold, oil, index, or another.
2. Which timeframe: intraday, swing, monthly premium, wheel cycle.
3. Which data source is available for OI and option chain.
4. Whether execution is via futures, options, CFD, or only signal alerts.
5. Whether the strategy uses long premium, short premium, or futures/CFD entries around OI zones.
6. Which block size is currently valid.
7. Which risk model is acceptable.
8. Which backtest sample size is required.
9. What counts as a valid OI Change.
10. Whether the system should trade or only alert at first.

---

## 21. Final distilled truth

The source's core trading philosophy can be compressed into this:

Options are not only directional bets. They are tools for mapping market interest, collecting cash flow, hedging existing exposure, controlling margin, and shaping payoff. OI shows where market interest is concentrated, but OI does not reveal the winner. The correct use of OI is to map important zones, then combine those zones with block behavior, 1 SD/mean-deviation context, fresh OI Change, premium valuation, liquidity, and risk control. Only after all layers agree should a signal become tradeable.

The automation should therefore be built as a decision system, not a signal shortcut.

The correct order is:

1. Understand the instrument.
2. Build the OI map.
3. Map blocks and SD zones.
4. Check OI Change freshness.
5. Check premium cheap/expensive.
6. Select strategy family.
7. Apply risk veto.
8. Execute only after price trigger.
9. Log everything.
10. Improve only after backtest and paper trade.

---

## 22. Glossary

OI: Open Interest, open contracts still outstanding.

OI Change: Change in open interest from previous report/snapshot.

Heat map: Visual representation of OI or other concentration by price/strike/expiry.

Strike: Option exercise price.

Expiry: Last valid date/time of option.

Premium: Price of option.

ATM: At the money, strike near current price.

ITM: In the money, option has intrinsic value.

OTM: Out of the money, option has no intrinsic value yet.

IV: Implied volatility, volatility expectation inside option price.

ATR: Average True Range, historical movement measure.

POC: Point of Control or mean price area in profile context.

1 SD: Normal inner zone, most relevant for intraday in this source.

2 SD / 3 SD: Wider deviation zones, used mainly when price expands strongly.

Block: Repeating price interval where reactions often happen, such as gold 25/50 or oil 0.5/1.0 in the source examples.

Fresh OI: New OI or OI Change that price has not yet fully reacted to.

Late OI: OI signal where price already moved too far.

Premium / ATR ratio: Practical measure of whether option price is cheap or expensive relative to expected movement.

Covered Call: Long underlying + short call.

Protective Put: Long underlying + long put.

Collar: Long underlying + short call + long put.

Cash-Secured Put: Short put with cash reserve to buy/hold underlying if price falls.

Wheel: Repeated cycle of short put -> assignment/holding -> covered call -> called away -> repeat.

Synthetic Long: Long call + short put, mimics long underlying.

Deep Protective Put: Long underlying + far OTM put, cheap disaster hedge.

Calendar Spread: Different expiry, same strike.

Diagonal Spread: Different expiry and different strike.

Vertical Spread: Same expiry, different strike.

Straddle: Buy/sell call and put at same strike.

Strangle: Buy/sell OTM call and OTM put at different strikes.

Butterfly: Multi-leg structure designed to define profit around a middle zone.
