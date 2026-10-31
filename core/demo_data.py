"""Deterministic fictional data, generated locally for demonstration only."""
import pandas as pd


def extended_demo():
    rows = []
    for month in range(18):
        period = pd.Period('2024-01', freq='M') + month
        for customer in range(30):
            if customer % 3 == 0 and month % 2:
                continue
            day = period.start_time if customer % 2 == 0 else period.end_time.normalize()
            quantity = 1 + (customer + month) % 5
            price = 100 + (customer % 3) * 250 + month * 5
            rows.append(dict(date=day.strftime('%Y-%m-%d'), order_id=f'DEMO-{month:02}-{customer:03}',
                             customer_id=f'C{customer:03}', product=['Notebook', 'Lamp', 'Keyboard'][customer % 3],
                             category=['Stationery', 'Home', 'Electronics'][customer % 3], quantity=quantity,
                             unit_price=price, unit_cost=round(price * .65, 2),
                             region=['North', 'South', 'East', 'West'][customer % 4], currency='INR'))
    return pd.DataFrame(rows).to_csv(index=False).encode('utf-8')
