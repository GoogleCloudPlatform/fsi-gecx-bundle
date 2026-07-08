FROM gcr.io/google.com/cloudsdktool/cloud-sdk:slim

WORKDIR /app

COPY scripts/datastream/reconcile_lakehouse_views.py /app/reconcile_lakehouse_views.py
COPY deployment/bigquery /app/deployment/bigquery

ENTRYPOINT ["python3", "/app/reconcile_lakehouse_views.py"]
