SELECT *
FROM orders
WHERE status IN ('paid', 'cancelled');
