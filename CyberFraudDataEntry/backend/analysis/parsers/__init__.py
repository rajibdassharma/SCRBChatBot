"""F2 -- statement parsing.

NOT ORGANISED BY BANK, AND THAT WAS A CORRECTION
------------------------------------------------
The plan called for an SBI parser, an HDFC parser and an Axis parser,
on a profile that said those three covered ~70% of the corpus. Two
measurements killed that idea.

First, the bank labels were wrong. Detection matched a bank's name
anywhere on page one -- but page one carries transaction narrations,
and a narration names the COUNTERPARTY's bank. One file in the corpus
matched "SBI", "HDFC" and "Axis" simultaneously. The reported split was
an artefact of which name appeared first in the lookup list.

Second, and more usefully: statement layouts do not cluster by bank at
all. Measured over 600 files, the most common column-header signature
covers 7.7% -- there is no dominant template to hand-write. Layout
tracks the core banking system (Finacle, BaNCS, ...) and whoever
generated the PDF, so one bank emits several layouts and several banks
share one.

What the same 600 files DO show is that every layout is the same
LOGICAL shape under different words:

    date . [value date] . description . [cheque/ref] . debit . credit . balance

with "debit" written as debit / debits / withdrawals / withdraws /
withdrawal amt / debit amount, and so on down every column. So this
package has ONE table parser driven by a synonym table, not N bank
parsers -- fewer lines, and it covers layouts nobody has seen yet.

MODULES
    values.py   dates, Indian-grouped amounts, Dr/Cr suffixes
    columns.py  header words -> canonical roles
    extract.py  PDF tables, Excel sheets, and a text-line fallback
    enrich.py   counterparty account / UPI / channel out of narration
    verify.py   balance-chain reconciliation -- the correctness gate

COVERAGE (measured, not projected)
    PDF    60% header table . 10% text-layout fallback . 17% scanned
           (the OCR queue, out of scope here) . 13% no transaction rows
    Excel  ~90%
    -> roughly 74% of the 16,234-file corpus

WHY RECONCILIATION IS NOT OPTIONAL
A statement parser that "works" is easy to produce and hard to trust:
mixing up the debit and credit columns still yields plausible rows, and
so does dropping every third line. Every statement carries its own
check -- the running balance. If prev_balance - debit + credit equals
balance on every row, the columns were read correctly and no row was
missed. verify.py runs that chain and the driver stores the result, so
a file is never counted as parsed merely because it produced output.
"""
