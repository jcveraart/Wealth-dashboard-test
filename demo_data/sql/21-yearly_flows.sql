-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into yearly_flows (year,account,deposits_eur,withdrawals_eur,invested_eur,dividends_eur,interest_received_eur,interest_paid_eur,fees_eur,taxes_eur,profit_eur,return_pct,note) values
(2022,'Example Broker One',5000,500,4500,156,35,0,45,0,3192.2,-1.0,'Invented yearly statement; not an actual account.'),
(2022,'Example Broker Two',5000,500,4500,208,35,0,45,0,2552.96,11.6,'Invented yearly statement; not an actual account.'),
(2022,'Example Crypto Exchange',5000,500,4500,231,35,0,45,0,77.18,7.6,'Invented yearly statement; not an actual account.'),
(2022,'Example Managed Portfolio',5000,500,4500,203,35,0,45,0,-1220.74,9.3,'Invented yearly statement; not an actual account.'),
(2023,'Example Broker One',5000,500,4500,239,35,0,45,0,169.06,-2.4,'Invented yearly statement; not an actual account.'),
(2023,'Example Broker Two',5000,500,4500,170,35,0,45,0,881.08,-4.6,'Invented yearly statement; not an actual account.'),
(2023,'Example Crypto Exchange',5000,500,4500,215,35,0,45,0,352.39,-0.3,'Invented yearly statement; not an actual account.'),
(2023,'Example Managed Portfolio',5000,500,4500,111,35,0,45,0,-63.51,7.2,'Invented yearly statement; not an actual account.'),
(2024,'Example Broker One',5000,500,4500,161,35,0,45,0,1049.33,-3.0,'Invented yearly statement; not an actual account.'),
(2024,'Example Broker Two',5000,500,4500,171,35,0,45,0,637.46,3.3,'Invented yearly statement; not an actual account.'),
(2024,'Example Crypto Exchange',5000,500,4500,157,35,0,45,0,-74.01,5.1,'Invented yearly statement; not an actual account.'),
(2024,'Example Managed Portfolio',5000,500,4500,184,35,0,45,0,1148.99,-0.9,'Invented yearly statement; not an actual account.'),
(2025,'Example Broker One',5000,500,4500,171,35,0,45,0,-1678.14,7.8,'Invented yearly statement; not an actual account.'),
(2025,'Example Broker Two',5000,500,4500,180,35,0,45,0,1855.94,6.1,'Invented yearly statement; not an actual account.'),
(2025,'Example Crypto Exchange',5000,500,4500,190,35,0,45,0,-0.81,6.8,'Invented yearly statement; not an actual account.'),
(2025,'Example Managed Portfolio',5000,500,4500,174,35,0,45,0,108.37,9.4,'Invented yearly statement; not an actual account.'),
(2026,'Example Broker One',5000,500,4500,150,35,0,45,0,-613.25,7.9,'Invented yearly statement; not an actual account.'),
(2026,'Example Broker Two',5000,500,4500,146,35,0,45,0,-810.67,10.9,'Invented yearly statement; not an actual account.'),
(2026,'Example Crypto Exchange',5000,500,4500,182,35,0,45,0,-61.63,11.5,'Invented yearly statement; not an actual account.'),
(2026,'Example Managed Portfolio',5000,500,4500,165,35,0,45,0,-288.33,1.8,'Invented yearly statement; not an actual account.')
on conflict do nothing;
commit;
