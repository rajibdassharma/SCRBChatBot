USE [NCRP]
GO

SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

-- ============================================================
-- 1. MoneyTransferTo
-- ============================================================
CREATE TABLE [dbo].[MoneyTransferTo](
	[TrailID] [bigint] IDENTITY(1,1) NOT NULL,
	[SNo] [int] NULL,
	[AcknowledgementNo] [bigint] NOT NULL,
	[AccountOrWalletId] [varchar](100) NULL,
	[TransactionUTR] [varchar](100) NULL,
	[BankFIs] [nvarchar](200) NULL,
	[Layer] [int] NULL,
	[AccountNo] [varchar](50) NULL,
	[IFSCCode] [varchar](20) NULL,
	[TransactionDate] [datetime2](0) NULL,
	[TransactionUTR2] [varchar](100) NULL,
	[TransactionAmount] [decimal](18, 2) NULL,
	[DisputedAmount] [decimal](18, 2) NULL,
	[ReferenceNo] [varchar](100) NULL,
	[Remarks] [nvarchar](2000) NULL,
	[ActionTakenByBank] [nvarchar](500) NULL,
	[DateOfAction] [datetime2](0) NULL,
	[PISNodal] [varchar](50) NULL,
PRIMARY KEY CLUSTERED ([TrailID] ASC)
) ON [PRIMARY]
GO

CREATE INDEX IX_MoneyTransferTo_AckNo ON [dbo].[MoneyTransferTo]([AcknowledgementNo]);
GO

-- ============================================================
-- 2. OtherTransactions
-- ============================================================
CREATE TABLE [dbo].[OtherTransactions](
	[TrailID] [bigint] IDENTITY(1,1) NOT NULL,
	[SNo] [int] NULL,
	[AcknowledgementNo] [bigint] NOT NULL,
	[AccountOrWalletId] [varchar](100) NULL,
	[TransactionUTR] [varchar](100) NULL,
	[OtherDate] [datetime2](0) NULL,
	[TransactionAmount] [decimal](18, 2) NULL,
	[OtherAmount] [decimal](18, 2) NULL,
	[ReferenceNo] [varchar](100) NULL,
	[Remarks] [nvarchar](2000) NULL,
	[ActionTakenByBank] [nvarchar](500) NULL,
	[DateOfAction] [datetime2](0) NULL,
	[PISNodal] [varchar](50) NULL,
PRIMARY KEY CLUSTERED ([TrailID] ASC)
) ON [PRIMARY]
GO

CREATE INDEX IX_OtherTransactions_AckNo ON [dbo].[OtherTransactions]([AcknowledgementNo]);
GO

-- ============================================================
-- 3. PutOnHold
-- ============================================================
CREATE TABLE [dbo].[PutOnHold](
	[TrailID] [bigint] IDENTITY(1,1) NOT NULL,
	[SNo] [int] NULL,
	[AcknowledgementNo] [bigint] NOT NULL,
	[AccountOrWalletId] [varchar](100) NULL,
	[TransactionUTR] [varchar](100) NULL,
	[PutOnHoldDate] [datetime2](0) NULL,
	[PutOnHoldAmount] [decimal](18, 2) NULL,
	[ActionTakenByBank] [nvarchar](500) NULL,
	[DateOfAction] [datetime2](0) NULL,
	[Layer] [int] NULL,
	[PISNodal] [varchar](50) NULL,
PRIMARY KEY CLUSTERED ([TrailID] ASC)
) ON [PRIMARY]
GO

CREATE INDEX IX_PutOnHold_AckNo ON [dbo].[PutOnHold]([AcknowledgementNo]);
GO

-- ============================================================
-- 4. OthersLessThan500
-- ============================================================
CREATE TABLE [dbo].[OthersLessThan500](
	[TrailID] [bigint] IDENTITY(1,1) NOT NULL,
	[SNo] [int] NULL,
	[AcknowledgementNo] [bigint] NOT NULL,
	[AccountOrWalletId] [varchar](100) NULL,
	[TransactionUTR] [varchar](100) NULL,
	[ReferenceNo] [varchar](100) NULL,
	[Remarks] [nvarchar](2000) NULL,
	[ActionTakenByBank] [nvarchar](500) NULL,
	[DateOfAction] [datetime2](0) NULL,
	[PISNodal] [varchar](50) NULL,
PRIMARY KEY CLUSTERED ([TrailID] ASC)
) ON [PRIMARY]
GO

CREATE INDEX IX_OthersLessThan500_AckNo ON [dbo].[OthersLessThan500]([AcknowledgementNo]);
GO

-- ============================================================
-- 5. AEPS
-- ============================================================
CREATE TABLE [dbo].[AEPS](
	[TrailID] [bigint] IDENTITY(1,1) NOT NULL,
	[SNo] [int] NULL,
	[AcknowledgementNo] [bigint] NOT NULL,
	[AccountOrWalletId] [varchar](100) NULL,
	[TransactionUTR] [varchar](100) NULL,
	[WithdrawalDate] [datetime2](0) NULL,
	[WithdrawalAmount] [decimal](18, 2) NULL,
	[ReferenceNo] [varchar](100) NULL,
	[Remarks] [nvarchar](2000) NULL,
	[ActionTakenByBank] [nvarchar](500) NULL,
	[DateOfAction] [datetime2](0) NULL,
	[ParentTrans] [varchar](100) NULL,
	[ParentAccountNo] [varchar](50) NULL,
	[ParentIFSCCode] [varchar](20) NULL,
	[ParentLayer] [int] NULL,
	[PISNodal] [varchar](50) NULL,
PRIMARY KEY CLUSTERED ([TrailID] ASC)
) ON [PRIMARY]
GO

CREATE INDEX IX_AEPS_AckNo ON [dbo].[AEPS]([AcknowledgementNo]);
GO

-- ============================================================
-- 6. ATMWithdrawal
-- ============================================================
CREATE TABLE [dbo].[ATMWithdrawal](
	[TrailID] [bigint] IDENTITY(1,1) NOT NULL,
	[SNo] [int] NULL,
	[AcknowledgementNo] [bigint] NOT NULL,
	[AccountOrWalletId] [varchar](100) NULL,
	[TransactionUTR] [varchar](100) NULL,
	[WithdrawalDateTime] [datetime2](0) NULL,
	[WithdrawalAmount] [decimal](18, 2) NULL,
	[DisputedAmount] [decimal](18, 2) NULL,
	[ATMID] [varchar](50) NULL,
	[ATMLocation] [nvarchar](300) NULL,
	[ReferenceNo] [varchar](100) NULL,
	[Remarks] [nvarchar](2000) NULL,
	[ActionTakenByBank] [nvarchar](500) NULL,
	[DateOfAction] [datetime2](0) NULL,
	[PISNodal] [varchar](50) NULL,
PRIMARY KEY CLUSTERED ([TrailID] ASC)
) ON [PRIMARY]
GO

CREATE INDEX IX_ATMWithdrawal_AckNo ON [dbo].[ATMWithdrawal]([AcknowledgementNo]);
GO
