import { describe, expect, it } from "vitest";

import { formatMoneyAmount } from "@/lib/money";

describe("exact string-only money formatting", () => {
  it.each([
    ["12345.00", "CLP", "positive", "+12.345 CLP"],
    ["-12345.00", "CLP", "negative", "−12.345 CLP"],
    ["0.00", "CLP", "zero", "0 CLP"],
    ["-0.00", "CLP", "zero", "0 CLP"],
    ["12345.60", "CLP", "positive", "+12.345,60 CLP"],
    ["-0.01", "CLP", "negative", "−0,01 CLP"],
    ["12345.00", "USD", "positive", "+12.345,00 USD"],
    [
      "9999999999999999999999999999.01",
      "CLP",
      "positive",
      "+9.999.999.999.999.999.999.999.999.999,01 CLP",
    ],
  ] as const)("formats %s %s without changing precision", (amount, currency, direction, display) => {
    expect(formatMoneyAmount(amount, currency)).toMatchObject({ direction, display });
  });

  it.each([
    ["+1.00", "CLP"],
    ["01.00", "CLP"],
    ["1", "CLP"],
    ["1.0", "CLP"],
    ["1.000", "CLP"],
    ["1e3", "CLP"],
    ["NaN", "CLP"],
    ["1.00", "clp"],
  ])("fails closed for malformed presentation input %s %s", (amount, currency) => {
    expect(() => formatMoneyAmount(amount, currency)).toThrow(
      "MoneyAmount requires a validated amount and currency",
    );
  });
});
