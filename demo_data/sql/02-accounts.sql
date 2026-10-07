-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into accounts (id,institution_id,name,kind,opened,interest_rate_pct,maturity,counted_in_net_worth,value_eur,cash_eur,profit_eur,fees_paid_eur,active,updated_at) values
('example-broker-one','example-broker-one','Example Broker One','brokerage','2021-10',NULL,NULL,TRUE,28600.2,485,4155.2,NULL,TRUE,'2026-10-07T14:38:18.748232Z'),
('example-broker-two','example-broker-two','Example Broker Two','brokerage','2023-01',NULL,NULL,TRUE,24051.0,210,2001.0,NULL,TRUE,'2026-10-07T14:38:18.748232Z'),
('example-crypto-exchange','example-crypto-exchange','Example Crypto Exchange','brokerage','2024-04',NULL,NULL,TRUE,3939.0,95,234.00000000000023,NULL,TRUE,'2026-10-07T14:38:18.748232Z'),
('example-managed-portfolio','abn-amro','Example Managed Portfolio','managed','2022-01-01',NULL,NULL,TRUE,22019.5,350,3019.5,290,TRUE,'2026-10-07T14:38:18.748232Z'),
('demo-bank-current-account','demo-bank','Demo Bank Current Account','current',NULL,0,NULL,TRUE,2750.0,NULL,NULL,NULL,TRUE,'2026-10-07T14:38:18.748232Z'),
('demo-travel-card','demo-travel-bank','Demo Travel Card','savings',NULL,0,NULL,TRUE,650.0,NULL,NULL,NULL,TRUE,'2026-10-07T14:38:18.748232Z'),
('emergency-savings','example-savings-bank','Emergency Savings','savings',NULL,2.2,NULL,TRUE,12532.0,NULL,NULL,NULL,TRUE,'2026-10-07T14:38:18.748232Z'),
('fixed-deposit','example-deposit-bank','Fixed Deposit','deposit',NULL,3.1,'2027-06-04',TRUE,6670.0,NULL,NULL,NULL,TRUE,'2026-10-07T14:38:18.748232Z'),
('example-student-loan','example-student-loan','Example Student Loan','loan',NULL,2.35,NULL,TRUE,14750.0,NULL,NULL,NULL,TRUE,'2026-10-07T14:38:18.748232Z'),
('example-personal-loan','example-personal-loan','Example Personal Loan','loan',NULL,4.5,NULL,TRUE,2400.0,NULL,NULL,NULL,TRUE,'2026-10-07T14:38:18.748232Z')
on conflict do nothing;
commit;
