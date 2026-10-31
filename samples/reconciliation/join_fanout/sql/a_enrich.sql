SELECT o.*, p.product_version_id, p.category
FROM a_filtered AS o
LEFT JOIN a_products_current AS p ON o.product_id = p.product_id;
