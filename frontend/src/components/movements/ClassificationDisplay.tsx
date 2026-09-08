import type { MovementClassification } from "@/api";

export function ClassificationDisplay({
  classification,
}: Readonly<{ classification: MovementClassification }>) {
  if (classification.state !== "CLASSIFIED") {
    return (
      <p className="text-sm leading-normal text-muted-foreground">
        Category: Unclassified
      </p>
    );
  }

  return (
    <p className="text-sm leading-normal text-muted-foreground">
      Category: {classification.category.display_name}
      {!classification.category.is_active && " · Inactive"}
    </p>
  );
}
