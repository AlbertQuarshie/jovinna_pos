-- One row per STK Push result received from Safaricom
CREATE TABLE IF NOT EXISTS payments (
  checkout_id TEXT PRIMARY KEY,   -- Safaricom's CheckoutRequestID (the app knows this)
  result_code INTEGER NOT NULL,   -- 0 = paid
  result_desc TEXT,
  receipt     TEXT,               -- M-Pesa code, e.g. SLK4H7XYZ1
  amount      REAL,
  phone       TEXT,
  paid_at     TEXT,               -- Safaricom's TransactionDate, e.g. 20261028143055
  received_at TEXT NOT NULL
);
