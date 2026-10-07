-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into instruments (id,isin,name,category,asset_type,ticker,price_eur,price_live,updated_at) values
('DEMO-WORLD','DEMO-WORLD','World Equity ETF','Broad ETF','ETFs','IWDA.AS',96.8,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-EUROPE','DEMO-EUROPE','Europe Equity ETF','Broad ETF','ETFs','IMEU.AS',52.4,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-TECH','DEMO-TECH','Technology ETF','Tech ETF','ETFs','QDVE.DE',143.1,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-ASML','DEMO-ASML','ASML','Stock','Stocks','ASML.AS',712,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-UNILEVER','DEMO-UNILEVER','Unilever','Stock','Stocks','UNA.AS',49.6,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-APPLE','DEMO-APPLE','Apple','Stock','Stocks','AAPL',184,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-JAPAN','DEMO-JAPAN','Japan Equity ETF','Broad ETF','ETFs','SJPA.AS',56.3,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-EM','DEMO-EM','Emerging Markets ETF','Broad ETF','ETFs','EMIM.AS',31.7,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-BOND-1','DEMO-BOND-1','Example Euro Bond 2028','Bond','Bonds',NULL,0.985,FALSE,'2026-10-07T14:38:18.748232Z'),
('DEMO-CORP','DEMO-CORP','Euro Corporate Bond Fund','Bond fund','Bonds','IEAC.AS',101.8,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-BTC','DEMO-BTC','Bitcoin','Crypto','Crypto','BTC-EUR',58200,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-ETH','DEMO-ETH','Ethereum','Crypto','Crypto','ETH-EUR',2780,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-MWORLD','DEMO-MWORLD','Managed Global Equity Fund','Broad ETF','ETFs','VWRL.AS',112.3,TRUE,'2026-10-07T14:38:18.748232Z'),
('DEMO-MBOND','DEMO-MBOND','Managed Euro Bond Fund','Bond fund','Bonds','AGGH.AS',95.4,TRUE,'2026-10-07T14:38:18.748232Z')
on conflict do nothing;
commit;
