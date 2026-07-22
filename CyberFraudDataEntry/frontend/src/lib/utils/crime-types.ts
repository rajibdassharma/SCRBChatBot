/** KSP Cyber Crime classification list — source of truth for the
 *  Crime Type dropdown on the Case Entry form.
 *
 *  Order matches the "Classification Details" PDF (SL. NO. 1-31),
 *  all sitting under the single Major Head "CYBER CRIME". "Others"
 *  is the escape hatch — picking it reveals a free-text box on the
 *  form, and the text lands in `crime_type_other` on the case row.
 *
 *  Adding a new sub-head: append to the list. The dropdown updates
 *  automatically. The backend `crime_type` column already fits any
 *  new entry up to VARCHAR(200) (migration 016). */
export const CYBER_CRIME_TYPES: readonly string[] = [
  'Advertising Frauds',
  'AEPS Frauds',
  'ATM Frauds',
  'Business Frauds',
  'Card Skimming',
  'Credit Card Frauds',
  'Bitcoin, Crypto Currency, etc.',
  'CSAM (Child pornography)',
  'Data Theft',
  'Deep fake / Deep nudes',
  'Digital Arrest',
  'Email Spoofing Fraud',
  'Fake Customer Care',
  'Fedex',
  'Gift, I Phone Lottery Fraud',
  'Hacking of Accounts & Ids',
  'Investment Fraud (Part Time Job, Task Review)',
  'Investment Fraud (Trading & Share Trading)',
  'Job Frauds',
  'Loan Frauds',
  'Matrimonial Frauds',
  'OLX Frauds',
  'Online Money Transfer',
  'OTP Frauds (KYC Update, App link)',
  'Phishing (Taking Password & Information)',
  'Ransomware Attacks, Installing Spyware & Trojan, Using Other malware & Viruses to infect digital server',
  'Remote Access Frauds (Anydesk/TeamViewer)',
  'Sextortion & Revenge Porn',
  'SIM card Swapping / SIM Jacking / SIM cloning',
  'Social Media Cases (Instagram/Facebook/Whatsapp/X/Telegram etc)',
  'Others',
] as const;

export const CRIME_TYPE_OTHERS = 'Others';
