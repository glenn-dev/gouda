# ADR-0005: Define canonical movement sign across asset and liability accounts

- Status: Accepted
- Date: 2026-08-23
- Supersedes: the universal scope of ADR-0001

## Context

ADR-0001 established one canonical signed amount and correctly defined the
observed Santander current-account behavior: positive means money enters the
referenced asset account and negative means money leaves it. That wording is
incomplete for a credit-card account. A card purchase increases a liability,
while a card payment reduces that liability; neither event is fully described
as cash entering or leaving a liability account.

Gouda needs one canonical movement meaning across current accounts and future
credit-card accounts without making provider-native direction or household
expense classification the same concept. The source contracts also need to
preserve their own meanings for audit and safe parsing.

## Decision

### Canonical signed amount

`Movement.signed_amount` represents the change in the referenced account's
contribution to household net worth caused by that movement:

- positive means the account's contribution to household net worth increases;
- negative means the account's contribution to household net worth decreases.

This remains one authoritative signed amount. It is not an expense/income
classification and it is not a provider-specific debit/credit flag.

### Economic account orientation

The domain distinguishes product/source kind from economic orientation:

- product/source kind describes what the account is, such as current account
  or credit card;
- economic orientation describes whether the account is an `ASSET` or a
  `LIABILITY`.

For an `ASSET` account:

- an asset increase is positive;
- an asset decrease is negative.

For a `LIABILITY` account:

- a debt reduction is positive;
- a debt increase is negative.

An eventual `Account` model should carry economic orientation explicitly. It
must not derive orientation implicitly from a provider name or source kind.
The current schema does not yet implement this field or a credit-card account
kind.

### Source-native versus canonical meaning

Provider-specific facts remain at the source boundary:

- Santander current-account cargo/abono meaning remains source-native;
- Santander TDC `debt_effect` remains source-native, where positive means an
  increase in billed card debt and negative means a reduction.

The source adapter/parser boundary converts supported source-native semantics
into the one canonical `Movement.signed_amount`. For a liability card,

```text
canonical signed amount = -source debt_effect
```

Source-native values and direction may be retained in parser results, raw
records, or provenance. They must not become a second independently mutable
canonical amount.

### Classification and transfers

The sign alone does not determine income, expense, refund, fee, tax, or
transfer. Those are later semantic classifications.

A transfer is one economic movement represented by two account movements. A
current-account payment side is negative and the card-account payment side is
positive. When paired, their combined household net-worth effect is zero.
Importing both sides is correct; double-counting occurs only when reporting or
classification treats a transfer side as a separate expense.

Transfer pairing, transaction identity, and classification algorithms remain
future concerns.

## Compatibility with existing current-account imports

Existing Santander current-account values remain semantically valid without
rewrite:

- cargo/debit remains negative;
- abono/credit remains positive;
- deposits and incoming transfers remain positive;
- purchases, fees, and outgoing transfers remain negative.

No parser, importer, model, migration, or persisted value changes are implied
by this ADR. The new definition generalizes the meaning to liability accounts;
it does not reinterpret existing asset-account data.

## Consequences

- Canonical movement arithmetic is coherent across asset and liability
  accounts and can support household net-worth aggregation.
- Account orientation becomes a required future domain concept for interpreting
  balances and converting source effects.
- Card purchases, interest, commissions, taxes, and insurance become negative
  canonical movements; card payments and refunds become positive canonical
  movements.
- Expense, income, refund, fee, tax, cash-flow, and transfer reporting require
  separate classification or relationship layers.
- Source contracts can describe Santander faithfully without deciding all
  household semantics.
- A full debit/credit journal is not required for this movement-ledger
  decision.

## Rejected alternatives

- **Raw provider/debt orientation as canonical:** rejected because source signs
  differ across providers and a debt increase would not have a consistent
  household meaning.
- **Sign as expense/income:** rejected because transfers, refunds, fees,
  liabilities, and account-side movements cannot be classified from sign
  alone.
- **Universal literal “money enters/leaves the account”:** retained as a
  correct asset-account explanation but rejected as the complete cross-product
  invariant because liability movements are not cash-account movements.
- **Full double-entry accounting now:** deferred as unnecessary for the
  current movement ledger; it may be reconsidered when transaction journals,
  counterparty identity, corrections, and reconciliation requirements justify
  it.
