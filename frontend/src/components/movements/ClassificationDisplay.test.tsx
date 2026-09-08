import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ClassificationDisplay } from "@/components/movements/ClassificationDisplay";
import { ACTIVE_CATEGORY_ID } from "@/test/fixtures";

describe("ClassificationDisplay", () => {
  it("shows active and inactive Category names without internal metadata", () => {
    const { rerender } = render(
      <ClassificationDisplay
        classification={{
          state: "CLASSIFIED",
          category: {
            id: ACTIVE_CATEGORY_ID,
            display_name: "Synthetic essentials",
            is_active: true,
          },
          revision: 7,
        }}
      />,
    );
    expect(screen.getByText("Category: Synthetic essentials")).toBeInTheDocument();
    expect(screen.queryByText("Inactive")).not.toBeInTheDocument();

    rerender(
      <ClassificationDisplay
        classification={{
          state: "CLASSIFIED",
          category: {
            id: ACTIVE_CATEGORY_ID,
            display_name: "Synthetic archived topic",
            is_active: false,
          },
          revision: 8,
        }}
      />,
    );
    expect(screen.getByText("Category: Synthetic archived topic · Inactive")).toBeInTheDocument();
    expect(screen.queryByText(ACTIVE_CATEGORY_ID)).not.toBeInTheDocument();
    expect(screen.queryByText("8")).not.toBeInTheDocument();
  });

  it.each([
    { state: "NEVER_ASSIGNED", category: null, revision: 0 } as const,
    { state: "CLEARED", category: null, revision: 3 } as const,
  ])("shows $state as Unclassified while retaining distinct input state", (classification) => {
    render(<ClassificationDisplay classification={classification} />);
    expect(screen.getByText("Category: Unclassified")).toBeInTheDocument();
    expect(screen.queryByText(classification.state)).not.toBeInTheDocument();
  });
});
