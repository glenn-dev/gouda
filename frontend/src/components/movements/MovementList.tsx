import type { MovementReportItem } from "@/api";
import { MoneyAmount } from "@/components/gouda/MoneyAmount";
import { ClassificationDisplay } from "@/components/movements/ClassificationDisplay";

export function MovementList({
  movements,
}: Readonly<{ movements: ReadonlyArray<MovementReportItem> }>) {
  return (
    <ul aria-label="Movements" className="border-t border-border">
      {movements.map((movement) => (
        <MovementRow key={movement.movement_id} movement={movement} />
      ))}
    </ul>
  );
}

function MovementRow({ movement }: Readonly<{ movement: MovementReportItem }>) {
  return (
    <li className="grid min-w-0 gap-2 border-b border-border py-3 md:grid-cols-[7rem_minmax(0,1fr)_auto] md:gap-4">
      <time
        className="text-sm leading-normal text-muted-foreground md:pt-0.5"
        dateTime={movement.occurrence_date}
      >
        {movement.occurrence_date}
      </time>
      <div className="min-w-0 space-y-1">
        <p className="wrap-break-word text-base leading-normal text-foreground">
          {movement.description ?? "No description"}
        </p>
        <ClassificationDisplay classification={movement.classification} />
      </div>
      <div className="max-w-full overflow-x-auto text-right md:overflow-visible md:pt-0.5">
        <MoneyAmount amount={movement.signed_amount} currency={movement.currency} />
      </div>
    </li>
  );
}
