SELECT o.*, p.product_version_id, p.category
FROM b_filtered AS o
LEFT JOIN products AS p ON o.product_id = p.product_id;
