# Santander synthetic fixture

`synthetic-current-account.xlsx` is entirely fictional. It contains no copied
bank data, real names, real descriptions, real references, account identifiers,
or real balances.

The workbook intentionally mirrors the observed Santander layout:

- one visible sheet;
- metadata before the movement table;
- columns for date, auxiliary text, description, reference, debit, credit, and
  running balance;
- separate debit and credit cells;
- an intentional footer row to ignore;
- one candidate row with both debit and credit populated, which must be
  rejected;
- opening/ending balances whose arithmetic balances under the signed convention;
- one intentionally rejected movement candidate, which makes the parser's
  reconciliation evidence `INSUFFICIENT_DATA` despite that balanced arithmetic.

The fixture is for a future isolated Python parser and tests only. It is not a
Django model, migration, endpoint, or production import.
