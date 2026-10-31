SELECT o.*, p.category
FROM a_filtered AS o
LEFT JOIN products AS p ON o.product_id = p.product_id;
