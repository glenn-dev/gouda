import { cn } from "@/lib/utils";
import { formatMoneyAmount } from "@/lib/money";

type MoneyAmountProps = Readonly<{
  amount: string;
  currency: string;
  className?: string;
}>;

export function MoneyAmount({ amount, currency, className }: MoneyAmountProps) {
  const formatted = formatMoneyAmount(amount, currency);
  const spokenDirection =
    formatted.direction.charAt(0).toUpperCase() + formatted.direction.slice(1);

  return (
    <span
      className={cn(
        "inline-block whitespace-nowrap font-medium tabular-nums text-foreground",
        formatted.direction === "positive" && "text-financial-positive",
        formatted.direction === "negative" && "text-financial-negative",
        className,
      )}
      data-direction={formatted.direction}
      data-slot="money-amount"
    >
      <span className="sr-only">
        {spokenDirection} {formatted.magnitude} {currency}
      </span>
      <span aria-hidden="true">{formatted.display}</span>
    </span>
  );
}
