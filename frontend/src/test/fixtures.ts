export const PRIMARY_ACCOUNT_ID = "11111111-1111-4111-8111-111111111111";
export const CARD_ACCOUNT_ID = "22222222-2222-4222-8222-222222222222";
export const FIRST_MOVEMENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const SECOND_MOVEMENT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

export const accountsResponse = {
  count: 2,
  accounts: [
    {
      id: PRIMARY_ACCOUNT_ID,
      display_name: "Synthetic Daily Account",
      kind: "CURRENT",
      currency: "CLP",
    },
    {
      id: CARD_ACCOUNT_ID,
      display_name: "Synthetic Card",
      kind: "CREDIT_CARD",
      currency: "USD",
    },
  ],
};

export function movementReportResponse(
  accountId = PRIMARY_ACCOUNT_ID,
  startDate = "2026-04-01",
  endDate = "2026-04-30",
) {
  const currency = accountId === CARD_ACCOUNT_ID ? "USD" : "CLP";
  return {
    account_id: accountId,
    start_date: startDate,
    end_date: endDate,
    movement_count: 2,
    net_signed_amount: "1234567890123456.77",
    movements: [
      {
        movement_id: FIRST_MOVEMENT_ID,
        account_id: accountId,
        occurrence_date: "2026-04-30",
        signed_amount: "1234567890123456.78",
        currency,
        description: "Synthetic returned first",
        source_trace: {
          original_filename: "SYNTHETIC_PRIVATE_FILENAME.xlsx",
          raw_record_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        },
      },
      {
        movement_id: SECOND_MOVEMENT_ID,
        account_id: accountId,
        occurrence_date: "2026-04-01",
        signed_amount: "-0.01",
        currency,
        description: "Synthetic returned second",
        source_trace: {
          content_digest: "SYNTHETIC_PRIVATE_DIGEST",
          import_batch_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        },
      },
    ],
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}
