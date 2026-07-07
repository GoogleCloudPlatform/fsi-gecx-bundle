import logging

from utils.database import SessionLocal
from services.cdc_monitoring import CdcMonitoringService

logging.basicConfig(level=logging.INFO)

db = SessionLocal()
service = CdcMonitoringService(db)
metrics = service.fetch_realtime_datastream_metrics()
print("METRICS:", metrics)
