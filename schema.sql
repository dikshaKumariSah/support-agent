CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    pincode TEXT CONSTRAINT pincode_six_digits CHECK (pincode ~ '^[0-9]{6}$')
);

CREATE TABLE memberships (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    tier TEXT NOT NULL CHECK (tier IN ('Free', 'Plus', 'Total')),
    start_date DATE NOT NULL,
    last_payment_date DATE,
    last_payment_amount NUMERIC(10, 2),
    renewal_date DATE,
    status TEXT NOT NULL CHECK (status IN ('Active', 'Cancelled', 'Expired')),
    cancel_reason TEXT
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product TEXT NOT NULL,
    order_date DATE NOT NULL,
    warranty_months INTEGER,
    expected_delivery DATE,
    status TEXT NOT NULL CHECK (status IN ('On the way', 'Rescheduled', 'Cancelled', 'Delivered')),
    courier_status TEXT,
    delay_reason TEXT,
    amount NUMERIC(10, 2)
);

CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_id INTEGER REFERENCES orders(id),
    type TEXT NOT NULL,
    location TEXT NOT NULL CHECK (location IN ('Store', 'Home')),
    appointment_time TIMESTAMP NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Booked', 'Done', 'Cancelled'))
);

CREATE TABLE plans (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_id INTEGER REFERENCES orders(id),
    type TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('Membership', 'Separate')),
    start_date DATE NOT NULL,
    end_date DATE,
    price NUMERIC(10, 2)
);

CREATE TABLE tickets (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    status TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'Taken', 'Solved')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    brief JSONB NOT NULL
);