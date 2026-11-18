-- Sample data for ElectroMart (made-up). Run after schema.sql.
-- Tickets are not included: Riya creates them during chats.

INSERT INTO customers (id, name, phone, email, address, city, state, pincode) VALUES (1, 'Asha Rao', '9800000001', 'asha@mail.com', '12 MG Road', 'Bengaluru', 'Karnataka', '560001');
INSERT INTO customers (id, name, phone, email, address, city, state, pincode) VALUES (2, 'Ravi Rao', '9800000001', 'ravi@mail.com', '12 MG Road', 'Bengaluru', 'Karnataka', '560001');

INSERT INTO memberships (id, customer_id, tier, start_date, last_payment_date, last_payment_amount, renewal_date, status, cancel_reason) VALUES (1, 1, 'Plus', '2026-01-10', '2026-01-10', 1999.00, '2027-01-10', 'Active', NULL);

INSERT INTO orders (id, customer_id, product, order_date, warranty_months, expected_delivery, status, courier_status, delay_reason, amount) VALUES (1, 1, 'Laptop', '2026-11-05', 12, '2026-11-10', 'On the way', 'Held at facility', 'Heavy rain in the area', 54999.00);

INSERT INTO services (id, customer_id, order_id, type, location, appointment_time, status) VALUES (1, 1, 1, 'Laptop repair', 'Store', '2026-11-20 14:30:00', 'Booked');

INSERT INTO plans (id, customer_id, order_id, type, source, start_date, end_date, price) VALUES (1, 1, NULL, 'Protection plan', 'Membership', '2026-01-10', '2027-01-10', NULL);
INSERT INTO plans (id, customer_id, order_id, type, source, start_date, end_date, price) VALUES (2, 1, 1, 'Antivirus subscription', 'Separate', '2026-11-05', '2027-11-05', 999.00);

-- Move each id counter past the rows above, so new rows don't reuse an id.
SELECT setval(pg_get_serial_sequence('customers', 'id'), (SELECT MAX(id) FROM customers));
SELECT setval(pg_get_serial_sequence('memberships', 'id'), (SELECT MAX(id) FROM memberships));
SELECT setval(pg_get_serial_sequence('orders', 'id'), (SELECT MAX(id) FROM orders));
SELECT setval(pg_get_serial_sequence('services', 'id'), (SELECT MAX(id) FROM services));
SELECT setval(pg_get_serial_sequence('plans', 'id'), (SELECT MAX(id) FROM plans));
