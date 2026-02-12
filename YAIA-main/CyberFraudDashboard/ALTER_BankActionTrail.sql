USE [NCRP]
GO

-- ============================================================
-- Migration: Drop the legacy flat BankActionTrail table
-- Run ONLY after the 6 new tables have been created
-- (MoneyTransferTo, OtherTransactions, PutOnHold,
--  OthersLessThan500, AEPS, ATMWithdrawal)
-- ============================================================

IF OBJECT_ID('dbo.BankActionTrail', 'U') IS NOT NULL
BEGIN
    DROP TABLE [dbo].[BankActionTrail];
    PRINT 'Dropped legacy table dbo.BankActionTrail';
END
GO
