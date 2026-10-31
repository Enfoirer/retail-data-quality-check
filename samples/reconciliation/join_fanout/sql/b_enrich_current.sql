SELECT o.*, p.product_version_id, p.category
FROM b_filtered AS o
LEFT JOIN b_products_current AS p ON o.product_id = p.product_id;
