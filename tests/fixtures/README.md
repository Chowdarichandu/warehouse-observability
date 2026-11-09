# Integration contract fixtures

These synthetic, sanitized fixtures exercise the published Airflow 2.10/3.1 and Airbyte API shapes. They were **not recorded from staging**. Tests replay them with HTTP MockTransport and botocore Stubber; no real Airflow, Airbyte, AWS, warehouse, or notification endpoints are contacted.

Before release, capture sanitized responses from the actual deployed versions and compare 20 sampled runs with the Airflow UI, including mapped tasks, retries, failures, late task updates, and externally triggered Airbyte jobs. Track that evidence in the staging acceptance report. Keep credentials and tenant data out of fixtures.
