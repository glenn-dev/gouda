import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MovementList } from "@/components/movements/MovementList";
import type { MovementReportItem } from "@/api";
import { movementReportResponse } from "@/test/fixtures";

describe("MovementList", () => {
  it("uses one semantic list and preserves backend order without client sorting", () => {
    const movements = movementReportResponse().movements as ReadonlyArray<MovementReportItem>;
    render(<MovementList movements={movements} />);

    const list = screen.getByRole("list", { name: "Movements" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Synthetic returned first")).toBeInTheDocument();
    expect(within(rows[0]).getByText("2026-04-30")).toHaveAttribute(
      "datetime",
      "2026-04-30",
    );
    expect(within(rows[1]).getByText("Synthetic returned second")).toBeInTheDocument();
    expect(within(rows[1]).getByText("2026-04-01")).toHaveAttribute(
      "datetime",
      "2026-04-01",
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
