export type MoneyDirection = "positive" | "negative" | "zero";

export type FormattedMoneyAmount = Readonly<{
  direction: MoneyDirection;
  magnitude: string;
  sign: "+" | "−" | "";
  display: string;
}>;

const DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]*)\.[0-9]{2}$/;
const CURRENCY_PATTERN = /^[A-Z]{3}$/;

export function formatMoneyAmount(
  amount: string,
  currency: string,
): FormattedMoneyAmount {
  if (!DECIMAL_PATTERN.test(amount) || !CURRENCY_PATTERN.test(currency)) {
    throw new Error("MoneyAmount requires a validated amount and currency");
  }

  const hasNegativePrefix = amount.startsWith("-");
  const unsignedAmount = hasNegativePrefix ? amount.slice(1) : amount;
  const [integerDigits, fractionalDigits] = unsignedAmount.split(".");
  const isZero = integerDigits === "0" && fractionalDigits === "00";
  const direction: MoneyDirection = isZero
    ? "zero"
    : hasNegativePrefix
      ? "negative"
      : "positive";
  const sign = direction === "positive" ? "+" : direction === "negative" ? "−" : "";
  const groupedInteger = integerDigits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const fraction =
    currency === "CLP" && fractionalDigits === "00" ? "" : `,${fractionalDigits}`;
  const magnitude = `${groupedInteger}${fraction}`;

  return {
    direction,
    magnitude,
    sign,
    display: `${sign}${magnitude} ${currency}`,
  };
}
