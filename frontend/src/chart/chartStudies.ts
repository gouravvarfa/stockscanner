/**
 * RSI/Bollinger Bands, computed client-side from the same raw candles the
 * chart already has — mirrors backend/indicators/rsi.py's Wilder formula
 * and backend/indicators/bollinger.py's standard population-stddev bands
 * exactly, so numbers match the backend. Computed here (not re-fetched
 * from the backend on every settings change) so toggling a period/
 * multiplier recalculates instantly with no extra network round trip.
 */

export function calculateRSI(closes: number[], period = 14): Array<number | null> {
  const result: Array<number | null> = new Array(closes.length).fill(null);
  if (closes.length <= period) {
    return result;
  }

  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= period; i += 1) {
    const change = closes[i] - closes[i - 1];
    if (change >= 0) {
      avgGain += change;
    } else {
      avgLoss -= change;
    }
  }
  avgGain /= period;
  avgLoss /= period;

  result[period] = rsiFromAverages(avgGain, avgLoss);

  for (let i = period + 1; i < closes.length; i += 1) {
    const change = closes[i] - closes[i - 1];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    result[i] = rsiFromAverages(avgGain, avgLoss);
  }

  return result;
}

function rsiFromAverages(avgGain: number, avgLoss: number): number {
  if (avgLoss === 0) {
    return 100;
  }
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

export interface BollingerBandsResult {
  upper: Array<number | null>;
  middle: Array<number | null>;
  lower: Array<number | null>;
}

export function calculateBollingerBands(closes: number[], period = 20, multiplier = 2): BollingerBandsResult {
  const upper: Array<number | null> = new Array(closes.length).fill(null);
  const middle: Array<number | null> = new Array(closes.length).fill(null);
  const lower: Array<number | null> = new Array(closes.length).fill(null);

  for (let i = period - 1; i < closes.length; i += 1) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j += 1) {
      sum += closes[j];
    }
    const mean = sum / period;

    let variance = 0;
    for (let j = i - period + 1; j <= i; j += 1) {
      variance += (closes[j] - mean) ** 2;
    }
    const stdDev = Math.sqrt(variance / period);

    middle[i] = mean;
    upper[i] = mean + multiplier * stdDev;
    lower[i] = mean - multiplier * stdDev;
  }

  return { upper, middle, lower };
}
