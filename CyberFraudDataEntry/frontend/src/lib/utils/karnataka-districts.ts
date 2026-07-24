/** The 36 Karnataka districts, matching what `police_stations` uses.
 *
 *  Used by the Accused / Victim Accounts sections on DSR -> New FIR:
 *  the District select is populated from this list only when
 *  State == "Karnataka"; other states leave District disabled + empty
 *  (the operator's own note keeps it that way; DB column stays nullable).
 */
export const KARNATAKA_DISTRICTS: string[] = [
  'Bagalkot',
  'Ballari',
  'Belagavi',
  'Bengaluru Rural',
  'Bengaluru Urban',
  'Bidar',
  'Chamarajanagar',
  'Chikkaballapur',
  'Chikkamagaluru',
  'Chitradurga',
  'Dakshina Kannada',
  'Davanagere',
  'Dharwad',
  'Gadag',
  'Hassan',
  'Haveri',
  'Kalaburagi',
  'Kodagu',
  'Kolar',
  'Koppal',
  'Mandya',
  'Mysuru',
  'Raichur',
  'Ramanagara',
  'Shivamogga',
  'Tumakuru',
  'Udupi',
  'Uttara Kannada',
  'Vijayanagara',
  'Vijayapura',
  'Yadgir',
  'Bengaluru City',
  'Mysuru City',
  'Hubli-Dharwad',
  'Mangaluru City',
  'Belagavi City',
];
