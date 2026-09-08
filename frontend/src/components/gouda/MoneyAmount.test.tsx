import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MoneyAmount } from "@/components/gouda/MoneyAmount";

describe("MoneyAmount", () => {
  it("keeps the visible signed amount separate from one complete screen-reader phrase", () => {
    render(<MoneyAmount amount="12345.00" currency="CLP" />);

    const visible = screen.getByText("+12.345 CLP");
    const spoken = screen.getByText("Positive 12.345 CLP");
    expect(visible).toHaveAttribute("aria-hidden", "true");
    expect(spoken).toHaveClass("sr-only");
    expect(visible.closest("[data-slot='money-amount']")).toHaveAttribute(
      "data-direction",
      "positive",
    );
  });
});
