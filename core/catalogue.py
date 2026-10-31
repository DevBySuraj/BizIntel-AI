"""The fixed business vocabulary. Source headers and original data stay intact."""

FIELDS = {
    "order_date": ("date", "Date the sale/order occurred", {"date", "sale_date", "transaction_date", "invoice_date", "invoicedate", "orderdate", "order_datetime", "orderdatetime", "saledate", "transactiondate"}),
    "order_id": ("text", "Order identifier; may repeat across line items", {"orderid", "invoice_no", "invoiceno", "invoice_id", "transaction_id", "ordernumber", "order_number", "order_no", "orderno"}),
    "customer_id": ("text", "Customer identifier", {"customerid", "client_id", "customernumber", "customer_number", "customerno", "customername", "customer_name"}),
    "segment": ("text", "Customer/business segment", {"customer_segment", "dealsize", "deal_size", "sales_channel", "channel", "distribution_channel"}),
    "product_id": ("text", "Product identifier", {"productid", "stock_code", "stockcode", "sku", "productcode", "product_code", "item_code", "itemcode"}),
    "product_name": ("text", "Product or item name", {"product", "item", "description"}),
    "category": ("text", "Product category", {"product_category", "department", "productline", "product_line", "item_category"}),
    "sub_category": ("text", "Product subcategory", {"subcategory", "sub_category_name"}),
    "sales": ("number", "Recorded sales amount for this row, not an order total repeated on each line", {"revenue", "line_revenue", "sales_revenue", "total_sales", "total_sale", "sales_amount", "sale_amount", "gross_sales", "net_sales"}),
    "quantity": ("number", "Units in this row; negative quantities may represent returns", {"qty", "units", "quantityordered", "quantity_ordered", "order_quantity", "orderquantity", "units_sold", "unit_sold", "quantity_sold", "items_sold"}),
    "discount": ("number", "Informational only; document whether fraction, percentage or amount", {"discount_rate", "discount_percent", "discount_amount"}),
    "profit": ("number", "Reported profit for this row; definition belongs to the source", {"reported_profit"}),
    "unit_price": ("number", "Selling price per unit; fallback sales assumes this is the realized price", {"unitprice", "price_per_unit", "priceeach", "price_each", "item_price"}),
    "unit_cost": ("number", "Cost of goods per unit", {"unitcost", "cost_per_unit"}),
    "total_cost": ("number", "Total cost of goods for this row", {"line_cost", "cost_of_goods", "cogs"}),
    "country": ("text", "Country", set()),
    "state": ("text", "State or province", {"province"}),
    "city": ("text", "City", set()),
    "region": ("text", "Business/geographic region", {"territory", "sales_region"}),
    "currency": ("text", "Currency code; no automatic exchange conversion", {"currency_code"}),
}
ALIASES = {role: {role, *details[2]} for role, details in FIELDS.items()}
NUMERIC_ROLES = {role for role, details in FIELDS.items() if details[0] == "number"}
MONEY_ROLES = {"sales", "profit", "unit_price", "unit_cost", "total_cost", "discount"}
LEGACY_ROLES = {"date": "order_date", "revenue": "sales", "product": "product_name"}
RECOMMENDED = ("order_date", "order_id", "customer_id", "product_name", "category",
               "region", "quantity", "sales", "profit")


def canonical_mapping(mapping):
    """Read older saved settings without silently resolving conflicting mappings."""
    result = {}
    for role, column in mapping.items():
        canonical = LEGACY_ROLES.get(role, role)
        if canonical not in FIELDS:
            raise ValueError(f"Unsupported field role: {role}")
        if canonical in result and result[canonical] != column:
            raise ValueError(f"Conflicting mappings for {canonical}.")
        result[canonical] = column
    return result


def analysis_columns(data, mapping):
    assigned = set(canonical_mapping(mapping).values()) - {None}
    return [column for column in data.columns if column in assigned]


def analysis_table(data, mapping):
    """Unmapped columns remain in the source/preview, outside business analysis."""
    return data.loc[:, analysis_columns(data, mapping)].copy()


def check_measure(column, mapping, monetary_ok):
    """Shared currency gate, including explicitly selected raw money columns."""
    monetary_columns = {value for role, value in canonical_mapping(mapping).items()
                        if role in MONEY_ROLES and value is not None}
    if not monetary_ok and (column == "@revenue" or column in monetary_columns):
        raise ValueError("Monetary analysis requires a single currency with no missing currency values in this scope.")
